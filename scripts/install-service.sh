#!/usr/bin/env bash
# 把课时记录装成开机自启、关掉终端也不停的 systemd 服务（Ubuntu Server 上用）。
#
# 用法：
#   sudo ./scripts/install-service.sh                                  # 数据就放项目里的 data/
#   sudo ./scripts/install-service.sh --data-dir /var/lib/class-hours    # 数据放项目外面（长期跑推荐）
#   ./scripts/install-service.sh --dry-run                              # 只打印会生成的服务文件，不安装
#
# 之后常用命令：
#   systemctl status class-hours
#   journalctl -u class-hours -f
#   sudo systemctl restart class-hours
set -eu

DATA_DIR=""
DRY_RUN=0
while [ $# -gt 0 ]; do
  case "$1" in
    --data-dir)
      DATA_DIR=$2
      shift 2
      ;;
    --data-dir=*)
      DATA_DIR=${1#*=}
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h | --help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "不认识的参数：$1（--help 看用法）"
      exit 1
      ;;
  esac
done

DIR=$(cd "$(dirname "$0")/.." && pwd)
RUN_USER=${SUDO_USER:-$(id -un)}
UNIT=/etc/systemd/system/class-hours.service

build_unit() {
  awk -v dir="$DIR" -v user="$RUN_USER" -v data="$DATA_DIR" '
    {
      gsub(/__DIR__/, dir)
      gsub(/__USER__/, user)
    }
    /^# __DATA_DIR_ENV__$/ {
      if (data != "") {
        printf "Environment=CLASS_HOURS_DB=%s/app.db\n", data
        printf "Environment=CLASS_HOURS_FILES=%s/files\n", data
      }
      next
    }
    { print }
  ' "$DIR/deploy/class-hours.service"
}

if [ "$DRY_RUN" = "1" ]; then
  build_unit
  exit 0
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "要用 sudo 跑：sudo ./scripts/install-service.sh"
  echo "（只想看看会生成什么： ./scripts/install-service.sh --dry-run）"
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  echo "这台机器没有 systemd，装不了服务。直接跑 ./start.sh 就行。"
  exit 1
fi

if [ ! -x "$DIR/.venv/bin/python" ]; then
  echo "还没装运行环境。先用 $RUN_USER 这个账号在 $DIR 里跑一次： uv sync"
  exit 1
fi

if [ -n "$DATA_DIR" ] && [ ! -f "$DATA_DIR/app.db" ]; then
  echo "数据目录 $DATA_DIR 里还没有 app.db。先把现有数据搬过去，再重跑本脚本："
  echo
  echo "  sudo mkdir -p '$DATA_DIR'"
  echo "  sudo rsync -a '$DIR/data/' '$DATA_DIR/'"
  echo "  sudo chown -R $RUN_USER:$RUN_USER '$DATA_DIR'"
  echo
  echo "（搬完确认 $DATA_DIR/app.db 和 $DATA_DIR/files 都在，再跑一次本脚本）"
  exit 1
fi

if [ "$RUN_USER" = "root" ]; then
  echo "提醒：别用 root 直接跑这个服务，建议先用普通账号 uv sync，再 sudo 跑本脚本。"
fi

if [ -n "$DATA_DIR" ]; then
  mkdir -p "$DATA_DIR"
  chown -R "$RUN_USER:$RUN_USER" "$DATA_DIR"
fi

build_unit > "$UNIT"
systemctl daemon-reload
systemctl enable --now class-hours
echo
echo "装好了：$UNIT"
echo "运行身份：$RUN_USER，项目目录：$DIR"
if [ -n "$DATA_DIR" ]; then
  echo "数据目录：$DATA_DIR（在项目外面，git 永远碰不到）"
else
  echo "数据目录：$DIR/data"
fi
systemctl --no-pager --lines=5 status class-hours || true
echo
echo "看日志： journalctl -u class-hours -f"
echo "放行端口（如果开了防火墙）： sudo ufw allow 8550/tcp"
