#!/usr/bin/env python3
"""
喬政翔律師個人網站 - 本地後台管理伺服器
用於編輯網站文字、照片，並推送到 GitHub

使用方式：
    python3 admin_server.py
    然後瀏覽器開啟 http://localhost:8088
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import cgi

TW_TZ = timezone(timedelta(hours=8))
REPO_ROOT = Path(__file__).parent.parent
DATA_FILE = REPO_ROOT / "data" / "site-data.json"
CONTENT_FILE = REPO_ROOT / "data" / "content.json"  # 可編輯的靜態內容
ASSETS_DIR = REPO_ROOT / "assets"
ADMIN_PORT = 8088


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
        os.chdir(REPO_ROOT)
        subprocess.run(["git", "add", "-A"], check=True)
        result = subprocess.run(["git", "diff", "--staged", "--quiet"], capture_output=True)
        if result.returncode != 0:
            subprocess.run(["git", "commit", "-m", message], check=True)
            subprocess.run(["git", "push"], check=True)
            return {"success": True, "message": "已成功推送到 GitHub"}
        return {"success": True, "message": "沒有變更需要推送"}
    except subprocess.CalledProcessError as e:
        return {"success": False, "message": f"推送失敗: {e}"}


class AdminHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/" or parsed.path == "/admin":
            self.serve_admin_page()
        elif parsed.path == "/api/data":
            self.send_json(load_json(DATA_FILE))
        elif parsed.path == "/api/content":
            self.send_json(load_json(CONTENT_FILE))
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        content_length = int(self.headers.get("Content-Length", 0))

        if parsed.path == "/api/data":
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
            data["lastUpdated"] = datetime.now(TW_TZ).isoformat()
            save_json(DATA_FILE, data)
            self.send_json({"success": True})

        elif parsed.path == "/api/content":
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
            save_json(CONTENT_FILE, data)
            # 同時更新 index.html 中的文字
            self.update_html_content(data)
            self.send_json({"success": True})

        elif parsed.path == "/api/upload-photo":
            self.handle_photo_upload()

        elif parsed.path == "/api/push":
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8")) if body else {}
            msg = data.get("message", f"update: 更新網站內容 {datetime.now(TW_TZ).strftime('%Y-%m-%d %H:%M')}")
            result = git_push(msg)
            self.send_json(result)

        else:
            self.send_error(404)

    def handle_photo_upload(self):
        """處理照片上傳"""
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self.send_json({"success": False, "message": "Invalid content type"})
            return

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type}
        )

        if "photo" not in form:
            self.send_json({"success": False, "message": "No photo file"})
            return

        file_item = form["photo"]
        if file_item.filename:
            # 保存為 profile.jpg
            ext = Path(file_item.filename).suffix or ".jpg"
            dest = ASSETS_DIR / f"profile{ext}"
            with open(dest, "wb") as f:
                f.write(file_item.file.read())
            self.send_json({"success": True, "message": f"照片已保存: {dest.name}"})
        else:
            self.send_json({"success": False, "message": "Empty file"})

    def update_html_content(self, content):
        """更新 index.html 中的可編輯內容"""
        html_path = REPO_ROOT / "index.html"
        if not html_path.exists():
            return

        html = html_path.read_text(encoding="utf-8")

        replacements = {
            "about_text": (
                '<div class="about-content">',
                "</div>",
                lambda v: f'<div class="about-content">\n                <p>\n                    {v}\n                </p>\n            '
            ),
            "hero_tagline": (
                '<p class="hero-tagline">',
                "</p>",
                lambda v: f'<p class="hero-tagline">{v}'
            ),
        }

        for key, (start_tag, end_tag, formatter) in replacements.items():
            if key in content:
                start_idx = html.find(start_tag)
                if start_idx == -1:
                    continue
                end_idx = html.find(end_tag, start_idx + len(start_tag))
                if end_idx == -1:
                    continue
                html = html[:start_idx] + formatter(content[key]) + html[end_idx:]

        html_path.write_text(html, encoding="utf-8")

    def send_json(self, data):
        response = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(response))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(response)

    def serve_admin_page(self):
        html = ADMIN_HTML.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(html))
        self.end_headers()
        self.wfile.write(html)

    def log_message(self, format, *args):
        print(f"[Admin] {args[0]}")


ADMIN_HTML = r"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>網站後台管理 - 喬政翔律師</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"Noto Sans TC",system-ui,sans-serif;background:#f1f5f9;color:#1e293b;line-height:1.6}
.header{background:#1e293b;color:white;padding:16px 24px;display:flex;align-items:center;justify-content:space-between}
.header h1{font-size:1.2rem;font-weight:600}
.header .actions{display:flex;gap:8px}
.btn{padding:8px 20px;border:none;border-radius:6px;font-size:0.9rem;font-weight:600;cursor:pointer;transition:all .2s}
.btn-primary{background:#2563eb;color:white}.btn-primary:hover{background:#1d4ed8}
.btn-success{background:#16a34a;color:white}.btn-success:hover{background:#15803d}
.btn-danger{background:#dc2626;color:white}.btn-danger:hover{background:#b91c1c}
.btn-outline{background:transparent;border:1px solid #cbd5e1;color:#475569}.btn-outline:hover{background:#f8fafc}
.main{max-width:900px;margin:24px auto;padding:0 16px}
.card{background:white;border-radius:12px;padding:24px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.card h2{font-size:1.1rem;margin-bottom:16px;padding-bottom:8px;border-bottom:1px solid #e2e8f0}
.form-group{margin-bottom:16px}
.form-group label{display:block;font-size:.85rem;font-weight:600;color:#475569;margin-bottom:4px}
.form-group input,.form-group textarea{width:100%;padding:10px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:.9rem;font-family:inherit;transition:border .2s}
.form-group input:focus,.form-group textarea:focus{outline:none;border-color:#2563eb;box-shadow:0 0 0 3px rgba(37,99,235,.1)}
textarea{resize:vertical;min-height:100px}
.photo-preview{width:120px;height:120px;border-radius:50%;object-fit:cover;border:3px solid #e2e8f0;margin:8px 0}
.photo-placeholder{width:120px;height:120px;border-radius:50%;background:#dbeafe;display:flex;align-items:center;justify-content:center;font-size:2.5rem;color:#2563eb;margin:8px 0}
.news-row{display:flex;gap:8px;align-items:start;margin-bottom:12px;padding:12px;background:#f8fafc;border-radius:8px}
.news-row input{flex:1}
.news-row .btn{flex-shrink:0;padding:8px 12px}
.status{padding:12px 16px;border-radius:8px;margin-top:16px;font-size:.9rem;display:none}
.status.success{display:block;background:#dcfce7;color:#166534}
.status.error{display:block;background:#fee2e2;color:#991b1b}
.status.info{display:block;background:#dbeafe;color:#1e40af}
.stats-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
</style>
</head>
<body>

<div class="header">
    <h1>網站後台管理</h1>
    <div class="actions">
        <button class="btn btn-outline" onclick="loadAll()">重新載入</button>
        <button class="btn btn-primary" onclick="saveAll()">儲存變更</button>
        <button class="btn btn-success" onclick="pushToGitHub()">推送到 GitHub</button>
    </div>
</div>

<div class="main">
    <!-- 狀態訊息 -->
    <div id="statusMsg" class="status"></div>

    <!-- 照片管理 -->
    <div class="card">
        <h2>個人照片</h2>
        <div id="photoPreview">
            <div class="photo-placeholder">喬</div>
        </div>
        <input type="file" id="photoInput" accept="image/*" onchange="uploadPhoto()">
    </div>

    <!-- 個人介紹 -->
    <div class="card">
        <h2>個人介紹</h2>
        <div class="form-group">
            <label>一句話簡介</label>
            <input type="text" id="heroTagline" value="扎根花蓮，致力於公義的法律實踐">
        </div>
        <div class="form-group">
            <label>關於我（詳細介紹）</label>
            <textarea id="aboutText" rows="5">喬政翔律師，偵理法律事務所主持律師，執業於花蓮。長期投入司法改革運動，並積極參與法律扶助工作，為弱勢族群提供法律服務。專長涵蓋刑事辯護、民事訴訟、行政爭訟及消費者債務清理等領域，以嚴謹的法律分析與溫暖的人文關懷，為每一位當事人爭取最大的權益保障。</textarea>
        </div>
    </div>

    <!-- 數據統計 -->
    <div class="card">
        <h2>服務實績數據</h2>
        <div class="stats-grid">
            <div class="form-group">
                <label>累計案件數</label>
                <input type="number" id="statTotalCases" value="850">
            </div>
            <div class="form-group">
                <label>法律扶助案件數</label>
                <input type="number" id="statLegalAid" value="230">
            </div>
            <div class="form-group">
                <label>執業年數</label>
                <input type="number" id="statYears" value="10">
            </div>
            <div class="form-group">
                <label>發表文章數</label>
                <input type="number" id="statArticles" value="15">
            </div>
        </div>
    </div>

    <!-- 新聞管理 -->
    <div class="card">
        <h2>媒體報導</h2>
        <div id="newsContainer"></div>
        <button class="btn btn-outline" onclick="addNewsRow()" style="margin-top:8px">+ 新增報導</button>
    </div>

    <!-- 文章管理 -->
    <div class="card">
        <h2>發表文章</h2>
        <div id="articlesContainer"></div>
        <button class="btn btn-outline" onclick="addArticleRow()" style="margin-top:8px">+ 新增文章</button>
    </div>
</div>

<script>
let siteData = {};

async function loadAll() {
    try {
        const resp = await fetch('/api/data');
        siteData = await resp.json();
        populateForm(siteData);
        showStatus('資料已載入', 'info');
    } catch(e) {
        showStatus('載入失敗: ' + e.message, 'error');
    }
}

function populateForm(data) {
    // Stats
    const s = data.stats || {};
    document.getElementById('statTotalCases').value = s.totalCases || 0;
    document.getElementById('statLegalAid').value = s.legalAidCases || 0;
    document.getElementById('statYears').value = s.yearsOfPractice || 0;
    document.getElementById('statArticles').value = s.articles || 0;

    // News
    const nc = document.getElementById('newsContainer');
    nc.innerHTML = '';
    (data.news || []).forEach(n => addNewsRow(n));

    // Articles
    const ac = document.getElementById('articlesContainer');
    ac.innerHTML = '';
    (data.articles || []).forEach(a => addArticleRow(a));
}

function addNewsRow(item = {}) {
    const nc = document.getElementById('newsContainer');
    const div = document.createElement('div');
    div.className = 'news-row';
    div.innerHTML = `
        <input type="text" placeholder="標題" value="${item.title || ''}">
        <input type="text" placeholder="連結" value="${item.url || ''}">
        <input type="text" placeholder="來源" value="${item.source || ''}" style="max-width:120px">
        <input type="text" placeholder="日期" value="${item.date || ''}" style="max-width:100px">
        <button class="btn btn-danger" onclick="this.parentElement.remove()">刪</button>
    `;
    nc.appendChild(div);
}

function addArticleRow(item = {}) {
    const ac = document.getElementById('articlesContainer');
    const div = document.createElement('div');
    div.className = 'news-row';
    div.innerHTML = `
        <input type="text" placeholder="標題" value="${item.title || ''}">
        <input type="text" placeholder="連結" value="${item.url || ''}">
        <input type="text" placeholder="日期" value="${item.date || ''}" style="max-width:100px">
        <button class="btn btn-danger" onclick="this.parentElement.remove()">刪</button>
    `;
    ac.appendChild(div);
}

async function saveAll() {
    // Collect stats
    siteData.stats = {
        totalCases: parseInt(document.getElementById('statTotalCases').value) || 0,
        legalAidCases: parseInt(document.getElementById('statLegalAid').value) || 0,
        yearsOfPractice: parseInt(document.getElementById('statYears').value) || 0,
        articles: parseInt(document.getElementById('statArticles').value) || 0
    };

    // Collect news
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

    // Collect articles
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

    // Save data
    try {
        await fetch('/api/data', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(siteData)
        });

        // Save content (about text, tagline)
        await fetch('/api/content', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                hero_tagline: document.getElementById('heroTagline').value,
                about_text: document.getElementById('aboutText').value
            })
        });

        showStatus('變更已儲存', 'success');
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

    const formData = new FormData();
    formData.append('photo', input.files[0]);

    try {
        const resp = await fetch('/api/upload-photo', {
            method: 'POST',
            body: formData
        });
        const result = await resp.json();
        if (result.success) {
            // Update preview
            const preview = document.getElementById('photoPreview');
            preview.innerHTML = `<img class="photo-preview" src="/assets/profile.jpg?t=${Date.now()}" alt="Profile">`;
            showStatus(result.message, 'success');
        } else {
            showStatus(result.message, 'error');
        }
    } catch(e) {
        showStatus('上傳失敗: ' + e.message, 'error');
    }
}

function showStatus(msg, type) {
    const el = document.getElementById('statusMsg');
    el.textContent = msg;
    el.className = 'status ' + type;
    if (type !== 'info') {
        setTimeout(() => { el.style.display = 'none'; }, 5000);
    }
}

// Load on page ready
loadAll();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print(f"Admin server starting on http://localhost:{ADMIN_PORT}")
    print(f"Repo root: {REPO_ROOT}")
    print("Press Ctrl+C to stop\n")

    server = HTTPServer(("0.0.0.0", ADMIN_PORT), AdminHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nAdmin server stopped")
        server.server_close()
