# 股息率择时系统

工作日检测 ETF/基金股息率，便宜时推送一次性买入信号到微信。不参与定投。

```bash
# 配置企业微信 Key
export WECOM_KEY="你的Key"

# 运行
python3 notify.py
```

详细架构见 [ARCHITECTURE.md](ARCHITECTURE.md)。
