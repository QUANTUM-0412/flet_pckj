#!/bin/bash
# 开发模式：改完 Python 文件会自动重启，不用手动重启。
cd "$(dirname "$0")" || exit 1
app_port="${CLASS_HOURS_PORT:-8550}"
export CLASS_HOURS_NO_BROWSER=1
export CLASS_HOURS_IGNORE_SERVICE=1
( sleep 2; open "http://127.0.0.1:$app_port" >/dev/null 2>&1 & )
exec ./scripts/restart-server.sh dev_watch.py
