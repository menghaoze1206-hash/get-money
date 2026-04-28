#!/usr/bin/env python3
"""基金均线提醒工具 - 每天检查基金是否低于20日均线，低于则通过微信通知"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib import error, parse, request

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
NOTIFY_CACHE = DATA_DIR / "notify_cache.json"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
)

# 监控的基金列表
WATCH_FUNDS = [
    {"name": "红利低波ETF", "code": "512890", "market": "1"},  # 上交所
    {"name": "红利低波100", "code": "515080", "market": "1"},  # 上交所
    {"name": "自由现金流ETF", "code": "159201", "market": "0"},  # 深交所
]

# 通知方式配置
NOTIFY_TYPE = os.environ.get("NOTIFY_TYPE", "wecom").lower()  # wecom / pushplus
PUSHPLUS_TOKEN = os.environ.get("PUSHPLUS_TOKEN", "")
PUSHPLUS_URL = "http://www.pushplus.plus/send"

# 企业微信机器人配置
WECOM_KEY = os.environ.get("WECOM_KEY", "")
WECOM_WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"


def fetch_json(url, referer="https://quote.eastmoney.com/"):
    """通用 JSON 请求方法"""
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": referer,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    req = request.Request(url, headers=headers)
    with request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


_imported_akshare = None

def get_akshare():
    """延迟导入 akshare"""
    global _imported_akshare
    if _imported_akshare is None:
        try:
            import akshare as ak
            _imported_akshare = ak
        except ImportError:
            _imported_akshare = False
    return _imported_akshare


def fetch_kline(fund):
    """获取基金/ETF的K线数据（最近30个交易日）"""
    code = fund["code"]
    ak = get_akshare()
    
    if ak:
        # 使用 akshare
        symbol = f"sh{code}" if fund["market"] == "1" else f"sz{code}"
        df = ak.stock_zh_index_daily(symbol=symbol)
        if df is None or df.empty:
            raise ValueError(f"无法获取 {fund['name']}({code}) 的数据")
        # 取最近30天
        df = df.tail(30)
        # 格式: "日期,开盘,收盘,最低,最高,成交量"
        klines = []
        for _, row in df.iterrows():
            klines.append(
                f"{row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else str(row['date'])},"
                f"{row['open']},{row['close']},{row['low']},{row['high']},{row['volume']}"
            )
        return klines
    else:
        # 备用方案：直接 HTTP 请求（如果可用）
        market = fund["market"]
        url = (
            f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
            f"?secid={market}.{code}"
            f"&fields1=f1,f2,f3,f4,f5,f6"
            f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
            f"&klt=101&fqt=0&end=20500101&lmt=30"
        )
        data = fetch_json(url)
        klines = (data.get("data") or {}).get("klines", [])
        if not klines:
            raise ValueError(f"无法获取 {fund['name']}({code}) 的K线数据")
        return klines


def parse_kline(klines):
    """解析K线数据，返回收盘价列表"""
    # 格式: "日期,开盘,收盘,最低,最高,成交量"
    closes = []
    for k in klines:
        parts = k.split(",")
        closes.append(float(parts[2]))  # 收盘价
    return closes


def calc_ma(closes, n=20):
    """计算N日均线"""
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def check_fund(fund):
    """检查单个基金是否可以购买"""
    klines = fetch_kline(fund)
    closes = parse_kline(klines)
    
    if len(closes) < 20:
        return {
            "name": fund["name"],
            "code": fund["code"],
            "can_buy": False,
            "reason": "数据不足20个交易日",
        }
    
    current_price = closes[-1]
    ma20 = calc_ma(closes, 20)
    can_buy = current_price < ma20
    
    return {
        "name": fund["name"],
        "code": fund["code"],
        "current_price": round(current_price, 3),
        "ma20": round(ma20, 3),
        "can_buy": can_buy,
        "diff": round(current_price - ma20, 3),
        "diff_pct": round((current_price - ma20) / ma20 * 100, 2),
    }


def send_pushplus(title, content):
    """通过 PushPlus 发送微信通知"""
    if not PUSHPLUS_TOKEN:
        print("错误: 未设置 PUSHPLUS_TOKEN 环境变量")
        return False
    
    payload = {
        "token": PUSHPLUS_TOKEN,
        "title": title,
        "content": content,
        "template": "html",
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        PUSHPLUS_URL,
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    
    try:
        with request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("code") == 200:
                print("PushPlus 通知发送成功")
                return True
            else:
                print(f"PushPlus 通知发送失败: {result}")
                return False
    except Exception as e:
        print(f"PushPlus 通知发送异常: {e}")
        return False


def send_wecom(title, results):
    """通过企业微信机器人发送通知"""
    if not WECOM_KEY:
        print("错误: 未设置 WECOM_KEY 环境变量")
        return False
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    buy_count = sum(1 for r in results if r.get("can_buy"))
    
    # 构建 markdown 消息
    lines = [f"## 基金均线提醒 - {now}\n"]
    
    for r in results:
        name = r["name"]
        code = r["code"]
        can_buy = r.get("can_buy", False)
        
        if "reason" in r:
            lines.append(f"**{name}({code})**\n> ⚠️ {r['reason']}\n")
        else:
            price = r["current_price"]
            ma20 = r["ma20"]
            diff_pct = r["diff_pct"]
            
            if can_buy:
                status = "<font color='red'>✅ 可购买</font>"
            else:
                status = "<font color='green'>❌ 不购买</font>"
            
            direction = "低于" if diff_pct < 0 else "高于"
            lines.append(
                f"**{name}({code})** {status}\n"
                f"> 当前价格: {price}，20日均线: {ma20}\n"
                f"> {direction}均线 {abs(diff_pct)}%\n"
            )
    
    lines.append(f"---\n**今日共 {buy_count} 个基金可购买**")
    
    payload = {
        "msgtype": "markdown",
        "markdown": {"content": "\n".join(lines)},
    }
    
    url = f"{WECOM_WEBHOOK}?key={WECOM_KEY}"
    data = json.dumps(payload).encode("utf-8")
    
    req = request.Request(
        url,
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    
    try:
        with request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("errcode") == 0:
                print("企业微信通知发送成功")
                return True
            else:
                print(f"企业微信通知发送失败: {result}")
                return False
    except Exception as e:
        print(f"企业微信通知发送异常: {e}")
        return False


def build_message(results):
    """构建通知消息（返回 HTML 格式供 PushPlus 使用）"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"<h3>基金均线提醒 - {now}</h3>", "<hr>"]
    
    buy_count = sum(1 for r in results if r.get("can_buy"))
    
    for r in results:
        name = r["name"]
        code = r["code"]
        can_buy = r.get("can_buy", False)
        
        if "reason" in r:
            status = f"<span style='color:gray'>⚠️ {r['reason']}</span>"
            detail = ""
        else:
            price = r["current_price"]
            ma20 = r["ma20"]
            diff_pct = r["diff_pct"]
            
            if can_buy:
                status = "<span style='color:red;font-weight:bold'>✅ 可购买</span>"
            else:
                status = "<span style='color:green'>❌ 不购买</span>"
            
            direction = "低于" if diff_pct < 0 else "高于"
            detail = f"<br>当前价格: {price}，20日均线: {ma20}，{direction}均线 {abs(diff_pct)}%"
        
        lines.append(f"<p><b>{name}({code})</b> - {status}{detail}</p>")
    
    lines.append("<hr>")
    lines.append(f"<p>今日共 {buy_count} 个基金可购买</p>")
    
    return "\n".join(lines)


