#!/usr/bin/env bash
# 回归：即使找不到 lsof，也要先停掉旧实例，再启动新实例。
set -eu

ROOT=$(cd "$(dirname "$0")/.." && pwd)
PORT=${RESTART_TEST_PORT:-18650}
TMP=$(mktemp -d "${TMPDIR:-/tmp}/class-hours-restart-test.XXXXXX")
FAKE_BIN="$TMP/bin"
OLD_PID=""
NEW_PID=""

cleanup() {
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    kill "$OLD_PID" 2>/dev/null || true
  fi
  if [ -n "$NEW_PID" ] && kill -0 "$NEW_PID" 2>/dev/null; then
    kill "$NEW_PID" 2>/dev/null || true
  fi
  rm -rf "$TMP"
}
trap cleanup EXIT INT TERM

port_ready() {
  (exec 3<>"/dev/tcp/127.0.0.1/$PORT") >/dev/null 2>&1
}

wait_for_port() {
  count=0
  while ! port_ready; do
    if [ "$count" -ge 40 ]; then
      echo "端口 $PORT 未在 10 秒内就绪"
      return 1
    fi
    sleep 0.25
    count=$((count + 1))
  done
}

cp "$ROOT/data/app.db" "$TMP/app.db"
mkdir -p "$TMP/files" "$FAKE_BIN"
cp -R "$ROOT/data/files/." "$TMP/files/"

# 让 lsof 命令存在但查不到 PID，模拟树莓派缺少 lsof 的故障条件。
printf '#!/bin/sh\nexit 1\n' > "$FAKE_BIN/lsof"
chmod +x "$FAKE_BIN/lsof"

cd "$ROOT"
CLASS_HOURS_DB="$TMP/app.db" \
CLASS_HOURS_FILES="$TMP/files" \
CLASS_HOURS_PORT="$PORT" \
CLASS_HOURS_NO_BROWSER=1 \
  .venv/bin/python main.py >"$TMP/old.log" 2>&1 &
OLD_PID=$!
wait_for_port

PATH="$FAKE_BIN:$PATH" \
CLASS_HOURS_IGNORE_SERVICE=1 \
CLASS_HOURS_DB="$TMP/app.db" \
CLASS_HOURS_FILES="$TMP/files" \
CLASS_HOURS_PORT="$PORT" \
CLASS_HOURS_NO_BROWSER=1 \
  ./scripts/restart-server.sh >"$TMP/restart.log" 2>&1 &
NEW_PID=$!

count=0
while kill -0 "$OLD_PID" 2>/dev/null; do
  if [ "$count" -ge 40 ]; then
    echo "旧实例没有停止"
    exit 1
  fi
  sleep 0.25
  count=$((count + 1))
done
wait_for_port

kill -0 "$NEW_PID"
grep -q "正在停止占用端口 $PORT 的旧实例" "$TMP/restart.log"
echo "重启脚本回归通过：旧实例已停止，新实例已监听 $PORT"
