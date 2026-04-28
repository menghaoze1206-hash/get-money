#!/bin/zsh
# 卸载定时任务

plist="com.jijin.notify.plist"
launchd_dir="$HOME/Library/LaunchAgents"
plist_path="$launchd_dir/$plist"

if [ -f "$plist_path" ]; then
    launchctl unload "$plist_path" 2>/dev/null
    rm "$plist_path"
    echo "✅ 定时任务已卸载"
else
    echo "⚠️  定时任务未加载"
fi