def send_notification(title, content, results):
    """根据配置发送通知"""
    if NOTIFY_TYPE == "wecom":
        return send_wecom(title, results)
    else:
        return send_pushplus(title, content)


def load_cache():
    """加载缓存"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not NOTIFY_CACHE.exists():
        return {}
    try:
        return json.loads(NOTIFY_CACHE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def save_cache(cache):
    """保存缓存"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    NOTIFY_CACHE.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def should_notify_today():
    """检查今天是否已经发送过通知"""
    cache = load_cache()
    today = datetime.now().strftime("%Y-%m-%d")
    return cache.get("last_notify_date") != today


def mark_notified():
    """标记今天已发送通知"""
    cache = load_cache()
    cache["last_notify_date"] = datetime.now().strftime("%Y-%m-%d")
    save_cache(cache)


def main():
    """主函数"""
    # 检查是否需要发送通知（避免重复发送）
    if not should_notify_today():
        print("今天已经发送过通知，跳过")
        return
    
    print(f"开始检查基金均线... {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = []
    for fund in WATCH_FUNDS:
        try:
            result = check_fund(fund)
            results.append(result)
            print(f"  {result['name']}({result['code']}): 可购买={result.get('can_buy', False)}")
        except Exception as e:
            print(f"  检查 {fund['name']}({fund['code']}) 失败: {e}")
            results.append({
                "name": fund["name"],
                "code": fund["code"],
                "can_buy": False,
                "reason": f"获取数据失败: {e}",
            })
    
    # 构建并发送通知
    title = f"基金均线提醒 - {datetime.now().strftime('%m月%d日')}"
    content = build_message(results)
    
    if send_notification(title, content, results):
        mark_notified()
    
    print("检查完成")


if __name__ == "__main__":
    main()
