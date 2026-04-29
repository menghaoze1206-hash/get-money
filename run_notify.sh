#!/bin/zsh
# 股息率定投信号 - 始终持有，股息率只决定加仓力度

# 通知方式: wecom (企业微信) 或 pushplus
export NOTIFY_TYPE="wecom"

# 企业微信机器人 Webhook Key
# 在企业微信群 -> 群设置 -> 添加群机器人 -> 复制 Webhook URL 中的 key 部分
export WECOM_KEY="1acfb992-d196-4c0d-8581-b6eac8b695c2"

# 如果使用 PushPlus，设置 Token
# export PUSHPLUS_TOKEN="你的PushPlus Token"

export PATH="/usr/local/bin:/opt/homebrew/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

python3 notify.py >> data/notify.log 2>&1
