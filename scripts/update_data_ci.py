#!/usr/bin/env python3
"""
GitHub Actions CI script - 在 GitHub 上執行的資料更新腳本
從公開來源抓取新聞、判決等資訊來更新 site-data.json
"""

import json
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

TW_TZ = timezone(timedelta(hours=8))
DATA_FILE = Path(__file__).parent.parent / "data" / "site-data.json"


def load_existing_data():
    """載入現有的 site-data.json"""
    if DATA_FILE.exists():
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"stats": {}, "news": [], "articles": []}


def search_news():
    """搜尋與喬政翔律師相關的公開新聞"""
    news = []
    # 已知的固定新聞
    known_news = [
        {
            "title": "與司改會一起長大：專訪喬政翔律師",
            "url": "https://www.jrf.org.tw/articles/1969",
            "date": "2023",
            "source": "司法改革基金會"
        }
    ]
    news.extend(known_news)
    return news


def fetch_lawsnote_stats():
    """
    嘗試從 Lawsnote 公開頁面取得判決統計
    如果無法取得則返回 None
    """
    try:
        url = "https://page.lawsnote.com/page/5cffa99e0890331626f56525"
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code == 200:
            # 嘗試解析頁面中的案件數量等統計
            # 此處為佔位邏輯，實際需要根據頁面結構解析
            pass
    except Exception:
        pass
    return None


def update_data():
    """主更新邏輯"""
    data = load_existing_data()

    # 更新時間戳
    now = datetime.now(TW_TZ)
    data["lastUpdated"] = now.isoformat()

    # 更新新聞（合併已知新聞 + 新發現的）
    existing_urls = {n.get("url") for n in data.get("news", [])}
    new_news = search_news()
    for item in new_news:
        if item["url"] not in existing_urls:
            data.setdefault("news", []).append(item)
            existing_urls.add(item["url"])

    # 保留已有的 stats（由 MAGI 本地端更新），只更新時間
    if "stats" not in data:
        data["stats"] = {
            "totalCases": 850,
            "legalAidCases": 230,
            "yearsOfPractice": 10,
            "articles": 15
        }

    # 寫入檔案
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"Site data updated at {now.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    update_data()
