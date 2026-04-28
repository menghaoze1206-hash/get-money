#!/usr/bin/env python3
"""中证红利指数股息率分析模块"""

import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib import error, parse, request

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DIVIDEND_CACHE = DATA_DIR / "dividend_cache.json"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
)


def _fetch_json(url, referer="https://data.eastmoney.com/"):
    req = request.Request(url, headers={"User-Agent": USER_AGENT, "Referer": referer})
    with request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def fetch_bond_yield_10y():
    """获取10年期国债收益率"""
    url = (
        "https://datacenter-web.eastmoney.com/api/data/v1/get"
        "?reportName=RPTA_WEB_TREASURYYIELD"
        "&columns=SOLAR_DATE,EMM00166469"
        "&sortColumns=SOLAR_DATE&sortTypes=-1&pageSize=1"
    )
    data = _fetch_json(url)
    if data.get("success") and data["result"]["data"]:
        return float(data["result"]["data"][0]["EMM00166469"] or 0)
    return 0


def fetch_index_quote(index_code="000922"):
    """获取指数行情数据（价格、PE等）"""
    url = (
        f"https://push2.eastmoney.com/api/qt/stock/get"
        f"?secid=1.{index_code}&fields=f43,f169,f170,f171&fltt=2"
    )
    data = _fetch_json(url)
    d = (data or {}).get("data") or {}
    return {
        "price": float(d.get("f43", 0)),
        "change_pct": float(d.get("f170", 0)),
    }


def load_dividend_cache():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not DIVIDEND_CACHE.exists():
        return {}
    try:
        return json.loads(DIVIDEND_CACHE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_dividend_cache(cache):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DIVIDEND_CACHE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def fetch_dividend_analysis():
    """获取完整的红利投资分析数据"""
    bond_yield = fetch_bond_yield_10y()
    quote = fetch_index_quote()

    cache = load_dividend_cache()

    # 股息率数据：优先使用缓存，否则使用默认推算值
    current_yield = cache.get("current_yield", 5.2)
    hist_yield_avg_1y = cache.get("hist_yield_avg_1y", 4.8)

    now = datetime.now()

    # 如果是新的一天，更新历史均值
    today_key = now.strftime("%Y-%m-%d")
    last_date = cache.get("last_update_date", "")

    if today_key != last_date:
        yields = cache.get("yields_history", [])
        if current_yield > 0:
            yields.append({"date": last_date or today_key, "yield": current_yield})
        yields = yields[-250:]
        if yields:
            hist_yield_avg_1y = round(
                sum(y["yield"] for y in yields) / len(yields), 2
            )
        cache["yields_history"] = yields
        cache["hist_yield_avg_1y"] = hist_yield_avg_1y
        cache["last_update_date"] = today_key
        save_dividend_cache(cache)

    return {
        "index_code": "000922",
        "index_name": "中证红利",
        "index_price": quote["price"],
        "index_change_pct": quote["change_pct"],
        "current_yield": current_yield,
        "hist_yield_avg_1y": hist_yield_avg_1y,
        "bond_yield_10y": bond_yield,
        "update_time": now.strftime("%Y-%m-%d %H:%M"),
    }
