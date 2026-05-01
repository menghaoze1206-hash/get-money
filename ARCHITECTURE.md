# 股息率定投系统架构文档

## 项目概览

工作日检测股息率，便宜时推送一次性买入信号到微信（企业微信/PushPlus）。

---

## 一、整体流程

```
  GitHub Actions (工作日 9:30 BJT)
         │
         ▼
     notify.py
         │
         ├─ 遍历 WATCH_FUNDS
         │    │
         │    ├─ [yield_etf] ──► fetch_etf_dividend_yield()
         │    │                    ├─ eastmoney 分红页面 → 分红记录
         │    │                    ├─ sina 实时价格
         │    │                    └─ akshare 年度收盘价 → 历史股息率中位
         │    │
         │    ├─ [index_name] ─► fetch_index_valuation()
         │    │                    └─ danjuanfunds.com 指数估值 API
         │    │
         │    └─ 获取价格数据
         │         ├─ ETF → fetch_kline() → parse_kline()
         │         └─ 场外基金 → fetch_fund_nav()
         │
         ├─ analyze()
         │    ├─ 有股息率数据 → calc_effective_yield() → buy_signal()
         │    └─ 无股息率数据 → 无法判断
         │
         └─ 推送通知
              ├─ NOTIFY_TYPE=wecom → send_wecom() [企业微信机器人]
              └─ NOTIFY_TYPE=pushplus → send_pushplus() [PushPlus]
```

## 二、策略核心：股息率择时买入

```
effective = yield_pct / hist_yield × 5.0        （有历史中位时）
effective = yield_pct                            （无历史中位时）

信号判断：
  effective < 6.0   →  继续等待（不便宜，不动）
  effective >= 6.0  →  买入机会（便宜，一次性买入）
  effective >= 8.0  →  大举买入（非常便宜，多买）
```

**核心思想**：只在股息率显著高于历史时才出手，平时不动。不参与定投。

## 三、信号分档

```
  effective    label        color
  ─────────    ─────        ──────
     <6.0      继续等待      #999999
    6.0~7.9    买入机会      #ff6600
     >=8.0     🔥 大举买入    #ff0000
```

## 四、基金配置 (WATCH_FUNDS)

| 基金 | 代码 | 类型 | 数据源 |
|---|---|---|---|
| 红利低波ETF | 512890 | ETF | 蛋卷指数(红利低波) |
| 自由现金流ETF | 159201 | ETF | ETF分红反推 |
| 南方红利低波联接A | 008163 | 场外基金 | 蛋卷指数(标普红利) |

数据优先级：`yield_etf` > `index_name`

## 五、关键函数一览

| 函数 | 职责 | 外部 API |
|---|---|---|
| `fetch_etf_dividend_yield()` | 从 ETF 分红记录反推当前股息率 + 历史中位 | eastmoney, sina, akshare |
| `fetch_index_valuation()` | 从蛋卷获取指数 PE/PB/股息率 | danjuanfunds.com |
| `fetch_kline()` | 获取 ETF 日 K 线 (最近 80 根) | eastmoney, akshare |
| `fetch_fund_nav()` | 获取场外基金净值 (最近 80 个交易日) | eastmoney |
| `calc_effective_yield()` | 股息率 → 有效股息率（相对历史标准化） | 无 |
| `buy_signal()` | 有效股息率 → 买入信号 + 颜色 | 无 |
| `analyze()` | 组装均线+估值数据，决策信号 | 无 |
| `send_wecom()` | 企业微信机器人 Markdown 推送 | 企业微信 webhook |
| `send_pushplus()` | PushPlus 微信推送 | pushplus.plus |

## 六、外部 API 依赖

```
  danjuanfunds.com /djapi/index_eva/dj     → 指数估值 (PE/PB/股息率)
  fundf10.eastmoney.com /fhsp_{code}.html   → ETF 分红记录
  api.fund.eastmoney.com /f10/lsjz         → 场外基金净值
  push2his.eastmoney.com /api/qt/stock     → K 线数据 (回退)
  hq.sinajs.cn /list={code}                → ETF 实时价格
  qyapi.weixin.qq.com /cgi-bin/webhook     → 企业微信通知
  pushplus.plus /send                      → PushPlus 通知
  akshare (Python 库)                       → K 线 + 指数日线 (优先)
```

## 七、部署方式

```
  ┌─ GitHub Actions ───────────────────────────┐
  │  cron: "30 1 * * 1-5" (UTC)               │
  │  等价于北京时间工作日 9:30                   │
  │  支持 workflow_dispatch 手动触发            │
  │  Secrets: WECOM_KEY                       │
  └────────────────────────────────────────────┘
```

## 八、文件清单

```
  jijin/
  ├── notify.py                 # 定投信号引擎
  ├── scripts/
  │   ├── run.sh                # 运行通知
  │   ├── test.sh               # 快速测试
  │   └── install_cron.sh       # cron 调度安装
  ├── .github/workflows/
  │   └── notify.yml            # GitHub Actions 定时任务
  ├── data/
  │   └── notify.log            # 运行日志
  ├── ARCHITECTURE.md           # 本文档
  ├── opencode.json             # OpenCode AI 配置
  └── .gitignore
```

## 九、策略演进历史

| 日期 | Commit | 变化 |
|---|---|---|
| 04-28 | `2369a06` | notify.py 诞生：MA 均线策略 |
| 04-29 | `ac828eb` | 加入 MA60 趋势过滤 |
| 04-29 | `b2aae75` | **切换为股息率策略**：便宜多投、贵了少投 |
| 04-30 | `02e43ef` | **引入历史中位**：相对股息率框架 |
| 04-30 | `f37e606` | **连续线性公式**：(eff-3.0)/2.0，范围 0~2.5x |
| 04-30 | `43e7db1` | 倍率取整到 0.5 步长，自由现金流接入股息率策略 |
| 05-01 | - | **放弃定投，改为机会买入**：effective>=6 买入，>=8 大举买入 |
