#!/usr/bin/env python3
"""
判決書爬蟲 — 從司法院裁判書查詢系統搜尋喬政翔律師的公開判決
抓取案由分類統計，更新 site-data.json

SSL 修正：Python 3.14 + OpenSSL 3.x 對 judicial.gov.tw 的 SKI 檢查過嚴，
         使用 relaxed SSL context 解決。

使用方式：
    python3 crawl_judgments.py              # 搜尋並更新
    python3 crawl_judgments.py --push       # 搜尋、更新、並推送到 GitHub
"""

import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TW_TZ = timezone(timedelta(hours=8))
REPO_ROOT = Path(__file__).parent.parent
DATA_FILE = REPO_ROOT / "data" / "site-data.json"
LAWYER_NAME = "喬政翔"

FJUD_BASE = "https://judgment.judicial.gov.tw/FJUD"


class RelaxedSSLAdapter(HTTPAdapter):
    """HTTPAdapter that relaxes X.509 strict mode for judicial.gov.tw"""
    def init_poolmanager(self, *args, **kwargs):
        try:
            import certifi
            ca_bundle = certifi.where()
        except ImportError:
            ca_bundle = None
        ctx = create_urllib3_context()
        if ca_bundle:
            ctx.load_verify_locations(ca_bundle)
        ctx.verify_flags &= ~ssl.VERIFY_X509_STRICT
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)


def create_session():
    """建立帶 SSL 修正的 session"""
    session = requests.Session()
    adapter = RelaxedSSLAdapter()
    session.mount("https://judgment.judicial.gov.tw", adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    })
    return session


