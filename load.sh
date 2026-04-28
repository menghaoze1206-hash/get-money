#!/bin/zsh
# 加载定时任务

cd "$(dirname "$0")"

plist="com.jijin.notify.plist"
launchd_dir="$HOME/Library/LaunchAgents"

# 复制 plist 到 LaunchAgents
mkdir -p "$launchd_dir"
cp "$plist" "$launchd_dir/"

# 加载定时任务
launchctl load "$launchd_dir/$plist"

echo "✅ 定时任务已加载，每天 9:30 自动运行"
echo ""
echo "注意：请在 run_notify.sh 中设置你的 PushPlus Token"
