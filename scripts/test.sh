#!/bin/zsh
# 测试通知功能（立即发送一次）
# NOTIFY_TYPE 和对应的 Key 需要在环境中设置
# 或者直接 source scripts/run.sh 后执行

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/.."

NOTIFY_TYPE="${NOTIFY_TYPE:-wecom}"

if [ "$NOTIFY_TYPE" = "wecom" ] && [ -z "$WECOM_KEY" ]; then
    echo "⚠️  未设置 WECOM_KEY 环境变量"
    echo "请先运行: export WECOM_KEY='你的Key'"
    echo "或者在 scripts/run.sh 中设置后 source scripts/run.sh"
    exit 1
elif [ "$NOTIFY_TYPE" = "pushplus" ] && [ -z "$PUSHPLUS_TOKEN" ]; then
    echo "⚠️  未设置 PUSHPLUS_TOKEN 环境变量"
    echo "请先运行: export PUSHPLUS_TOKEN='你的Token'"
    exit 1
fi

python3 notify.py
