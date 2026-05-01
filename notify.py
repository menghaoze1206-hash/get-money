#!/usr/bin/env python3
"""基金定投提醒工具 - 始终持有+股息率定投力度，每日推送加仓倍数建议"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

# 北京时间
TZ_BEIJING = timezone(timedelta(hours=8))


def now_beijing():
    return datetime.now(tz=TZ_BEIJING)
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
     "thresholds": (1.0, 1.8, None), "index_name": "红利低波"},
    {"name": "自由现金流ETF", "code": "159201", "market": "0",
     "yield_etf": "159201", "thresholds": (2.0, 4.0, 6.0)},
    # 场外基金 - 使用净值数据
    {"name": "南方红利低波联接A", "code": "008163", "type": "fund",
     "thresholds": (1.0, 1.8, None), "index_name": "标普红利"},
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


def buy_signal(effective):
    """根据有效股息率判断买入机会"""
    if effective is None:
        return ("#999999", "无法判断")
    if effective >= 8.0:
        return ("#ff0000", "🔥 大举买入")
    elif effective >= 6.0:
        return ("#ff6600", "买入机会")
    else:
        return ("#999999", "继续等待")



# 估值缓存（同一次运行内复用）
_val_cache = {}


def fetch_index_valuation(index_name):
    """从蛋卷基金获取指数PE/股息率估值数据"""
    if index_name in _val_cache:
        return _val_cache[index_name]

    url = "https://danjuanfunds.com/djapi/index_eva/dj"
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://danjuanfunds.com/",
    }
    try:
        req = request.Request(url, headers=headers)
        with request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        items = data.get("data", {}).get("items", [])
        for item in items:
            name = item.get("name", "")
            if name == index_name:
                result = {
                    "pe": item.get("pe"),
                    "pb": item.get("pb"),
                    "yield_pct": round(item.get("yeild", 0) * 100, 2),
                    "pe_pct": item.get("pe_percentile"),
                    "pb_pct": item.get("pb_percentile"),
                }
                _val_cache[index_name] = result
                return result
        _val_cache[index_name] = None
        return None
    except Exception as e:
        print(f"  获取{index_name}估值失败: {e}")
        _val_cache[index_name] = None
        return None


# ETF分红缓存
_etf_yield_cache = {}


def fetch_etf_dividend_yield(etf_code):
    """从ETF分红记录反推股息率，返回当前股息率和历史中位"""
    if etf_code in _etf_yield_cache:
        return _etf_yield_cache[etf_code]

    # 1. 爬取分红页面
    url = f"https://fundf10.eastmoney.com/fhsp_{etf_code}.html"
    headers = {
        "User-Agent": USER_AGENT,
        "Referer": "https://fundf10.eastmoney.com/",
    }
    try:
        req = request.Request(url, headers=headers)
        with request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  获取{etf_code}分红数据失败: {e}")
        _etf_yield_cache[etf_code] = None
        return None

    # 2. 解析分红表格，提取每份派现金额和日期
    tds = re.findall(r"<td[^>]*>([^<]*)</td>", html)
    dividends = []
    for i in range(0, len(tds), 5):
        row = tds[i : i + 5]
        if len(row) >= 4 and "每份派现金" in row[3]:
            m = re.search(r"(\d+\.?\d*)", row[3])
            if m:
                dividends.append((row[1], float(m.group(1))))
        elif len(row) >= 1 and "暂无拆分信息" in row[0]:
            break

    if not dividends:
        print(f"  {etf_code}无分红记录")
        _etf_yield_cache[etf_code] = None
        return None

    # 3. 计算过去12个月的分红总额
    now = now_beijing()
    one_year_ago = now - timedelta(days=365)
    trailing_sum = 0.0
    for date_str, amount in dividends:
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=TZ_BEIJING)
            if d >= one_year_ago:
                trailing_sum += amount
        except ValueError:
            continue

    if trailing_sum == 0:
        _etf_yield_cache[etf_code] = None
        return None

    # 4. 获取当前价格 (Sina API)
    prefix = "sh" if etf_code.startswith(("51", "56")) else "sz"
    try:
        sina_url = f"https://hq.sinajs.cn/list={prefix}{etf_code}"
        req2 = request.Request(sina_url, headers={
            "User-Agent": USER_AGENT,
            "Referer": "https://finance.sina.com.cn/",
        })
        with request.urlopen(req2, timeout=10) as resp2:
            data = resp2.read().decode("gbk", errors="replace")
        # Sina格式: name,open,prev_close,current,high,low,...
        current_price = float(data.split("=")[1].strip('"').split(",")[3])
    except Exception as e:
        print(f"  获取{etf_code}价格失败: {e}")
        _etf_yield_cache[etf_code] = None
        return None

    yield_pct = round(trailing_sum / current_price * 100, 2)

    # 5. 计算历史年度股息率（中位数作为"正常水平"）
    yearly_div = {}
    for date_str, amount in dividends:
        try:
            year = datetime.strptime(date_str, "%Y-%m-%d").year
            yearly_div[year] = yearly_div.get(year, 0.0) + amount
        except ValueError:
            continue

    ak = get_akshare()
    symbol = f"{prefix}{etf_code}"
    yearly_yields = []
    if ak and yearly_div:
        try:
            df = ak.stock_zh_index_daily(symbol=symbol)
            if df is not None and not df.empty:
                for year, total_div in yearly_div.items():
                    year_df = df[df["date"].apply(lambda x: str(x)[:4] == str(year))]
                    if not year_df.empty:
                        dec = year_df[year_df["date"].apply(lambda x: "-12-" in str(x))]
                        if not dec.empty:
                            close = float(dec.iloc[-1]["close"])
                            yearly_yields.append(round(total_div / close * 100, 2))
        except Exception:
            pass

    hist_yield = None
    if len(yearly_yields) >= 2:
        sorted_y = sorted(yearly_yields)
        n = len(sorted_y)
        hist_yield = round((sorted_y[n // 2 - 1] + sorted_y[n // 2]) / 2, 2) if n % 2 == 0 else sorted_y[n // 2]

    result = {"yield_pct": yield_pct}
    if hist_yield is not None:
        result["hist_yield"] = hist_yield
    _etf_yield_cache[etf_code] = result
    return result


def calc_effective_yield(yield_pct, hist_yield=None):
    """计算有效股息率（相对历史中位标准化到5%基准）"""
    if yield_pct is None:
        return None
    if hist_yield is not None and hist_yield > 0:
        return round(yield_pct / hist_yield * 5.0, 1)
    return round(yield_pct, 1)


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


def analyze(closes, fund, valuation=None):
    """股息率择时：便宜时提示一次性买入，不便宜时等待"""
    if len(closes) < 60:
        return {
            "name": fund["name"],
            "code": fund["code"],
            "effective": None,
            "reason": f"数据不足60个交易日(当前{len(closes)}天)",
        }

    current_price = closes[-1]
    ma20 = calc_ma(closes, 20)
    ma60 = calc_ma(closes, 60)

    diff_pct = (current_price - ma20) / ma20 * 100
    trend_up = current_price > ma60

    # 股息率择时：有效股息率>=6买入，>=8大举买入
    yld = valuation.get("yield_pct") if valuation else None
    if yld is not None:
        hist_yield = valuation.get("hist_yield") if valuation else None
        effective = calc_effective_yield(yld, hist_yield)
    else:
        effective = None

    color, action = buy_signal(effective)

    return {
        "name": fund["name"],
        "code": fund["code"],
        "current_price": round(current_price, 3),
        "ma20": round(ma20, 3),
        "ma60": round(ma60, 3),
        "diff_pct": round(diff_pct, 2),
        "trend_up": trend_up,
        "effective": effective,
        "action": action,
        "action_color": color,
        "valuation": valuation,
    }


def check_fund(fund):
    """检查单个基金 - ETF分红反推股息率，无数据时回退均线"""
    fund_type = fund.get("type", "etf")

    # 股息率来源：优先用yield_etf反推（含历史中位），其次蛋卷index_name
    yld_etf = fund.get("yield_etf")
    if yld_etf:
        valuation = fetch_etf_dividend_yield(yld_etf)
    else:
        index_name = fund.get("index_name")
        valuation = fetch_index_valuation(index_name) if index_name else None

    if fund_type == "fund":
        navs = fetch_fund_nav(fund["code"])
        return analyze(navs, fund, valuation)
    else:
        klines = fetch_kline(fund)
        closes = parse_kline(klines)
        return analyze(closes, fund, valuation)


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

    now = now_beijing().strftime("%Y-%m-%d %H:%M")

    # 构建 markdown 消息
    lines = [f"## 股息率买入信号 - {now}\n"]
    lines.append("> 股息率便宜时一次性买入，不便宜时继续等待\n")

    for r in results:
        name = r["name"]
        code = r["code"]

        if "reason" in r:
            lines.append(f"**{name}({code})**\n>  {r['reason']}\n")
        else:
            price = r["current_price"]
            action = r.get("action", "")
            action_color = r.get("action_color", "#666666")
            effective = r.get("effective")

            status = f"<font color='{action_color}'>{action}</font>"

            val_info = ""
            if r.get("valuation"):
                v = r["valuation"]
                yld = v["yield_pct"]
                if yld is not None:
                    hist = v.get("hist_yield")
                    if effective is not None:
                        if effective < 5.0:
                            level = "偏贵"
                        elif effective < 6.0:
                            level = "合理"
                        elif effective < 7.0:
                            level = "略便宜"
                        elif effective < 8.0:
                            level = "便宜"
                        else:
                            level = "很便宜"
                    else:
                        level = ""
                    hist_str = f"（历史中位{hist}%）" if hist else ""
                    pe_pb = f"  PE: {v['pe']}  PB: {v['pb']}" if "pe" in v else ""
                    eff_str = f" 有效: {effective}" if effective is not None else ""
                    val_info = f"\n> 股息率: **{yld}%**{hist_str} {level}{eff_str}{pe_pb}"

            ma_str = f"\n> MA20: {r['ma20']} 偏离: {r['diff_pct']}%"
            lines.append(
                f"**{name}({code})**\n"
                f"> {status}{ma_str}{val_info}\n"
            )

    lines.append(f"---\n> 股息率相对历史越高越便宜 | 便宜时买入 | 不便宜时等待")

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
    now = now_beijing().strftime("%Y-%m-%d %H:%M")
    lines = [f"<h3>股息率买入信号 - {now}</h3>", "<p>股息率便宜时一次性买入，不便宜时继续等待</p>", "<hr>"]

    for r in results:
        name = r["name"]
        code = r["code"]

        if "reason" in r:
            status = f"<span style='color:gray'>{r['reason']}</span>"
            detail = ""
        else:
            price = r["current_price"]
            action = r.get("action", "")
            action_color = r.get("action_color", "#666666")
            effective = r.get("effective")

            status = f"<span style='color:{action_color};font-weight:bold'>{action}</span>"
            val_html = ""
            if r.get("valuation"):
                v = r["valuation"]
                yld = v["yield_pct"]
                if yld is not None:
                    hist = v.get("hist_yield")
                    if effective is not None:
                        if effective < 5.0:
                            level = "偏贵"
                        elif effective < 6.0:
                            level = "合理"
                        elif effective < 7.0:
                            level = "略便宜"
                        elif effective < 8.0:
                            level = "便宜"
                        else:
                            level = "很便宜"
                    else:
                        level = ""
                    hist_str = f"（历史中位{hist}%）" if hist else ""
                    pe_pb = f"  PE: {v['pe']}  PB: {v['pb']}" if "pe" in v else ""
                    eff_str = f" 有效: {effective}" if effective is not None else ""
                    val_html = f"<br>股息率: <b>{yld}%</b>{hist_str}({level}){eff_str}{pe_pb}"

            ma_str = f"<br>MA20: {r['ma20']} 偏离: {r['diff_pct']}%"
            detail = f"{ma_str}{val_html}"

        lines.append(f"<p><b>{name}({code})</b> - {status}{detail}</p>")

    lines.append("<hr>")
    lines.append("<p>股息率相对历史越高越便宜 | 便宜时买入 | 不便宜时等待</p>")

    return "\n".join(lines)


def send_notification(title, content, results):
    """根据配置发送通知"""
    if NOTIFY_TYPE == "wecom":
        return send_wecom(title, results)
    else:
        return send_pushplus(title, content)


def main():
    """主函数"""
    print(f"开始检查股息率买入信号... {now_beijing().strftime('%Y-%m-%d %H:%M:%S')}")

    results = []
    for fund in WATCH_FUNDS:
        try:
            result = check_fund(fund)
            results.append(result)
            eff = result.get("effective")
            eff_str = f" eff={eff}" if eff is not None else ""
            print(f"  {result['name']}({result['code']}): {result.get('action', '')}{eff_str}")
        except Exception as e:
            print(f"  检查 {fund['name']}({fund['code']}) 失败: {e}")
            results.append({
                "name": fund["name"],
                "code": fund["code"],
                "effective": None,
                "reason": f"获取数据失败: {e}",
            })

    # 构建并发送通知
    title = f"股息率买入信号 - {now_beijing().strftime('%m月%d日')}"
    content = build_message(results)

    send_notification(title, content, results)
    print("检查完成")


if __name__ == "__main__":
    main()
