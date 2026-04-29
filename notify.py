#!/usr/bin/env python3
"""基金均线提醒工具 - 结合20日/60日均线，分级判断买入信号并通过微信通知"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib import error, parse, request

BASE_DIR = Path(__file__).resolve().parent
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
)

# 监控的基金列表
# thresholds: (轻仓阈值%, 建议买入阈值%, 重仓阈值%或None)
WATCH_FUNDS = [
    # ETF（场内基金）- 使用K线数据
    {"name": "红利低波ETF", "code": "512890", "market": "1",
     "thresholds": (1.0, 1.8, None)},
    {"name": "自由现金流ETF", "code": "159201", "market": "0",
     "thresholds": (2.0, 4.0, 6.0)},
    # 场外基金 - 使用净值数据
    {"name": "南方红利低波联接A", "code": "008163", "type": "fund",
     "thresholds": (1.0, 1.8, None)},
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
    """获取基金/ETF的K线数据（最近80个交易日，用于计算MA20和MA60）"""
    code = fund["code"]
    ak = get_akshare()

    if ak:
        try:
            symbol = f"sh{code}" if fund["market"] == "1" else f"sz{code}"
            df = ak.stock_zh_index_daily(symbol=symbol)
            if df is None or df.empty:
                raise ValueError(f"无法获取 {fund['name']}({code}) 的数据")
            df = df.tail(80)
            klines = []
            for _, row in df.iterrows():
                klines.append(
                    f"{row['date'].strftime('%Y-%m-%d') if hasattr(row['date'], 'strftime') else str(row['date'])},"
                    f"{row['open']},{row['close']},{row['low']},{row['high']},{row['volume']}"
                )
            return klines
        except Exception:
            pass  # akshare 失败，回退到 HTTP

    # HTTP 备用方案
    market = fund["market"]
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get"
        f"?secid={market}.{code}"
        f"&fields1=f1,f2,f3,f4,f5,f6"
        f"&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
        f"&klt=101&fqt=0&end=20500101&lmt=80"
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


def multiplier_label(mult):
    """映射定投倍数到显示信息"""
    if mult >= 2.0:
        return ("#ff0000", "🔥 大幅加码")
    elif mult >= 1.6:
        return ("#ff6600", "🟠 加码买入")
    elif mult >= 1.3:
        return ("#e6a817", "🟡 适度多投")
    elif mult >= 1.0:
        return ("#666666", "⚪ 标准定投")
    elif mult >= 0.7:
        return ("#3366cc", "🔵 减少投入")
    elif mult >= 0.5:
        return ("#339933", "🟢 轻仓观望")
    else:
        return ("#999999", "⏸️ 暂缓投入")


def calc_multiplier(diff_pct, trend_up, thresholds):
    """根据偏离和趋势计算定投倍数"""
    light_t, buy_t, strong_t = thresholds

    if trend_up:
        if diff_pct < 0:  # 低于MA20，多投
            below_pct = abs(diff_pct)
            if strong_t and below_pct >= strong_t:
                return 2.0
            elif below_pct >= buy_t:
                return 1.6
            elif below_pct >= light_t:
                return 1.3
            else:
                return 1.0
        else:  # 高于MA20，少投
            if diff_pct >= light_t:
                return 0.4
            elif diff_pct >= light_t * 0.5:
                return 0.6
            else:
                return 0.8
    else:  # 趋势向下，控制仓位
        if diff_pct < 0:
            below_pct = abs(diff_pct)
            if strong_t and below_pct >= strong_t:
                return 1.0
            elif below_pct >= buy_t:
                return 0.8
            else:
                return 0.7
        else:
            return 0.5


def fetch_fund_nav(code):
    """获取场外基金净值历史（最近80个交易日），返回净值列表（从旧到新）"""
    JZ_URL = "https://api.fund.eastmoney.com/f10/lsjz"
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": f"https://fundf10.eastmoney.com/jjjz_{code}.html",
    }

    all_entries = []
    # API 每页最多20条，分4页获取80条
    for page in range(1, 5):
        url = f"{JZ_URL}?fundCode={code}&pageIndex={page}&pageSize=20"
        req = request.Request(url, headers=headers)
        with request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        entries = data.get("Data", {}).get("LSJZList", [])
        if not entries:
            break
        all_entries.extend(entries)

    if not all_entries:
        raise ValueError(f"无法获取基金 {code} 的净值数据")

    # API 返回从新到旧，反转为从旧到新
    navs = []
    for e in reversed(all_entries):
        navs.append(float(e["DWJZ"]))
    return navs


def analyze(closes, fund):
    """分析价格/净值序列，结合MA20/MA60给出定投倍数建议"""
    if len(closes) < 60:
        return {
            "name": fund["name"],
            "code": fund["code"],
            "multiplier": 0,
            "reason": f"数据不足60个交易日(当前{len(closes)}天)",
        }

    current_price = closes[-1]
    ma20 = calc_ma(closes, 20)
    ma60 = calc_ma(closes, 60)

    diff_pct = (current_price - ma20) / ma20 * 100
    trend_up = current_price > ma60
    t = fund.get("thresholds", (2.0, 4.0, None))
    mult = calc_multiplier(diff_pct, trend_up, t)
    color, action = multiplier_label(mult)

    return {
        "name": fund["name"],
        "code": fund["code"],
        "current_price": round(current_price, 3),
        "ma20": round(ma20, 3),
        "ma60": round(ma60, 3),
        "diff_pct": round(diff_pct, 2),
        "trend_up": trend_up,
        "multiplier": mult,
        "action": action,
        "action_color": color,
    }


def check_fund(fund):
    """检查单个基金 - 支持ETF(场内)和场外基金"""
    fund_type = fund.get("type", "etf")

    if fund_type == "fund":
        navs = fetch_fund_nav(fund["code"])
        return analyze(navs, fund)
    else:
        klines = fetch_kline(fund)
        closes = parse_kline(klines)
        return analyze(closes, fund)


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

    # 构建 markdown 消息
    lines = [f"## 基金均线提醒 - {now}\n"]
    lines.append("> 每日定投倍数建议\n")

    for r in results:
        name = r["name"]
        code = r["code"]
        mult = r.get("multiplier", 1.0)

        if "reason" in r:
            lines.append(f"**{name}({code})**\n> ⚠️ {r['reason']}\n")
        else:
            price = r["current_price"]
            ma20 = r["ma20"]
            ma60 = r["ma60"]
            diff_pct = r["diff_pct"]
            trend_up = r["trend_up"]
            action = r.get("action", "")
            action_color = r.get("action_color", "#666666")

            status = f"<font color='{action_color}'>{action}</font>"
            direction = "低于" if diff_pct < 0 else "高于"
            trend_text = "↑ 向上" if trend_up else "↓ 向下"

            lines.append(
                f"**{name}({code})**\n"
                f"> {status}\n"
                f"> 定投倍数: **{mult}x** | 当前: {price}\n"
                f"> MA20: {ma20}  MA60: {ma60}\n"
                f"> {direction}MA20 {abs(diff_pct)}%  趋势: {trend_text}\n"
            )

    lines.append(f"---\n定投倍数 >1 加码，=1 标准，<1 减少")

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
    lines = [f"<h3>基金均线提醒 - {now}</h3>", "<p>每日定投倍数建议</p>", "<hr>"]

    for r in results:
        name = r["name"]
        code = r["code"]
        mult = r.get("multiplier", 1.0)

        if "reason" in r:
            status = f"<span style='color:gray'>⚠️ {r['reason']}</span>"
            detail = ""
        else:
            price = r["current_price"]
            ma20 = r["ma20"]
            ma60 = r["ma60"]
            diff_pct = r["diff_pct"]
            trend_up = r["trend_up"]
            action = r.get("action", "")
            action_color = r.get("action_color", "#666666")

            status = f"<span style='color:{action_color};font-weight:bold'>{action}</span>"
            direction = "低于" if diff_pct < 0 else "高于"
            trend_text = "↑ 向上" if trend_up else "↓ 向下"
            detail = (
                f"<br>定投倍数: <b>{mult}x</b> | 当前: {price}"
                f"<br>MA20: {ma20}  MA60: {ma60}"
                f"<br>{direction}MA20 {abs(diff_pct)}%  趋势: {trend_text}"
            )

        lines.append(f"<p><b>{name}({code})</b> - {status}{detail}</p>")

    lines.append("<hr>")
    lines.append("<p>定投倍数 >1 加码，=1 标准，<1 减少</p>")

    return "\n".join(lines)


def send_notification(title, content, results):
    """根据配置发送通知"""
    if NOTIFY_TYPE == "wecom":
        return send_wecom(title, results)
    else:
        return send_pushplus(title, content)


def main():
    """主函数"""
    print(f"开始检查基金均线... {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    results = []
    for fund in WATCH_FUNDS:
        try:
            result = check_fund(fund)
            results.append(result)
            print(f"  {result['name']}({result['code']}): {result.get('multiplier', 0)}x {result.get('action', '')}")
        except Exception as e:
            print(f"  检查 {fund['name']}({fund['code']}) 失败: {e}")
            results.append({
                "name": fund["name"],
                "code": fund["code"],
                "multiplier": 0,
                "reason": f"获取数据失败: {e}",
            })
    
    # 构建并发送通知
    title = f"基金均线提醒 - {datetime.now().strftime('%m月%d日')}"
    content = build_message(results)
    
    send_notification(title, content, results)
    print("检查完成")


if __name__ == "__main__":
    main()
