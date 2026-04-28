#!/bin/zsh
# 测试通知功能（立即发送一次）

cd "$(dirname "$0")"

# 检查是否设置了 Token
if [ -z "$PUSHPLUS_TOKEN" ]; then
    echo "⚠️  未设置 PUSHPLUS_TOKEN 环境变量"
    echo "请先运行: export PUSHPLUS_TOKEN='你的Token'"
    echo "或者在 run_notify.sh 中设置"
    exit 1
fi

python3 notify.py
