#!/usr/bin/env bash
# 把课时记录放到后台静默运行：不占终端、不弹浏览器。
#
# Windows 那边用 docs/wsl/silent-start.vbs 调这个脚本，就一点窗口都不会出现。
# 已经在跑的话什么都不做，所以可以放心重复执行（开机自动执行也没问题）。
#
# 用法： ./scripts/wsl-silent-start.sh
set -eu

cd "$(dirname "$0")/.." || exit 1

PORT=${CLASS_HOURS_PORT:-8550}
PY=.venv/bin/python
PIDFILE=$PWD/.run.pid
LOG=${CLASS_HOURS_LOG:-$PWD/run.log}

if [ ! -x "$PY" ]; then
  echo "还没装运行环境。先在项目目录里跑： uv sync" >&2
  exit 1
fi

# 端口有响应就算在跑，不用管是谁拉起来的
running() {
  "$PY" - "$PORT" <<'PY' 2>/dev/null
import socket
import sys

s = socket.socket()
s.settimeout(0.5)
sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
PY
}

if running; then
  echo "已经在跑了： http://localhost:$PORT"
  exit 0
fi

# 装过 systemd 服务的话优先交给它（开机自启、崩了自动重启，比 nohup 稳）
if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files class-hours.service >/dev/null 2>&1; then
  if sudo -n systemctl start class-hours 2>/dev/null; then
    sleep 1
    if running; then
      echo "已通过 systemd 服务启动： http://localhost:$PORT"
      exit 0
    fi
  fi
fi

# 没有 systemd 服务（或者没权限免密 sudo）：直接丢到后台
echo "后台启动中……"
if command -v setsid >/dev/null 2>&1; then
  FLET_FORCE_WEB_SERVER=1 setsid nohup "$PY" main.py >>"$LOG" 2>&1 </dev/null &
else
  FLET_FORCE_WEB_SERVER=1 nohup "$PY" main.py >>"$LOG" 2>&1 </dev/null &
fi
echo $! >"$PIDFILE"

for _ in $(seq 1 10); do
  sleep 0.5
  if running; then
    echo "起来了： http://localhost:$PORT"
    echo "日志：$LOG"
    exit 0
  fi
done

echo "等了 5 秒还没起来，日志里有报错：$LOG" >&2
exit 1
