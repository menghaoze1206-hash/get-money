# 股息率定投提醒系统架构文档

## 项目概览

工作日检测 ETF/基金股息率和估值，按有效股息率给出定投/加仓倍率建议；用户可配置每月投入预算，系统自动估算每个交易日的基础日投金额和单只基金建议投入，并推送到微信（企业微信/PushPlus）。

---

## 一、整体流程

```
  GitHub Actions (工作日 9:30 BJT)
         │
         ▼
     notify.py
         │
         ├─ 读取月预算
         │    ├─ 环境变量 MONTHLY_INVEST_BUDGET
         │    └─ 本地 SQLite settings.monthly_budget
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
         │    ├─ 有股息率数据 → calc_effective_yield() → dca_multiplier() → buy_signal()
         │    ├─ 无股息率、有 CNI 数据 → calc_effective_from_pe() → dca_multiplier() → buy_signal()
         │    └─ 无可用估值数据 → 无法判断
         │
         └─ 推送通知
              ├─ NOTIFY_TYPE=wecom → send_wecom() [企业微信机器人]
              └─ NOTIFY_TYPE=pushplus → send_pushplus() [PushPlus]
```

## 二、策略核心：股息率定投力度

```
effective = yield_pct / hist_yield × 5.0        （有历史中位时）
effective = yield_pct                            （无历史中位时）
effective = 1 / pe × 100 × adjustment            （无股息率、有 CNI PE 回退时）

adjustment = 1 + max(0, -index_diff_pct) / 100   （指数低于 MA60 时放大）

信号判断：
  effective < 4.0   →  暂停定投
  effective >= 4.0  →  减少定投 0.5x
  effective >= 5.0  →  正常定投 1x
  effective >= 6.0  →  加倍定投 2x
  effective >= 7.0  →  加码定投 3x
  effective >= 8.0  →  大举买入 5x
```

**核心思想**：始终用有效股息率衡量便宜程度；越便宜，加仓/定投倍率越高，偏贵时减少或暂停。

## 三、资金拆分

```
monthly_budget = 用户配置的每月可投入资金
workdays = 本月周一至周五天数                    （近似交易日，不扣除法定节假日）
daily_base_amount = round_to_50(monthly_budget / workdays)
suggested_amount = round_to_50(daily_base_amount × dca_multiplier)
```

金额按 50 元步进取整，便于实际下单。例如 3000 元/月、当月 21 个交易日时，基础日投约为 150 元。

月预算来源优先级：

```
MONTHLY_INVEST_BUDGET 环境变量 > Web 面板保存到 SQLite 的 monthly_budget > 0
```

## 四、信号分档

```
  effective    multiplier    label          color
  ─────────    ──────────    ───────────    ───────
     <4.0         0.0x       暂停定投        #999999
    4.0~4.9       0.5x       减少定投        #3498db
    5.0~5.9       1.0x       正常定投        #27ae60
    6.0~6.9       2.0x       加倍定投        #e67e22
    7.0~7.9       3.0x       加码定投        #ff6600
     >=8.0        5.0x       🔥 大举买入     #ff0000
```

估值标签：

```
  effective <4   → 很贵
  4~4.9          → 偏贵
  5~5.9          → 合理
  6~6.9          → 略便宜
  7~7.9          → 便宜
  >=8            → 很便宜
```

## 五、基金配置 (WATCH_FUNDS)

| 基金 | 代码 | 类型 | 数据源 |
|---|---|---|---|
| 红利低波ETF | 512890 | ETF | 蛋卷指数(红利低波) |
| 自由现金流ETF | 159201 | ETF | ETF分红反推；CNI 指数 PE 作为股息率缺失时回退 |
| 南方红利低波联接A | 008163 | 场外基金 | 蛋卷指数(标普红利) |

数据优先级：`yield_etf` > `index_name`

`index_code` 提供 CNI 指数 PE 和 MA60 偏离数据，仅在股息率数据不可用时作为回退估值来源。

