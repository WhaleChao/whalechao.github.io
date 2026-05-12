#!/usr/bin/env python3
"""
GitHub Actions CI script - 在 GitHub 上執行的資料更新腳本
從公開來源抓取新聞、判決等資訊來更新 site-data.json
"""

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

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


def refresh_judgment_stats(data):
    """用公開司法院裁判書系統更新個人網站判決統計。"""
    try:
        from crawl_judgments import create_session, search_fjud

        result = search_fjud(create_session())
    except Exception as exc:
        data["judgmentUpdateStatus"] = {
            "ok": False,
            "source": "司法院裁判書系統",
            "error": str(exc)[:300],
            "checkedAt": datetime.now(TW_TZ).isoformat(),
        }
        return False

    if not result or int(result.get("total") or 0) <= 0:
        data["judgmentUpdateStatus"] = {
            "ok": False,
            "source": "司法院裁判書系統",
            "error": "empty_result",
            "checkedAt": datetime.now(TW_TZ).isoformat(),
        }
        return False

    data.setdefault("stats", {})
    data["stats"]["totalCases"] = int(result.get("total") or 0)
    data["stats"]["caseTypes"] = len(result.get("categories") or {})
    data["caseCategories"] = result.get("categories") or {}
    data["cases"] = result.get("cases") or []
    data["courts"] = result.get("courts") or {}
    data["judgmentUpdateStatus"] = {
        "ok": True,
        "source": "司法院裁判書系統",
        "checkedAt": datetime.now(TW_TZ).isoformat(),
    }
    return True


def update_data():
    """主更新邏輯"""
    data = load_existing_data()

    now = datetime.now(TW_TZ)

    # 更新新聞（合併已知新聞 + 新發現的）
    existing_urls = {n.get("url") for n in data.get("news", [])}
    new_news = search_news()
    for item in new_news:
        if item["url"] not in existing_urls:
            data.setdefault("news", []).append(item)
            existing_urls.add(item["url"])

    if "stats" not in data:
        data["stats"] = {
            "totalCases": 850,
            "legalAidCases": 230,
            "yearsOfPractice": 10,
            "articles": 15
        }

    refreshed_judgments = refresh_judgment_stats(data)

    # lastUpdated 代表主要公開數據已完成更新；判決抓取失敗時保留既有時間，
    # 避免網站看起來每天更新、但判決數其實停住。
    if refreshed_judgments:
        data["lastUpdated"] = now.isoformat()

    # 寫入檔案
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"Site data updated at {now.strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    update_data()
