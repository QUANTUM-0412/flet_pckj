#!/bin/bash
# 快速重启正式服务：先停掉占着端口的旧进程，再正常启动。
cd "$(dirname "$0")" || exit 1

app_port="${CLASS_HOURS_PORT:-8550}"
old_pids="$(lsof -ti tcp:"$app_port" 2>/dev/null)"
if [ -n "$old_pids" ]; then
  kill $old_pids 2>/dev/null || true
  sleep 0.6
fi

if [ ! -x .venv/bin/python ]; then
  echo "没找到运行环境（.venv 文件夹）。先在项目目录执行： uv sync"
  read -r -p "按回车键关闭窗口"
  exit 1
fi

exec .venv/bin/python main.py
