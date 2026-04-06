#!/usr/bin/env python3
"""
喬政翔律師個人網站 - 後台管理伺服器
支援本地 + Tailscale 遠端存取，含密碼驗證

使用方式：
    python3 admin_server.py                    # 預設密碼 whalelawyer
    python3 admin_server.py --password 你的密碼  # 自訂密碼
    python3 admin_server.py --port 9090         # 自訂 port

存取方式：
    本地: http://localhost:8088
    Tailscale: http://aimac-mini:8088 或 http://100.97.29.92:8088
"""

import argparse
import base64
import io
import json
import os
import secrets
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

TW_TZ = timezone(timedelta(hours=8))
REPO_ROOT = Path(__file__).parent.parent
DATA_FILE = REPO_ROOT / "data" / "site-data.json"
CONTENT_FILE = REPO_ROOT / "data" / "content.json"
ASSETS_DIR = REPO_ROOT / "assets"

# 預設設定
DEFAULT_PORT = 8088
DEFAULT_PASSWORD = "whalelawyer"

# Session token store
VALID_TOKENS = set()


def load_json(path):
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def git_push(message):
    """Commit all changes and push to GitHub"""
    try:
        env = os.environ.copy()
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "")
        os.chdir(REPO_ROOT)
        subprocess.run(["git", "add", "-A"], check=True, env=env)
        result = subprocess.run(["git", "diff", "--staged", "--quiet"], capture_output=True, env=env)
        if result.returncode != 0:
            subprocess.run(["git", "commit", "-m", message], check=True, env=env)
            subprocess.run(["git", "push"], check=True, env=env)
            return {"success": True, "message": "已成功推送到 GitHub！網站將在 1-2 分鐘內更新。"}
        return {"success": True, "message": "沒有變更需要推送"}
    except subprocess.CalledProcessError as e:
        return {"success": False, "message": f"推送失敗: {e}"}


def parse_multipart(content_type, body):
    """手動解析 multipart/form-data"""
    boundary = None
    for part in content_type.split(";"):
        part = part.strip()
        if part.startswith("boundary="):
            boundary = part[9:].strip('"')
            break

    if not boundary:
        return None, None

    boundary_bytes = f"--{boundary}".encode()
    parts = body.split(boundary_bytes)

    for part in parts:
        if b"Content-Disposition" not in part:
            continue
        header_end = part.find(b"\r\n\r\n")
        if header_end == -1:
            continue
        header = part[:header_end].decode("utf-8", errors="replace")
        file_data = part[header_end + 4:]
        # Remove trailing \r\n--
        if file_data.endswith(b"\r\n"):
            file_data = file_data[:-2]
        if file_data.endswith(b"--"):
            file_data = file_data[:-2]
        if file_data.endswith(b"\r\n"):
            file_data = file_data[:-2]

        if 'name="photo"' in header:
            # Extract filename
            filename = "photo.jpg"
            if 'filename="' in header:
                fn_start = header.index('filename="') + 10
                fn_end = header.index('"', fn_start)
                filename = header[fn_start:fn_end]
            return filename, file_data

    return None, None


