#!/usr/bin/env bash
# 安全地重启当前项目：先停旧实例，确认端口释放，再启动新实例。
set -u

ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT" || exit 1

app_port="${CLASS_HOURS_PORT:-8550}"
export CLASS_HOURS_PORT="$app_port"
entrypoint="${1:-main.py}"

if [ ! -x .venv/bin/python ]; then
  echo "没找到运行环境（.venv 文件夹）。先在项目目录执行：uv sync"
  exit 1
fi

# 装了 systemd 服务时，由 systemd 负责停止和拉起，避免 Restart=always
# 把进程杀掉后立即重新占回端口。
if [ "${CLASS_HOURS_IGNORE_SERVICE:-0}" != "1" ] \
  && command -v systemctl >/dev/null 2>&1 \
  && systemctl cat class-hours.service >/dev/null 2>&1; then
  echo "检测到 systemd 服务，正在重启 class-hours.service…"
  if [ "$(id -u)" -eq 0 ]; then
    systemctl restart class-hours.service
  elif command -v sudo >/dev/null 2>&1; then
    sudo systemctl restart class-hours.service
  else
    echo "当前用户不能重启 class-hours.service。请用 sudo ./restart.sh"
    exit 1
  fi
  if systemctl is-active --quiet class-hours.service; then
    systemctl --no-pager --lines=5 status class-hours.service || true
    exit 0
  fi
  echo "class-hours.service 没有成功启动，请查看：journalctl -u class-hours -n 50"
  exit 1
fi

port_accepts_connections() {
  (exec 3<>"/dev/tcp/127.0.0.1/$app_port") >/dev/null 2>&1
}

find_port_pids() {
  local pids=""
  if command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -tiTCP:"$app_port" -sTCP:LISTEN 2>/dev/null || true)
  fi
  if [ -z "$pids" ] && [ "$(uname -s)" = "Linux" ] && command -v fuser >/dev/null 2>&1; then
    pids=$(fuser "${app_port}/tcp" 2>/dev/null | tr ' ' '\n' | grep -E '^[0-9]+$' || true)
  fi
  if [ -z "$pids" ] && command -v ss >/dev/null 2>&1; then
    pids=$(
      ss -ltnpH "sport = :$app_port" 2>/dev/null \
        | sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' \
        | sort -u || true
    )
  fi
  if [ -z "$pids" ] && command -v pgrep >/dev/null 2>&1; then
    for pid in $(pgrep -f 'python([0-9.]*)? .*main\.py' 2>/dev/null || true); do
      command_line=$(ps -p "$pid" -o args= 2>/dev/null || true)
      cwd=$(
        readlink "/proc/$pid/cwd" 2>/dev/null \
          || pwd
      )
      if [ "$cwd" = "$ROOT" ] || printf '%s' "$command_line" | grep -q "$ROOT/main.py"; then
        pids="$pids $pid"
      fi
    done
  fi
  printf '%s\n' $pids | sed '/^$/d' | sort -u
}

if port_accepts_connections; then
  old_pids=$(find_port_pids)
  if [ -z "$old_pids" ]; then
    echo "端口 $app_port 正在被占用，但当前没有可用的工具识别占用进程。"
    echo "请先运行：sudo ss -ltnp 'sport = :$app_port'"
    echo "树莓派可以安装：sudo apt install lsof"
    exit 1
  fi

  echo "正在停止占用端口 $app_port 的旧实例：$old_pids"
  for pid in $old_pids; do
    command_line=$(ps -p "$pid" -o args= 2>/dev/null || true)
    case "$command_line" in
      *main.py* | *flet* | *dev_watch.py*) ;;
      *)
        echo "端口 $app_port 被其他程序占用：PID $pid $command_line"
        echo "为安全起见没有终止它，请先确认占用程序。"
        exit 1
        ;;
    esac
    kill "$pid" 2>/dev/null || true
  done

  waited=0
  while port_accepts_connections; do
    if [ "$waited" -ge 40 ]; then
      echo "端口 $app_port 在 10 秒内没有释放，重启已停止。"
      echo "检查占用进程：sudo ss -ltnp 'sport = :$app_port'"
      exit 1
    fi
    sleep 0.25
    waited=$((waited + 1))
  done
fi

exec .venv/bin/python "$entrypoint"
