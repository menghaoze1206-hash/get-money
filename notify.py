#!/usr/bin/env python3
"""基金定投提醒工具 - 始终持有+股息率定投力度，每日推送加仓倍数建议"""

import json
import os
import re
import sys
from calendar import monthrange
from datetime import datetime, timedelta, timezone

# 北京时间
TZ_BEIJING = timezone(timedelta(hours=8))


def now_beijing():
    return datetime.now(tz=TZ_BEIJING)
from pathlib import Path
from urllib import error, parse, request

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
)
INVEST_STEP = 50

# 监控的基金列表
WATCH_FUNDS = [
    # ETF（场内基金）- 使用K线数据
    {"name": "红利低波ETF", "code": "512890", "market": "1",
     "index_name": "红利低波"},
    {"name": "自由现金流ETF", "code": "159201", "market": "0",
     "yield_etf": "159201", "index_code": "980092"},
    # 场外基金 - 使用净值数据
    {"name": "南方红利低波联接A", "code": "008163", "type": "fund",
     "index_name": "标普红利"},
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
    """获取基金/ETF的K线数据（最近80个交易日，用于展示MA偏离）"""
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


def round_invest_amount(amount, step=INVEST_STEP):
    """把投入金额取整到易执行的金额，如 50、100、150。"""
    if amount is None or amount <= 0:
        return 0
    return max(step, int(round(amount / step)) * step)


def month_workdays(day=None):
    """用本月工作日近似交易日；不额外接入节假日日历。"""
    day = day or now_beijing().date()
    _, days = monthrange(day.year, day.month)
    return sum(
        1
        for d in range(1, days + 1)
        if datetime(day.year, day.month, d).weekday() < 5
    )


def get_monthly_budget_setting():
    """月投入预算：优先环境变量，其次读取本地 Web 面板设置。"""
    env_budget = os.environ.get("MONTHLY_INVEST_BUDGET")
    if env_budget:
        try:
            return max(0, int(float(env_budget)))
        except ValueError:
            pass
    try:
        from backend.database import get_monthly_budget
        return get_monthly_budget()
    except Exception:
        return 0


def build_investment_plan(monthly_budget=None):
    if monthly_budget is None:
        monthly_budget = get_monthly_budget_setting()
    workdays = month_workdays()
    daily_raw = monthly_budget / workdays if monthly_budget and workdays else 0
    return {
        "monthly_budget": monthly_budget,
        "workdays": workdays,
        "daily_base_amount": round_invest_amount(daily_raw),
    }


# 信号分档 (threshold, multiplier, color, action_label, valuation_label)
SIGNAL_TIERS = [
    (8.0, 5.0, "#ff0000", "🔥 大举买入 5x", "很便宜"),
    (7.0, 3.0, "#ff6600", "加码定投 3x", "便宜"),
    (6.0, 2.0, "#e67e22", "加倍定投 2x", "略便宜"),
    (5.0, 1.0, "#27ae60", "正常定投 1x", "合理"),
    (4.0, 0.5, "#3498db", "减少定投 0.5x", "偏贵"),
]


def _lookup_tier(effective):
    """查找有效股息率对应的分档"""
    if effective is None:
        return None
    for tier in SIGNAL_TIERS:
        if effective >= tier[0]:
            return tier
    return None


def dca_multiplier(effective):
    if effective is None:
        return None
    tier = _lookup_tier(effective)
    return tier[1] if tier else 0.0


def buy_signal(effective):
    if effective is None:
        return ("#999999", "无法判断", None)
    tier = _lookup_tier(effective)
    if tier:
        return (tier[2], tier[3], tier[1])
    return ("#999999", "暂停定投", 0.0)


def valuation_level(effective):
    if effective is None:
        return ""
    tier = _lookup_tier(effective)
    return tier[4] if tier else "很贵"


# 估值缓存（同一次运行内复用）
_val_cache = {}


def fetch_index_valuation(index_name):
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
            _val_cache[name] = {
                "pe": item.get("pe"),
                "pb": item.get("pb"),
                "yield_pct": round(item.get("yeild", 0) * 100, 2),
                "pe_pct": item.get("pe_percentile"),
                "pb_pct": item.get("pb_percentile"),
            }
        return _val_cache.get(index_name)
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


# CNI指数缓存
_cni_cache = {}


def fetch_cni_index_data(index_code):
    """获取国证指数PE和均线偏离数据（PE越低+指数低于MA=越便宜）"""
    if index_code in _cni_cache:
        return _cni_cache[index_code]

    ak = get_akshare()
    if not ak:
        _cni_cache[index_code] = None
        return None

    try:
        all_idx = ak.index_all_cni()
        row = all_idx[all_idx["指数代码"] == index_code]
        if row.empty:
            _cni_cache[index_code] = None
            return None
        row = row.iloc[0]
        pe = row.get("PE滚动")
        if pe is None or (hasattr(pe, '__iter__') and not pe) or pe != pe:  # NaN check
            _cni_cache[index_code] = None
            return None
        pe = float(pe)
        if pe <= 0:
            _cni_cache[index_code] = None
            return None
        current_level = float(row["收盘点位"])

        hist = ak.index_hist_cni(symbol=index_code)
        closes = [float(x) for x in hist["收盘价"].tolist()]
        if len(closes) < 60:
            _cni_cache[index_code] = None
            return None
        ma60 = sum(closes[-60:]) / 60
        diff_pct = round((current_level - ma60) / ma60 * 100, 2)

        result = {
            "pe": round(pe, 2),
            "index_level": round(current_level, 2),
            "ma60": round(ma60, 2),
            "diff_pct": diff_pct,
        }
        _cni_cache[index_code] = result
        return result
    except Exception as e:
        print(f"  获取CNI指数{index_code}数据失败: {e}")
        _cni_cache[index_code] = None
        return None


def calc_effective_from_pe(pe, index_diff_pct):
    """PE盈利率 + 指数均线偏离 → 有效收益率"""
    if pe is None or pe <= 0:
        return None
    earnings_yield = 1.0 / pe * 100
    # 指数低于MA时放大有效收益率，高于时不变
    adjustment = 1.0 + max(0, -index_diff_pct) / 100
    return round(earnings_yield * adjustment, 1)


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


def analyze(closes, fund, valuation=None, cni_data=None, investment_plan=None):
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

    yld = valuation.get("yield_pct") if valuation else None
    if yld is not None:
        hist_yield = valuation.get("hist_yield") if valuation else None
        effective = calc_effective_yield(yld, hist_yield)
    elif cni_data is not None:
        effective = calc_effective_from_pe(cni_data["pe"], cni_data["diff_pct"])
    else:
        effective = None

    color, action, multiplier = buy_signal(effective)
    daily_base_amount = (investment_plan or {}).get("daily_base_amount") or 0
    suggested_amount = (
        round_invest_amount(daily_base_amount * multiplier)
        if multiplier is not None and daily_base_amount
        else None
    )

    return {
        "name": fund["name"],
        "code": fund["code"],
        "current_price": round(current_price, 3),
        "ma20": round(ma20, 3),
        "ma60": round(ma60, 3),
        "diff_pct": round(diff_pct, 2),
        "effective": effective,
        "dca_multiplier": multiplier,
        "monthly_budget": (investment_plan or {}).get("monthly_budget"),
        "workdays": (investment_plan or {}).get("workdays"),
        "daily_base_amount": daily_base_amount or None,
        "suggested_amount": suggested_amount,
        "action": action,
        "action_color": color,
        "valuation": valuation,
        "cni_data": cni_data,
    }


def check_fund(fund, investment_plan=None):
    """检查单个基金 - ETF分红反推股息率，无数据时回退CNI指数PE"""
    fund_type = fund.get("type", "etf")

    # 股息率来源：优先用yield_etf反推（含历史中位），其次蛋卷index_name
    yld_etf = fund.get("yield_etf")
    if yld_etf:
        valuation = fetch_etf_dividend_yield(yld_etf)
    else:
        index_name = fund.get("index_name")
        valuation = fetch_index_valuation(index_name) if index_name else None

    # CNI指数数据（PE+均线，作为股息率缺失时的替代）
    cni_data = None
    index_code = fund.get("index_code")
    if index_code:
        cni_data = fetch_cni_index_data(index_code)

    if fund_type == "fund":
        navs = fetch_fund_nav(fund["code"])
        return analyze(navs, fund, valuation, cni_data, investment_plan)
    else:
        klines = fetch_kline(fund)
        closes = parse_kline(klines)
        return analyze(closes, fund, valuation, cni_data, investment_plan)


def send_pushplus(title, content, pushplus_token=None):
    """通过 PushPlus 发送微信通知"""
    token = pushplus_token or PUSHPLUS_TOKEN
    if not token:
        print("错误: 未设置 PUSHPLUS_TOKEN")
        return False
    
    payload = {
        "token": token,
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


def send_wecom(title, results, wecom_key=None):
    """通过企业微信机器人发送通知"""
    key = wecom_key or WECOM_KEY
    if not key:
        print("错误: 未设置 WECOM_KEY")
        return False

    now = now_beijing().strftime("%Y-%m-%d %H:%M")

    # 构建 markdown 消息
    lines = [f"## 股息率买入信号 - {now}\n"]
    lines.append("> 定投打底 + 股息率加速：便宜时加码，贵时减少/暂停\n")
    plan = next((r for r in results if r.get("daily_base_amount")), None)
    if plan:
        lines.append(
            f"> 月预算: **{plan['monthly_budget']}元** "
            f"本月交易日(估): {plan['workdays']}天 "
            f"基础日投: **{plan['daily_base_amount']}元**\n"
        )

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
            suggested_amount = r.get("suggested_amount")

            status = f"<font color='{action_color}'>{action}</font>"
            amount_info = (
                f"\n> 建议投入: **{suggested_amount}元**"
                if suggested_amount is not None
                else ""
            )

            val_info = ""
            if r.get("valuation"):
                v = r["valuation"]
                yld = v["yield_pct"]
                if yld is not None:
                    hist = v.get("hist_yield")
                    level = valuation_level(effective)
                    hist_str = f"（历史中位{hist}%）" if hist else ""
                    pe_pb = f"  PE: {v['pe']}  PB: {v['pb']}" if "pe" in v else ""
                    eff_str = f" 有效: {effective}" if effective is not None else ""
                    val_info = f"\n> 股息率: **{yld}%**{hist_str} {level}{eff_str}{pe_pb}"

            cni_info = ""
            if r.get("cni_data"):
                c = r["cni_data"]
                cni_info = f"\n> PE: {c['pe']} 盈利率: {round(1/c['pe']*100,1)}% 指数MA60偏离: {c['diff_pct']}%"

            ma_str = f"\n> MA20: {r['ma20']} 偏离: {r['diff_pct']}%"
            lines.append(
                f"**{name}({code})**\n"
                f"> {status}{amount_info}{ma_str}{cni_info}{val_info}\n"
            )

    lines.append(f"---\n> 股息率相对历史越高越便宜 | 便宜时买入 | 不便宜时等待")

    payload = {
        "msgtype": "markdown",
        "markdown": {"content": "\n".join(lines)},
    }

    url = f"{WECOM_WEBHOOK}?key={key}"
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
    lines = [f"<h3>股息率买入信号 - {now}</h3>", "<p>定投打底 + 股息率加速：便宜时加码，贵时减少/暂停</p>", "<hr>"]
    plan = next((r for r in results if r.get("daily_base_amount")), None)
    if plan:
        lines.append(
            f"<p>月预算: <b>{plan['monthly_budget']}元</b> "
            f"本月交易日(估): {plan['workdays']}天 "
            f"基础日投: <b>{plan['daily_base_amount']}元</b></p>"
        )

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
            suggested_amount = r.get("suggested_amount")

            status = f"<span style='color:{action_color};font-weight:bold'>{action}</span>"
            amount_html = (
                f"<br>建议投入: <b>{suggested_amount}元</b>"
                if suggested_amount is not None
                else ""
            )
            val_html = ""
            if r.get("valuation"):
                v = r["valuation"]
                yld = v["yield_pct"]
                if yld is not None:
                    hist = v.get("hist_yield")
                    level = valuation_level(effective)
                    hist_str = f"（历史中位{hist}%）" if hist else ""
                    pe_pb = f"  PE: {v['pe']}  PB: {v['pb']}" if "pe" in v else ""
                    eff_str = f" 有效: {effective}" if effective is not None else ""
                    val_html = f"<br>股息率: <b>{yld}%</b>{hist_str}({level}){eff_str}{pe_pb}"

            cni_html = ""
            if r.get("cni_data"):
                c = r["cni_data"]
                cni_html = f"<br>PE: {c['pe']} 盈利率: {round(1/c['pe']*100,1)}% 指数MA60偏离: {c['diff_pct']}%"

            ma_str = f"<br>MA20: {r['ma20']} 偏离: {r['diff_pct']}%"
            detail = f"{amount_html}{ma_str}{cni_html}{val_html}"

        lines.append(f"<p><b>{name}({code})</b> - {status}{detail}</p>")

    lines.append("<hr>")
    lines.append("<p>股息率相对历史越高越便宜 | 便宜时买入 | 不便宜时等待</p>")

    return "\n".join(lines)


def send_notification(title, results, wecom_key=None, pushplus_token=None, notify_type=None):
    ntype = notify_type or NOTIFY_TYPE
    if ntype == "wecom":
        return send_wecom(title, results, wecom_key=wecom_key)
    else:
        return send_pushplus(title, build_message(results), pushplus_token=pushplus_token)


def main():
    """主函数"""
    print(f"开始检查股息率买入信号... {now_beijing().strftime('%Y-%m-%d %H:%M:%S')}")

    # 尝试从数据库获取多用户数据
    users_data = _load_users_from_db()

    if users_data:
        _run_multi_user(users_data)
    else:
        _run_single_user()

    print("检查完成")


def _load_users_from_db():
    """从 SQLite 加载所有用户及其基金配置。无用户时返回 []。"""
    try:
        from backend.database import get_all_users_with_funds
        return get_all_users_with_funds()
    except Exception as e:
        print(f"  加载用户数据失败(将使用单用户模式): {e}")
        return []


def _analyze_fund(fund, investment_plan=None):
    """分析单个基金，返回结果。错误时返回 reason dict。"""
    try:
        return check_fund(fund, investment_plan)
    except Exception as e:
        return {
            "name": fund.get("name", ""),
            "code": fund.get("code", ""),
            "effective": None,
            "reason": f"获取数据失败: {e}",
        }


def _fund_dedup_key(f):
    return (f["code"], f.get("yield_etf") or "", f.get("index_name") or "", f.get("index_code") or "")


def _run_multi_user(users_data):
    all_fund_configs = {}
    for ud in users_data:
        for f in ud["funds"]:
            key = _fund_dedup_key(f)
            if key not in all_fund_configs:
                all_fund_configs[key] = f

    if not all_fund_configs:
        print("  没有用户配置了基金，跳过分析")
        return

    print(f"  统一分析 {len(all_fund_configs)} 只唯一基金...")
    fund_results = {}
    for key, fund in all_fund_configs.items():
        result = _analyze_fund(fund)
        fund_results[key] = result
        eff = result.get("effective")
        eff_str = f" eff={eff}" if eff is not None else ""
        print(f"    {result['name']}({result['code']}): {result.get('action', '')}{eff_str}")

    try:
        from backend.database import save_run_results
        all_unique_funds = list(all_fund_configs.values())
        all_results = list(fund_results.values())
        save_run_results(all_unique_funds, all_results)
    except Exception as e:
        print(f"  数据落盘失败: {e}")

    for ud in users_data:
        user = ud["user"]
        user_funds_list = ud["funds"]
        monthly_budget = ud["monthly_budget"]

        if not user_funds_list:
            continue

        plan = build_investment_plan(monthly_budget)

        user_results = []
        for f in user_funds_list:
            r = fund_results.get(_fund_dedup_key(f))
            if r is None:
                continue
            r_copy = dict(r)
            multiplier = r.get("dca_multiplier")
            daily_base = plan["daily_base_amount"]
            r_copy["monthly_budget"] = plan["monthly_budget"]
            r_copy["workdays"] = plan["workdays"]
            r_copy["daily_base_amount"] = daily_base or None
            r_copy["suggested_amount"] = (
                round_invest_amount(daily_base * multiplier)
                if multiplier is not None and daily_base
                else None
            )
            user_results.append(r_copy)

        if not user_results:
            continue

        username = user.get("username", user.get("id", "?"))
        print(f"\n  为用户 {username} 推送通知"
              f"（{len(user_results)}只基金, 月预算={monthly_budget}元）")

        title = f"股息率买入信号 - {now_beijing().strftime('%m月%d日')}"
        send_notification(
            title, user_results,
            wecom_key=user.get("wecom_key"),
            pushplus_token=user.get("pushplus_token"),
            notify_type=user.get("notify_type"),
        )


def _run_single_user():
    """单用户模式（兼容旧版：使用 WATCH_FUNDS + 环境变量）"""
    investment_plan = build_investment_plan()
    if investment_plan["monthly_budget"]:
        print(
            f"  月预算={investment_plan['monthly_budget']}元 "
            f"本月交易日(估)={investment_plan['workdays']} "
            f"基础日投={investment_plan['daily_base_amount']}元"
        )

    results = []
    for fund in WATCH_FUNDS:
        result = _analyze_fund(fund, investment_plan)
        results.append(result)
        eff = result.get("effective")
        eff_str = f" eff={eff}" if eff is not None else ""
        amount = result.get("suggested_amount")
        amount_str = f" amount={amount}元" if amount is not None else ""
        print(f"  {result['name']}({result['code']}): {result.get('action', '')}{eff_str}{amount_str}")

    title = f"股息率买入信号 - {now_beijing().strftime('%m月%d日')}"
    send_notification(title, results)

    try:
        from backend.database import save_run_results
        save_run_results(WATCH_FUNDS, results)
    except Exception as e:
        print(f"数据落盘失败: {e}")


if __name__ == "__main__":
    main()
