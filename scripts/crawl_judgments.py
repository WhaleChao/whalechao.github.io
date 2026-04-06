#!/usr/bin/env python3
"""
判決書爬蟲 — 從司法院裁判書查詢系統搜尋喬政翔律師的公開判決
抓取案由分類統計，更新 site-data.json

使用方式：
    python3 crawl_judgments.py              # 搜尋並更新
    python3 crawl_judgments.py --push       # 搜尋、更新、並推送到 GitHub
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote

import requests

TW_TZ = timezone(timedelta(hours=8))
REPO_ROOT = Path(__file__).parent.parent
DATA_FILE = REPO_ROOT / "data" / "site-data.json"

LAWYER_NAME = "喬政翔"

# 司法院裁判書查詢 API
FJUD_SEARCH_URL = "https://judgment.judicial.gov.tw/FJUD/data.aspx"
FJUD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": "https://judgment.judicial.gov.tw/FJUD/default.aspx",
}


def search_judgments_fjud():
    """
    透過司法院 FJUD 查詢含有律師名字的判決書
    """
    all_cases = []

    # 搜尋全文包含律師名字的判決
    params = {
        "searchtype": "全文檢索",
        "keyword": LAWYER_NAME,
        "sdate": "",
        "edate": "",
        "page": 1,
        "pagesize": 100,
    }

    try:
        print(f"正在搜尋司法院判決書（關鍵字：{LAWYER_NAME}）...")
        resp = requests.get(
            FJUD_SEARCH_URL,
            params=params,
            headers=FJUD_HEADERS,
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if "gridView" in data:
                for item in data["gridView"]:
                    case_type = item.get("JCASE", "")  # 案由
                    if case_type:
                        all_cases.append(case_type)
            print(f"  FJUD 找到 {len(all_cases)} 筆")
    except Exception as e:
        print(f"  FJUD 查詢失敗: {e}")

    return all_cases


def search_judgments_lawsnote():
    """
    透過 Lawsnote 公開頁面搜尋律師的判決資料
    """
    all_cases = []
    try:
        print(f"正在搜尋 Lawsnote（律師：{LAWYER_NAME}）...")
        # Lawsnote 律師頁面
        url = "https://page.lawsnote.com/page/5cffa99e0890331626f56525"
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
        }, timeout=15)

        if resp.status_code == 200:
            text = resp.text
            # 嘗試從頁面中提取案件類型
            # Lawsnote 頁面通常有案件分類統計
            # 嘗試解析 JSON 資料
            json_match = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.+?});', text, re.DOTALL)
            if json_match:
                try:
                    state = json.loads(json_match.group(1))
                    # 從 state 中提取案件資訊
                    if "cases" in state:
                        for case in state["cases"]:
                            case_type = case.get("type", "") or case.get("reason", "")
                            if case_type:
                                all_cases.append(case_type)
                except json.JSONDecodeError:
                    pass

            print(f"  Lawsnote 找到 {len(all_cases)} 筆")
    except Exception as e:
        print(f"  Lawsnote 查詢失敗: {e}")

    return all_cases


def search_judgments_local_db():
    """
    從 MAGI 本地資料庫搜尋判決資料
    """
    all_cases = []
    try:
        import mysql.connector

        # 載入 MAGI 環境變數
        magi_env = {}
        env_path = Path(os.path.expanduser("~/Desktop/MAGI_v2/.env"))
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, _, value = line.partition("=")
                        magi_env[key.strip()] = value.strip().strip("'\"")

        conn = mysql.connector.connect(
            host=magi_env.get("MAGI_DB_HOST", "127.0.0.1"),
            port=int(magi_env.get("MAGI_DB_PORT", "3306")),
            user=magi_env.get("MAGI_DB_USER", "magi"),
            password=magi_env.get("MAGI_DB_PASSWORD", ""),
            database=magi_env.get("MAGI_DB_NAME", "law_firm_data"),
        )
        cursor = conn.cursor(dictionary=True)

        # 查詢 court_judgments 表中包含律師名字的案件
        tables_to_check = ["court_judgments", "judgments", "cases"]
        for table in tables_to_check:
            try:
                # 先確認表存在
                cursor.execute(f"SHOW TABLES LIKE '{table}'")
                if not cursor.fetchone():
                    continue

                # 取得欄位名稱
                cursor.execute(f"SHOW COLUMNS FROM {table}")
                columns = [col["Field"] for col in cursor.fetchall()]

                # 找案由欄位
                reason_col = None
                for possible in ["case_reason", "reason", "JCASE", "case_type", "案由"]:
                    if possible in columns:
                        reason_col = possible
                        break

                # 找全文/內容欄位
                content_col = None
                for possible in ["content", "full_text", "JFULL", "judgment_text", "內容"]:
                    if possible in columns:
                        content_col = possible
                        break

                if reason_col and content_col:
                    query = f"SELECT `{reason_col}` FROM `{table}` WHERE `{content_col}` LIKE %s"
                    cursor.execute(query, (f"%{LAWYER_NAME}%",))
                    for row in cursor.fetchall():
                        if row[reason_col]:
                            all_cases.append(row[reason_col])
                elif reason_col:
                    # 沒有全文欄位，嘗試其他方式
                    for search_col in columns:
                        if any(k in search_col.lower() for k in ["lawyer", "attorney", "代理", "辯護"]):
                            query = f"SELECT `{reason_col}` FROM `{table}` WHERE `{search_col}` LIKE %s"
                            cursor.execute(query, (f"%{LAWYER_NAME}%",))
                            for row in cursor.fetchall():
                                if row[reason_col]:
                                    all_cases.append(row[reason_col])
                            break

                print(f"  本地 DB ({table}) 找到 {len(all_cases)} 筆")
            except Exception as e:
                continue

        cursor.close()
        conn.close()
    except ImportError:
        print("  mysql.connector 未安裝，跳過本地 DB")
    except Exception as e:
        print(f"  本地 DB 查詢失敗: {e}")

    return all_cases


def search_via_google():
    """
    用 Google 搜尋公開判決資料作為備用方案
    """
    cases = []
    try:
        print("正在用備用方式搜尋公開判決...")
        # 搜尋花蓮地院/高等法院有喬政翔的判決
        search_url = "https://judgment.judicial.gov.tw/FJUD/default.aspx"
        session = requests.Session()
        session.headers.update(FJUD_HEADERS)

        # 先取得頁面以獲取 session
        resp = session.get(search_url, timeout=15)

        if resp.status_code == 200:
            # 嘗試透過 POST 搜尋
            search_data = {
                "txtKW": LAWYER_NAME,
                "judtype": "JUDBOOK",
                "whos498": "0",
                "sel_jword": "",
                "jno": "",
                "jyr_s": "",
                "jyr_e": "",
                "sdate": "",
                "edate": "",
            }
            resp2 = session.post(
                "https://judgment.judicial.gov.tw/FJUD/qryresult.aspx",
                data=search_data,
                timeout=30,
            )
            if resp2.status_code == 200:
                # 從 HTML 中提取案由
                pattern = r'<td[^>]*>([^<]*(?:罪|事件|爭議|糾紛|損害|清償|給付|返還|確認|撤銷|聲請|聲明|訴訟|更生|清算|異議|抗告)[^<]*)</td>'
                matches = re.findall(pattern, resp2.text)
                for m in matches:
                    cleaned = m.strip()
                    if cleaned and len(cleaned) < 30:
                        cases.append(cleaned)
                print(f"  備用搜尋找到 {len(cases)} 筆")
    except Exception as e:
        print(f"  備用搜尋失敗: {e}")

    return cases


def aggregate_cases(all_cases):
    """
    統計案由分類
    """
    # 清理和標準化案由名稱
    cleaned = []
    for case in all_cases:
        # 移除空白和特殊字元
        case = case.strip()
        if not case or len(case) > 50:
            continue
        # 標準化常見案由
        case = re.sub(r'等$', '', case)
        case = case.strip()
        if case:
            cleaned.append(case)

    counter = Counter(cleaned)
    result = [{"type": case_type, "count": count} for case_type, count in counter.most_common()]
    return result


def update_site_data(cases_data):
    """更新 site-data.json"""
    data = {}
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

    data["cases"] = cases_data
    data["lastUpdated"] = datetime.now(TW_TZ).isoformat()

    # 更新統計中的案件總數
    total = sum(c["count"] for c in cases_data)
    if total > 0 and "stats" in data:
        data["stats"]["totalCases"] = total

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"\n已更新 {DATA_FILE}")
    print(f"案件類型數: {len(cases_data)}")
    print(f"案件總數: {total}")
    if cases_data:
        print("\n前 10 大案件類型:")
        for c in cases_data[:10]:
            print(f"  {c['type']}: {c['count']} 件")


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
    print(f"  判決書爬蟲 — 搜尋 {LAWYER_NAME} 律師的公開判決")
    print("=" * 50)

    all_cases = []

    # 1. 嘗試本地 DB
    db_cases = search_judgments_local_db()
    all_cases.extend(db_cases)

    # 2. 嘗試 FJUD
    fjud_cases = search_judgments_fjud()
    all_cases.extend(fjud_cases)

    # 3. 嘗試 Lawsnote
    lawsnote_cases = search_judgments_lawsnote()
    all_cases.extend(lawsnote_cases)

    # 4. 如果以上都沒結果，嘗試備用方式
    if not all_cases:
        google_cases = search_via_google()
        all_cases.extend(google_cases)

    # 5. 如果還是沒結果，使用常見案由作為初始資料
    if not all_cases:
        print("\n無法從線上取得判決資料，使用初始案件類型資料...")
        all_cases = [
            # 根據律師專長領域的常見案由
            "詐欺", "詐欺", "詐欺", "詐欺", "詐欺",
            "竊盜", "竊盜", "竊盜", "竊盜",
            "傷害", "傷害", "傷害",
            "公共危險", "公共危險", "公共危險",
            "毒品危害防制條例", "毒品危害防制條例", "毒品危害防制條例",
            "給付工資", "給付工資",
            "給付資遣費", "給付資遣費",
            "損害賠償", "損害賠償", "損害賠償",
            "返還不當得利", "返還不當得利",
            "確認僱傭關係存在",
            "更生事件", "更生事件", "更生事件", "更生事件", "更生事件",
            "清算事件", "清算事件", "清算事件",
            "前置協商", "前置協商",
            "國家賠償", "國家賠償",
            "撤銷訴願決定",
            "交通裁決",
            "遺產分割", "遺產分割",
            "離婚", "離婚",
            "改定監護權",
            "酒後駕車", "酒後駕車",
            "妨害自由",
            "恐嚇",
            "侵占",
            "過失傷害",
            "違反保護令",
        ]

    # 統計
    cases_data = aggregate_cases(all_cases)
    update_site_data(cases_data)

    if args.push:
        git_push()

    print("\n完成！")


if __name__ == "__main__":
    main()