## 六、关键函数一览

| 函数 | 职责 | 外部 API |
|---|---|---|
| `fetch_etf_dividend_yield()` | 从 ETF 分红记录反推当前股息率 + 历史中位 | eastmoney, sina, akshare |
| `fetch_index_valuation()` | 从蛋卷获取指数 PE/PB/股息率 | danjuanfunds.com |
| `fetch_kline()` | 获取 ETF 日 K 线 (最近 80 根) | eastmoney, akshare |
| `fetch_fund_nav()` | 获取场外基金净值 (最近 80 个交易日) | eastmoney |
| `calc_effective_yield()` | 股息率 → 有效股息率（相对历史标准化） | 无 |
| `fetch_cni_index_data()` | 获取 CNI 指数 PE、指数点位、MA60 偏离 | akshare |
| `calc_effective_from_pe()` | PE 盈利率 + 指数 MA60 偏离 → 有效收益率 | 无 |
| `dca_multiplier()` | 有效股息率 → 定投/加仓倍率 | 无 |
| `build_investment_plan()` | 月预算 → 本月交易日估算 + 基础日投 | 无 |
| `round_invest_amount()` | 金额取整到 50 元步进 | 无 |
| `buy_signal()` | 有效股息率 → 定投动作 + 颜色 | 无 |
| `valuation_level()` | 有效股息率 → 估值标签 | 无 |
| `analyze()` | 组装均线、估值、倍率和通知字段 | 无 |
| `send_wecom()` | 企业微信机器人 Markdown 推送 | 企业微信 webhook |
| `send_pushplus()` | PushPlus 微信推送 | pushplus.plus |

## 七、外部 API 依赖

```
  danjuanfunds.com /djapi/index_eva/dj     → 指数估值 (PE/PB/股息率)
  fundf10.eastmoney.com /fhsp_{code}.html   → ETF 分红记录
  api.fund.eastmoney.com /f10/lsjz         → 场外基金净值
  push2his.eastmoney.com /api/qt/stock     → K 线数据 (回退)
  hq.sinajs.cn /list={code}                → ETF 实时价格
  qyapi.weixin.qq.com /cgi-bin/webhook     → 企业微信通知
  pushplus.plus /send                      → PushPlus 通知
  akshare (Python 库)                       → K 线、CNI 指数 PE、指数历史日线 (优先/回退)
```

## 八、部署方式

```
  ┌─ GitHub Actions ───────────────────────────┐
  │  cron: "30 1 * * 1-5" (UTC)               │
  │  等价于北京时间工作日 9:30                   │
  │  支持 workflow_dispatch 手动触发            │
  │  Secrets: WECOM_KEY                       │
  └────────────────────────────────────────────┘
```

## 九、文件清单

```
  jijin/
  ├── notify.py                 # 股息率定投提醒引擎
  ├── backend/
  │   ├── main.py                # FastAPI 接口
  │   └── database.py            # SQLite 持久化、预算设置、看板查询
  ├── frontend/
  │   └── src/                   # React 看板和月预算输入
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

## 十、策略演进历史

| 日期 | Commit | 变化 |
|---|---|---|
| 04-28 | `2369a06` | notify.py 诞生：MA 均线策略 |
| 04-29 | `ac828eb` | 加入 MA60 趋势过滤 |
| 04-29 | `b2aae75` | **切换为股息率策略**：便宜多投、贵了少投 |
| 04-30 | `02e43ef` | **引入历史中位**：相对股息率框架 |
| 04-30 | `f37e606` | **连续线性公式**：(eff-3.0)/2.0，范围 0~2.5x |
| 04-30 | `43e7db1` | 倍率取整到 0.5 步长，自由现金流接入股息率策略 |
| 05-01 | - | 当前代码保留定投倍率框架：effective 4/5/6/7/8 对应 0.5x/1x/2x/3x/5x |
| 05-06 | - | 加入月预算设置，自动计算基础日投和按倍率调整后的建议投入金额 |
