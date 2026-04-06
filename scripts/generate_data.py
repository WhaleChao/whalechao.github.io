#!/usr/bin/env python3
"""
MAGI 本地端資料匯出腳本
從 MariaDB 讀取案件統計，產生 site-data.json 並推送到 GitHub

使用方式：
    python3 generate_data.py

環境變數（可選，預設使用 MAGI 的 .env）:
    DB_HOST, DB_USER, DB_PASSWORD, DB_NAME
    WEBSITE_REPO_PATH - whalechao.github.io 的本地路徑
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

TW_TZ = timezone(timedelta(hours=8))

# 預設路徑
DEFAULT_REPO_PATH = os.path.expanduser("~/Desktop/whalechao.github.io")
MAGI_ENV_PATH = os.path.expanduser("~/Desktop/MAGI_v2/.env")


def load_magi_env():
    """從 MAGI 的 .env 載入資料庫設定"""
    env = {}
    env_path = Path(MAGI_ENV_PATH)
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip().strip("'\"")
    return env


def get_db_stats():
    """從 MariaDB 查詢案件統計"""
    try:
        import mysql.connector
    except ImportError:
        print("Warning: mysql.connector not available, using fallback stats")
        return None

    magi_env = load_magi_env()

    db_config = {
        "host": os.environ.get("DB_HOST", magi_env.get("MAGI_DB_HOST", "127.0.0.1")),
        "port": int(os.environ.get("DB_PORT", magi_env.get("MAGI_DB_PORT", "3306"))),
        "user": os.environ.get("DB_USER", magi_env.get("MAGI_DB_USER", "magi")),
        "password": os.environ.get("DB_PASSWORD", magi_env.get("MAGI_DB_PASSWORD", "")),
        "database": os.environ.get("DB_NAME", magi_env.get("MAGI_DB_NAME", "law_firm_data")),
    }

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        stats = {}

        # 案件總數
        cursor.execute("SELECT COUNT(*) as cnt FROM cases")
        row = cursor.fetchone()
        stats["totalCases"] = row["cnt"] if row else 0

        # 法律扶助案件數
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM cases WHERE case_source = '法律扶助' OR case_type LIKE '%法扶%'"
        )
        row = cursor.fetchone()
        stats["legalAidCases"] = row["cnt"] if row else 0

        # 執業年數（以 2016 年開始計算，可依實際修改）
        current_year = datetime.now(TW_TZ).year
        stats["yearsOfPractice"] = current_year - 2016

        # 發表文章數（如有 articles table）
        try:
            cursor.execute("SELECT COUNT(*) as cnt FROM articles")
            row = cursor.fetchone()
            stats["articles"] = row["cnt"] if row else 15
        except Exception:
            stats["articles"] = 15

        cursor.close()
        conn.close()
        return stats

    except Exception as e:
        print(f"Warning: DB query failed: {e}")
        return None


def get_existing_data(repo_path):
    """載入現有的 site-data.json"""
    data_file = Path(repo_path) / "data" / "site-data.json"
    if data_file.exists():
        with open(data_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"stats": {}, "news": [], "articles": []}


def generate_and_push():
    """產生資料並推送到 GitHub"""
    repo_path = os.environ.get("WEBSITE_REPO_PATH", DEFAULT_REPO_PATH)

    if not Path(repo_path).exists():
        print(f"Error: Repo path {repo_path} does not exist")
        sys.exit(1)

    # 載入現有資料
    data = get_existing_data(repo_path)

    # 更新統計
    db_stats = get_db_stats()
    if db_stats:
        data["stats"] = db_stats
    elif not data.get("stats"):
        data["stats"] = {
            "totalCases": 850,
            "legalAidCases": 230,
            "yearsOfPractice": 10,
            "articles": 15
        }

    # 更新時間
    now = datetime.now(TW_TZ)
    data["lastUpdated"] = now.isoformat()

    # 寫入檔案
    data_file = Path(repo_path) / "data" / "site-data.json"
    with open(data_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"Data exported to {data_file}")

    # Git commit & push
    try:
        os.chdir(repo_path)
        subprocess.run(["git", "add", "data/site-data.json"], check=True)

        # 檢查是否有變更
        result = subprocess.run(
            ["git", "diff", "--staged", "--quiet"],
            capture_output=True
        )
        if result.returncode != 0:
            # 有變更，commit & push
            msg = f"chore: auto-update site data {now.strftime('%Y-%m-%d %H:%M')}"
            subprocess.run(["git", "commit", "-m", msg], check=True)
            subprocess.run(["git", "push"], check=True)
            print("Changes pushed to GitHub successfully")
        else:
            print("No changes to push")

    except subprocess.CalledProcessError as e:
        print(f"Git operation failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    generate_and_push()