class AdminHandler(BaseHTTPRequestHandler):
    password = DEFAULT_PASSWORD

    def check_auth(self):
        """檢查 session token 或顯示登入頁"""
        # Check cookie for session token
        cookies = self.headers.get("Cookie", "")
        for cookie in cookies.split(";"):
            cookie = cookie.strip()
            if cookie.startswith("session="):
                token = cookie[8:]
                if token in VALID_TOKENS:
                    return True
        return False

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/login":
            self.serve_login_page()
        elif parsed.path == "/api/check-auth":
            if self.check_auth():
                self.send_json({"authenticated": True})
            else:
                self.send_json({"authenticated": False})
        elif not self.check_auth():
            self.serve_login_page()
        elif parsed.path == "/" or parsed.path == "/admin":
            self.serve_admin_page()
        elif parsed.path == "/api/data":
            self.send_json(load_json(DATA_FILE))
        elif parsed.path == "/api/content":
            self.send_json(load_json(CONTENT_FILE))
        elif parsed.path.startswith("/assets/"):
            self.serve_static(parsed.path)
        elif parsed.path == "/preview":
            self.serve_preview()
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))

        # 登入不需要 auth
        if parsed.path == "/api/login":
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
            if data.get("password") == self.password:
                token = secrets.token_hex(32)
                VALID_TOKENS.add(token)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Set-Cookie", f"session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=86400")
                resp = json.dumps({"success": True}).encode()
                self.send_header("Content-Length", len(resp))
                self.end_headers()
                self.wfile.write(resp)
            else:
                self.send_json({"success": False, "message": "密碼錯誤"})
            return

        # 其他 API 需要認證
        if not self.check_auth():
            self.send_response(401)
            resp = json.dumps({"error": "未授權"}).encode()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(resp))
            self.end_headers()
            self.wfile.write(resp)
            return

        if parsed.path == "/api/data":
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
            data["lastUpdated"] = datetime.now(TW_TZ).isoformat()
            save_json(DATA_FILE, data)
            self.send_json({"success": True, "message": "資料已儲存"})

        elif parsed.path == "/api/content":
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
            save_json(CONTENT_FILE, data)
            self.update_html_content(data)
            self.send_json({"success": True, "message": "內容已更新"})

        elif parsed.path == "/api/upload-photo":
            self.handle_photo_upload(content_length)

        elif parsed.path == "/api/push":
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8")) if body else {}
            msg = data.get("message", f"update: 更新網站內容 {datetime.now(TW_TZ).strftime('%Y-%m-%d %H:%M')}")
            result = git_push(msg)
            self.send_json(result)

        elif parsed.path == "/api/logout":
            cookies = self.headers.get("Cookie", "")
            for cookie in cookies.split(";"):
                cookie = cookie.strip()
                if cookie.startswith("session="):
                    token = cookie[8:]
                    VALID_TOKENS.discard(token)
            self.send_response(200)
            self.send_header("Set-Cookie", "session=; Path=/; Max-Age=0")
            resp = json.dumps({"success": True}).encode()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(resp))
            self.end_headers()
            self.wfile.write(resp)

        else:
            self.send_error(404)

    def handle_photo_upload(self, content_length):
        """處理照片上傳"""
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self.send_json({"success": False, "message": "格式錯誤"})
            return

        body = self.rfile.read(content_length)
        filename, file_data = parse_multipart(content_type, body)

        if not file_data:
            self.send_json({"success": False, "message": "未收到檔案"})
            return

        ext = Path(filename).suffix.lower() if filename else ".jpg"
        if ext not in (".jpg", ".jpeg", ".png", ".webp"):
            ext = ".jpg"

        dest = ASSETS_DIR / f"profile{ext}"
        # 如果不是 .jpg，同時生成 .jpg 版本
        with open(dest, "wb") as f:
            f.write(file_data)

        # 確保有 profile.jpg
        if ext != ".jpg":
            jpg_dest = ASSETS_DIR / "profile.jpg"
            with open(jpg_dest, "wb") as f:
                f.write(file_data)

        self.send_json({"success": True, "message": f"照片已上傳（{len(file_data) // 1024}KB）"})

    def update_html_content(self, content):
        """更新 index.html 中的可編輯內容"""
        html_path = REPO_ROOT / "index.html"
        if not html_path.exists():
            return

        html = html_path.read_text(encoding="utf-8")

        if "about_text" in content:
            start = html.find('<div class="about-content">')
            end = html.find("</div>", start + 27) if start != -1 else -1
            if start != -1 and end != -1:
                new_block = f'<div class="about-content">\n                <p>\n                    {content["about_text"]}\n                </p>\n            '
                html = html[:start] + new_block + html[end:]

        if "hero_tagline" in content:
            start = html.find('<p class="hero-tagline">')
            end = html.find("</p>", start + 23) if start != -1 else -1
            if start != -1 and end != -1:
                html = html[:start] + f'<p class="hero-tagline">{content["hero_tagline"]}' + html[end:]

        html_path.write_text(html, encoding="utf-8")

    def serve_static(self, path):
        """提供靜態檔案（照片等）"""
        file_path = REPO_ROOT / path.lstrip("/")
        if file_path.exists() and file_path.is_file():
            content = file_path.read_bytes()
            ext = file_path.suffix.lower()
            mime = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".png": "image/png", ".webp": "image/webp",
                ".ico": "image/x-icon", ".svg": "image/svg+xml",
            }.get(ext, "application/octet-stream")
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", len(content))
            self.end_headers()
            self.wfile.write(content)
        else:
            self.send_error(404)

    def serve_preview(self):
        """提供網站預覽（嵌入 iframe）"""
        html = """<!DOCTYPE html><html><head><title>網站預覽</title></head>
        <body style="margin:0"><iframe src="https://whalechao.github.io"
        style="width:100%;height:100vh;border:none"></iframe></body></html>"""
        self.send_html(html)

    def send_json(self, data):
        response = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(response))
        self.end_headers()
        self.wfile.write(response)

    def send_html(self, html):
        encoded = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(encoded))
        self.end_headers()
        self.wfile.write(encoded)

    def serve_login_page(self):
        self.send_html(LOGIN_HTML)

    def serve_admin_page(self):
        self.send_html(ADMIN_HTML)

    def log_message(self, fmt, *args):
        ts = datetime.now(TW_TZ).strftime("%H:%M:%S")
        client = self.client_address[0]
        print(f"[{ts}] {client} {args[0]}")


