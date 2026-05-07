# 股息率定投提醒系统

工作日检测 ETF/基金股息率和估值，按有效股息率给出定投/加仓倍率建议，并可按每月预算自动换算每个交易日建议投入金额。

```bash
# 配置企业微信 Key
export WECOM_KEY="你的Key"

# 可选：直接用环境变量配置月投入预算
export MONTHLY_INVEST_BUDGET=5000

# 运行
python3 notify.py
```

也可以启动 Web 面板，在首页输入“每月资金”。系统会按本月周一至周五估算交易日数，把月预算拆成 50 元步进的基础日投金额，再乘以每只基金当前的定投倍数。

详细架构见 [ARCHITECTURE.md](ARCHITECTURE.md)。
