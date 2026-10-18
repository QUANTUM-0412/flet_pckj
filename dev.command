#!/bin/bash
# 开发模式：改完 Python 文件会自动重启，不用手动重启。
cd "$(dirname "$0")" || exit 1

app_port="${CLASS_HOURS_PORT:-8550}"
old_pids="$(lsof -ti tcp:"$app_port" 2>/dev/null)"
if [ -n "$old_pids" ]; then
  kill $old_pids 2>/dev/null || true
  sleep 0.6
fi

if [ ! -x .venv/bin/python ]; then
  echo "没找到运行环境（.venv）。先在项目目录执行： uv sync"
  read -r -p "按回车键关闭窗口"
  exit 1
fi

export CLASS_HOURS_PORT="$app_port"
export CLASS_HOURS_NO_BROWSER=1
( sleep 2; open "http://127.0.0.1:$app_port" >/dev/null 2>&1 & )
exec .venv/bin/python dev_watch.py