# ===== Login Page =====
LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>登入 - 網站後台管理</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;600;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Noto Sans TC",system-ui,sans-serif;background:#f1f5f9;display:flex;align-items:center;justify-content:center;min-height:100vh}
.login-card{background:white;padding:48px 40px;border-radius:16px;box-shadow:0 4px 24px rgba(0,0,0,.08);width:100%;max-width:400px;text-align:center}
.login-card h1{font-size:1.4rem;margin-bottom:8px;color:#1e293b}
.login-card p{color:#64748b;font-size:.9rem;margin-bottom:32px}
.form-group{margin-bottom:20px;text-align:left}
.form-group label{display:block;font-size:.85rem;font-weight:600;color:#475569;margin-bottom:6px}
.form-group input{width:100%;padding:12px 16px;border:1px solid #d1d5db;border-radius:8px;font-size:1rem;font-family:inherit}
.form-group input:focus{outline:none;border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.1)}
.btn{width:100%;padding:12px;background:#2563eb;color:white;border:none;border-radius:8px;font-size:1rem;font-weight:600;cursor:pointer;font-family:inherit}
.btn:hover{background:#1d4ed8}
.error{color:#dc2626;font-size:.85rem;margin-top:12px;display:none}
.logo{font-size:2.5rem;margin-bottom:16px}
</style>
</head>
<body>
<div class="login-card">
    <div class="logo">&#9878;</div>
    <h1>網站後台管理</h1>
    <p>喬政翔律師 | 偵理法律事務所</p>
    <form onsubmit="doLogin(event)">
        <div class="form-group">
            <label>管理密碼</label>
            <input type="password" id="password" placeholder="請輸入密碼" autofocus>
        </div>
        <button type="submit" class="btn">登入</button>
        <div class="error" id="errorMsg"></div>
    </form>
</div>
<script>
async function doLogin(e) {
    e.preventDefault();
    const pw = document.getElementById('password').value;
    const errEl = document.getElementById('errorMsg');
    try {
        const resp = await fetch('/api/login', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({password: pw})
        });
        const data = await resp.json();
        if (data.success) {
            window.location.href = '/';
        } else {
            errEl.textContent = data.message || '密碼錯誤';
            errEl.style.display = 'block';
        }
    } catch(err) {
        errEl.textContent = '連線失敗: ' + err.message;
        errEl.style.display = 'block';
    }
}
</script>
</body>
</html>"""

# ===== Admin Page =====
ADMIN_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>網站後台管理 - 喬政翔律師</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Noto Sans TC",system-ui,sans-serif;background:#f1f5f9;color:#1e293b;line-height:1.6}
.header{background:#1e293b;color:white;padding:12px 24px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100}
.header h1{font-size:1.1rem;font-weight:600}
.header .actions{display:flex;gap:8px;flex-wrap:wrap}
.btn{padding:8px 18px;border:none;border-radius:6px;font-size:.85rem;font-weight:600;cursor:pointer;transition:all .2s;font-family:inherit}
.btn-primary{background:#2563eb;color:white}.btn-primary:hover{background:#1d4ed8}
.btn-success{background:#16a34a;color:white}.btn-success:hover{background:#15803d}
.btn-danger{background:#dc2626;color:white}.btn-danger:hover{background:#b91c1c}
.btn-outline{background:transparent;border:1px solid rgba(255,255,255,.3);color:white}.btn-outline:hover{background:rgba(255,255,255,.1)}
.btn-ghost{background:transparent;border:1px solid #cbd5e1;color:#475569}.btn-ghost:hover{background:#f8fafc}
.btn-sm{padding:6px 12px;font-size:.8rem}
.main{max-width:900px;margin:24px auto;padding:0 16px}
.card{background:white;border-radius:12px;padding:24px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.card h2{font-size:1.05rem;margin-bottom:16px;padding-bottom:8px;border-bottom:1px solid #e2e8f0;display:flex;align-items:center;gap:8px}
.card h2 .icon{font-size:1.2rem}
.form-group{margin-bottom:16px}
.form-group label{display:block;font-size:.85rem;font-weight:600;color:#475569;margin-bottom:4px}
.form-group input,.form-group textarea{width:100%;padding:10px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:.9rem;font-family:inherit;transition:border .2s}
.form-group input:focus,.form-group textarea:focus{outline:none;border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.1)}
textarea{resize:vertical;min-height:100px}
.photo-area{display:flex;align-items:center;gap:24px;flex-wrap:wrap}
.photo-preview{width:100px;height:100px;border-radius:50%;object-fit:cover;border:3px solid #e2e8f0}
.photo-placeholder{width:100px;height:100px;border-radius:50%;background:linear-gradient(135deg,#2563eb,#1d4ed8);display:flex;align-items:center;justify-content:center;font-size:2.2rem;color:white;font-weight:700;flex-shrink:0}
.upload-area{flex:1}
.upload-area input[type=file]{margin-bottom:8px}
.news-row{display:flex;gap:8px;align-items:start;margin-bottom:10px;padding:12px;background:#f8fafc;border-radius:8px;flex-wrap:wrap}
.news-row input{flex:1;min-width:120px}
.news-row .btn{flex-shrink:0}
.status{padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:.9rem;display:none;animation:fadeIn .3s}
.status.show{display:block}
.status.success{background:#dcfce7;color:#166534;border:1px solid #bbf7d0}
.status.error{background:#fee2e2;color:#991b1b;border:1px solid #fecaca}
.status.info{background:#dbeafe;color:#1e40af;border:1px solid #bfdbfe}
.stats-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
@keyframes fadeIn{from{opacity:0;transform:translateY(-4px)}to{opacity:1;transform:translateY(0)}}
@media(max-width:640px){
    .header{flex-direction:column;gap:8px;text-align:center}
    .stats-grid{grid-template-columns:1fr}
    .news-row{flex-direction:column}
    .news-row input{width:100%}
    .photo-area{flex-direction:column;text-align:center}
}
</style>
</head>
<body>

<div class="header">
    <h1>&#9878; 網站後台管理</h1>
    <div class="actions">
        <button class="btn btn-outline" onclick="loadAll()">&#8635; 重新載入</button>
        <button class="btn btn-primary" onclick="saveAll()">&#128190; 儲存</button>
        <button class="btn btn-success" onclick="pushToGitHub()">&#128640; 推送到 GitHub</button>
        <a href="https://whalechao.github.io" target="_blank" class="btn btn-outline">&#127760; 檢視網站</a>
        <button class="btn btn-outline" onclick="logout()" style="opacity:.7">登出</button>
    </div>
</div>

<div class="main">
    <div id="statusMsg" class="status"></div>

    <!-- 照片管理 -->
    <div class="card">
        <h2><span class="icon">&#128247;</span> 個人照片</h2>
        <div class="photo-area">
            <div id="photoPreview">
                <div class="photo-placeholder">喬</div>
            </div>
            <div class="upload-area">
                <input type="file" id="photoInput" accept="image/jpeg,image/png,image/webp" onchange="uploadPhoto()">
                <p style="font-size:.8rem;color:#94a3b8;margin-top:4px">支援 JPG、PNG、WebP 格式</p>
            </div>
        </div>
    </div>

    <!-- 個人介紹 -->
    <div class="card">
        <h2><span class="icon">&#128100;</span> 個人介紹</h2>
        <div class="form-group">
            <label>一句話簡介</label>
            <input type="text" id="heroTagline" value="">
        </div>
        <div class="form-group">
            <label>關於我（詳細介紹）</label>
            <textarea id="aboutText" rows="5"></textarea>
        </div>
    </div>

    <!-- 數據統計 -->
    <div class="card">
        <h2><span class="icon">&#128202;</span> 服務實績數據</h2>
        <div class="stats-grid">
            <div class="form-group">
                <label>累計案件數</label>
                <input type="number" id="statTotalCases">
            </div>
            <div class="form-group">
                <label>法律扶助案件數</label>
                <input type="number" id="statLegalAid">
            </div>
            <div class="form-group">
                <label>執業年數</label>
                <input type="number" id="statYears">
            </div>
            <div class="form-group">
                <label>發表文章數</label>
                <input type="number" id="statArticles">
            </div>
        </div>
    </div>

    <!-- 新聞管理 -->
    <div class="card">
        <h2><span class="icon">&#128240;</span> 媒體報導</h2>
        <div id="newsContainer"></div>
        <button class="btn btn-ghost btn-sm" onclick="addNewsRow()" style="margin-top:8px">+ 新增報導</button>
    </div>

    <!-- 文章管理 -->
    <div class="card">
        <h2><span class="icon">&#128221;</span> 發表文章</h2>
        <div id="articlesContainer"></div>
        <button class="btn btn-ghost btn-sm" onclick="addArticleRow()" style="margin-top:8px">+ 新增文章</button>
    </div>
</div>

<script>
let siteData = {};
let contentData = {};

async function loadAll() {
    try {
        const [dataResp, contentResp] = await Promise.all([
            fetch('/api/data'),
            fetch('/api/content')
        ]);

        if (dataResp.status === 401) { window.location.href = '/login'; return; }

        siteData = await dataResp.json();
        contentData = await contentResp.json();
        populateForm(siteData, contentData);
        showStatus('資料已載入', 'info', 2000);
    } catch(e) {
        showStatus('載入失敗: ' + e.message, 'error');
    }
}

function populateForm(data, content) {
    const s = data.stats || {};
    document.getElementById('statTotalCases').value = s.totalCases || 0;
    document.getElementById('statLegalAid').value = s.legalAidCases || 0;
    document.getElementById('statYears').value = s.yearsOfPractice || 0;
    document.getElementById('statArticles').value = s.articles || 0;

    document.getElementById('heroTagline').value = content.hero_tagline || '扎根花蓮，致力於公義的法律實踐';
    document.getElementById('aboutText').value = content.about_text || '';

    const nc = document.getElementById('newsContainer');
    nc.innerHTML = '';
    (data.news || []).forEach(n => addNewsRow(n));

    const ac = document.getElementById('articlesContainer');
    ac.innerHTML = '';
    (data.articles || []).forEach(a => addArticleRow(a));

    // Try load photo
    const img = new Image();
    img.onload = () => {
        document.getElementById('photoPreview').innerHTML =
            '<img class="photo-preview" src="/assets/profile.jpg?t=' + Date.now() + '" alt="Profile">';
    };
    img.src = '/assets/profile.jpg?t=' + Date.now();
}

function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

function addNewsRow(item = {}) {
    const nc = document.getElementById('newsContainer');
    const div = document.createElement('div');
    div.className = 'news-row';
    div.innerHTML =
        '<input type="text" placeholder="標題" value="' + esc(item.title) + '">' +
        '<input type="text" placeholder="連結 URL" value="' + esc(item.url) + '">' +
        '<input type="text" placeholder="來源" value="' + esc(item.source) + '" style="max-width:120px">' +
        '<input type="text" placeholder="日期" value="' + esc(item.date) + '" style="max-width:100px">' +
        '<button class="btn btn-danger btn-sm" onclick="this.parentElement.remove()">&#10005;</button>';
    nc.appendChild(div);
}

function addArticleRow(item = {}) {
    const ac = document.getElementById('articlesContainer');
    const div = document.createElement('div');
    div.className = 'news-row';
    div.innerHTML =
        '<input type="text" placeholder="標題" value="' + esc(item.title) + '">' +
        '<input type="text" placeholder="連結 URL" value="' + esc(item.url) + '">' +
        '<input type="text" placeholder="日期" value="' + esc(item.date) + '" style="max-width:100px">' +
        '<button class="btn btn-danger btn-sm" onclick="this.parentElement.remove()">&#10005;</button>';
    ac.appendChild(div);
}

async function saveAll() {
    siteData.stats = {
        totalCases: parseInt(document.getElementById('statTotalCases').value) || 0,
        legalAidCases: parseInt(document.getElementById('statLegalAid').value) || 0,
        yearsOfPractice: parseInt(document.getElementById('statYears').value) || 0,
        articles: parseInt(document.getElementById('statArticles').value) || 0
    };

    siteData.news = [];
    document.querySelectorAll('#newsContainer .news-row').forEach(row => {
        const inputs = row.querySelectorAll('input');
        if (inputs[0].value.trim()) {
            siteData.news.push({
                title: inputs[0].value.trim(),
                url: inputs[1].value.trim(),
                source: inputs[2].value.trim(),
                date: inputs[3].value.trim()
            });
        }
    });

    siteData.articles = [];
    document.querySelectorAll('#articlesContainer .news-row').forEach(row => {
        const inputs = row.querySelectorAll('input');
        if (inputs[0].value.trim()) {
            siteData.articles.push({
                title: inputs[0].value.trim(),
                url: inputs[1].value.trim(),
                date: inputs[2].value.trim()
            });
        }
    });

    try {
        const [r1, r2] = await Promise.all([
            fetch('/api/data', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(siteData)
            }),
            fetch('/api/content', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    hero_tagline: document.getElementById('heroTagline').value,
                    about_text: document.getElementById('aboutText').value
                })
            })
        ]);
        showStatus('所有變更已儲存！記得按「推送到 GitHub」讓網站更新。', 'success');
    } catch(e) {
        showStatus('儲存失敗: ' + e.message, 'error');
    }
}

async function pushToGitHub() {
    showStatus('正在推送到 GitHub...', 'info');
    try {
        const resp = await fetch('/api/push', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({})
        });
        const result = await resp.json();
        showStatus(result.message, result.success ? 'success' : 'error');
    } catch(e) {
        showStatus('推送失敗: ' + e.message, 'error');
    }
}

async function uploadPhoto() {
    const input = document.getElementById('photoInput');
    if (!input.files.length) return;

    const file = input.files[0];
    if (file.size > 10 * 1024 * 1024) {
        showStatus('檔案太大（上限 10MB）', 'error');
        return;
    }

    showStatus('正在上傳照片...', 'info');
    const formData = new FormData();
    formData.append('photo', file);

    try {
        const resp = await fetch('/api/upload-photo', { method: 'POST', body: formData });
        const result = await resp.json();
        if (result.success) {
            document.getElementById('photoPreview').innerHTML =
                '<img class="photo-preview" src="/assets/profile.jpg?t=' + Date.now() + '" alt="Profile">';
            showStatus(result.message + '（記得推送到 GitHub）', 'success');
        } else {
            showStatus(result.message, 'error');
        }
    } catch(e) {
        showStatus('上傳失敗: ' + e.message, 'error');
    }
}

async function logout() {
    await fetch('/api/logout', { method: 'POST' });
    window.location.href = '/login';
}

function showStatus(msg, type, autoHide) {
    const el = document.getElementById('statusMsg');
    el.textContent = msg;
    el.className = 'status show ' + type;
    if (autoHide || type === 'success') {
        setTimeout(() => { el.className = 'status'; }, autoHide || 5000);
    }
}

loadAll();
</script>
</body>
</html>"""


def get_tailscale_ip():
    """嘗試取得 Tailscale IP"""
    try:
        result = subprocess.run(
            ["/Applications/Tailscale.app/Contents/MacOS/tailscale", "ip", "-4"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="網站後台管理伺服器")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"伺服器 port（預設 {DEFAULT_PORT}）")
    parser.add_argument("--password", type=str, default=DEFAULT_PASSWORD, help="管理密碼")
    args = parser.parse_args()

    AdminHandler.password = args.password

    ts_ip = get_tailscale_ip()

    print("=" * 50)
    print("  喬政翔律師 - 網站後台管理伺服器")
    print("=" * 50)
    print(f"  本地存取:     http://localhost:{args.port}")
    if ts_ip:
        print(f"  Tailscale:    http://{ts_ip}:{args.port}")
        print(f"  Tailscale:    http://aimac-mini:{args.port}")
    print(f"  管理密碼:     {args.password}")
    print(f"  網站目錄:     {REPO_ROOT}")
    print("=" * 50)
    print("  按 Ctrl+C 停止伺服器\n")

    server = HTTPServer(("0.0.0.0", args.port), AdminHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n伺服器已停止")
        server.server_close()
