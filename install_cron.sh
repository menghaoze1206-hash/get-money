#!/bin/zsh
# 安装 cron 定时任务（合盖休眠后唤醒会补执行）

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 添加到 crontab
(crontab -l 2>/dev/null | grep -v "run_notify.sh"; echo "30 9 * * 1-5 cd $SCRIPT_DIR && ./run_notify.sh >> $SCRIPT_DIR/data/notify.log 2>&1") | crontab -

echo "✅ cron 任务已安装，工作日 9:30 执行"
echo ""
echo "注意：cron 会在电脑唤醒后补执行错过的任务"
echo "查看任务: crontab -l"
echo "删除任务: crontab -r"