def search_fjud(session):
    """
    搜尋司法院裁判書查詢系統
    1. GET 搜尋頁面取得 ViewState
    2. POST 搜尋
    3. 解析結果頁面中的分類統計
    """
    print(f"正在搜尋司法院裁判書（{LAWYER_NAME}）...")

    # Step 1: 取得搜尋頁面
    r0 = session.get(f"{FJUD_BASE}/default.aspx", timeout=15)
    if r0.status_code != 200:
        print(f"  搜尋頁面載入失敗: {r0.status_code}")
        return None

    # 提取 ASP.NET form fields
    vs = re.search(r'id="__VIEWSTATE"\s+value="([^"]*)"', r0.text)
    vsg = re.search(r'id="__VIEWSTATEGENERATOR"\s+value="([^"]*)"', r0.text)
    ev = re.search(r'id="__EVENTVALIDATION"\s+value="([^"]*)"', r0.text)

    # Step 2: POST 搜尋
    post_data = {
        "__VIEWSTATE": vs.group(1) if vs else "",
        "__VIEWSTATEGENERATOR": vsg.group(1) if vsg else "",
        "__EVENTVALIDATION": ev.group(1) if ev else "",
        "txtKW": LAWYER_NAME,
        "judtype": "JUDBOOK",
        "whosType": "0",
        "btnSimpleQry": "送出查詢",
    }

    r1 = session.post(
        f"{FJUD_BASE}/default.aspx",
        data=post_data,
        timeout=30,
        allow_redirects=True,
    )
    print(f"  搜尋結果: {r1.status_code}")

    # Step 3: 取得結果頁
    r2 = session.get(f"{FJUD_BASE}/qryresult.aspx", timeout=15)

    # 解析分類統計（從側邊欄 panel）
    result = {
        "total": 0,
        "categories": {},
        "courts": {},
        "cases": [],
    }

    # 總筆數
    total_match = re.search(r"共\s*(\d+)\s*筆", r2.text)
    if total_match:
        result["total"] = int(total_match.group(1))
        print(f"  找到 {result['total']} 筆判決")

    # 案件類別（民事/刑事/行政/憲法）
    cat_pattern = r'<a[^>]*>(.*?)<span[^>]*class="badge"[^>]*>(\d+)</span>'
    for match in re.finditer(cat_pattern, r2.text, re.DOTALL):
        name = re.sub(r"<[^>]+>", "", match.group(1)).strip().lstrip("»").strip()
        count = int(match.group(2))
        if name in ("民事", "刑事", "行政", "憲法"):
            result["categories"][name] = count
        elif not any(c in name for c in ["民國", "年"]):
            # 法院名稱
            result["courts"][name] = count

    print(f"  類別: {result['categories']}")
    print(f"  法院: {len(result['courts'])} 個")

    # 從結果頁面取得案由（如果有 iframe）
    # 嘗試直接取得 iframe 的內容
    iframe_match = re.search(r'<iframe[^>]*id="iframe-data"[^>]*src="([^"]*)"', r2.text)
    if iframe_match:
        iframe_src = iframe_match.group(1)
        if not iframe_src.startswith("http"):
            iframe_src = f"{FJUD_BASE}/{iframe_src}"

        # 抓取多頁案由
        all_reasons = []
        pages_to_fetch = min(24, (result["total"] // 20) + 1)

        for page in range(1, pages_to_fetch + 1):
            try:
                page_url = re.sub(r'page=\d+', f'page={page}', iframe_src)
                if 'page=' not in page_url:
                    sep = '&' if '?' in page_url else '?'
                    page_url += f'{sep}page={page}'

                rp = session.get(page_url, timeout=15)
                if rp.status_code == 200:
                    # 提取案由（最後一個 td）
                    rows = re.findall(r'<tr[^>]*>(.*?)</tr>', rp.text, re.DOTALL)
                    for row in rows:
                        tds = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
                        if len(tds) >= 3:
                            reason = re.sub(r'<[^>]+>', '', tds[-1]).strip()
                            if reason and reason != "裁判案由" and len(reason) < 40:
                                all_reasons.append(reason)

                    sys.stdout.write(f"\r  抓取案由: 第 {page}/{pages_to_fetch} 頁 ({len(all_reasons)} 筆)")
                    sys.stdout.flush()
                    time.sleep(0.5)  # 避免請求過快
            except Exception as e:
                print(f"\n  第 {page} 頁失敗: {e}")
                continue

        print()  # 換行

        if all_reasons:
            # 過濾非案由項目
            skip_reasons = {"訴訟救助", "聲請復權", ""}
            filtered = [r for r in all_reasons if r not in skip_reasons]

            counter = Counter(filtered)

            # 為每個案由判斷分類
            criminal_keywords = ["罪", "毒品", "竊盜", "詐欺", "傷害", "殺人", "妨害", "恐嚇",
                               "侵占", "偽造", "洗錢", "公共危險", "過失", "國民法官", "假釋",
                               "強盜", "搶奪", "性自主", "酒駕"]
            admin_keywords = ["行政", "訴願", "裁決", "國家賠償", "公民投票"]

            def classify(reason):
                for kw in criminal_keywords:
                    if kw in reason:
                        return "刑事"
                for kw in admin_keywords:
                    if kw in reason:
                        return "行政"
                return "民事"

            result["cases"] = [
                {"type": t, "count": c, "category": classify(t)}
                for t, c in counter.most_common()
            ]

    return result


def update_site_data(fjud_result):
    """更新 site-data.json"""
    data = {}
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

    if fjud_result:
        data["lastUpdated"] = datetime.now(TW_TZ).isoformat()

        # 更新統計
        data["stats"] = data.get("stats", {})
        data["stats"]["totalCases"] = fjud_result["total"]

        # 更新分類
        data["caseCategories"] = fjud_result["categories"]

        # 更新案由
        data["cases"] = fjud_result["cases"]

        # 更新法院
        data["courts"] = fjud_result["courts"]

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"\n已更新 {DATA_FILE}")
    if fjud_result:
        print(f"總判決數: {fjud_result['total']}")
        print(f"類別: {fjud_result['categories']}")
        print(f"案由類型: {len(fjud_result['cases'])} 種")
        if fjud_result["cases"]:
            print("\n前 15 大案由:")
            for c in fjud_result["cases"][:15]:
                print(f"  [{c['category']}] {c['type']}: {c['count']}")


def git_push():
    """推送到 GitHub"""
    try:
        env = os.environ.copy()
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "")
        os.chdir(REPO_ROOT)
        subprocess.run(["git", "add", "data/site-data.json"], check=True, env=env)
        result = subprocess.run(["git", "diff", "--staged", "--quiet"], capture_output=True, env=env)
        if result.returncode != 0:
            now = datetime.now(TW_TZ).strftime("%Y-%m-%d %H:%M")
            subprocess.run(
                ["git", "commit", "-m", f"data: update judgment cases {now}"],
                check=True, env=env
            )
            subprocess.run(["git", "push"], check=True, env=env)
            print("已推送到 GitHub")
        else:
            print("沒有變更需要推送")
    except subprocess.CalledProcessError as e:
        print(f"推送失敗: {e}")


def main():
    parser = argparse.ArgumentParser(description="判決書爬蟲")
    parser.add_argument("--push", action="store_true", help="更新後推送到 GitHub")
    args = parser.parse_args()

    print("=" * 50)
    print(f"  判決書爬蟲 — {LAWYER_NAME} 律師公開判決統計")
    print("=" * 50)

    session = create_session()
    result = search_fjud(session)

    if result and result["total"] > 0:
        update_site_data(result)
    else:
        print("未能取得判決資料")

    if args.push:
        git_push()

    print("\n完成！")


if __name__ == "__main__":
    main()
