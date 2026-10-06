#!/usr/bin/env bash
# 备份课时记录的全部数据（账本 app.db + 照片海报 + 导出的表格）。
#
# 为什么不直接 cp / tar 拷 app.db：程序在跑的时候数据库随时在写，
# 直接拷有可能拷到写了一半的文件。这里用 SQLite 自带的备份接口做一个
# 「一致的快照」，再用 rsync 拷照片。
#
# 用法：
#   ./scripts/backup-data.sh                          # 备到 <数据目录>/backups，保留最近 7 份
#   ./scripts/backup-data.sh /mnt/u盘/课时记录          # 备到 U 盘 / 移动硬盘
#   ./scripts/backup-data.sh /mnt/u盘/课时记录 --keep 30
#
# 数据在哪儿跟 main.py 用同一套环境变量：
#   CLASS_HOURS_DB     默认 <项目>/data/app.db
#   CLASS_HOURS_FILES  默认 <数据库旁边>/files
set -eu

cd "$(dirname "$0")/.." || exit 1

DEST=""
KEEP=7
while [ $# -gt 0 ]; do
  case "$1" in
    --keep)
      KEEP=$2
      shift 2
      ;;
    --keep=*)
      KEEP=${1#*=}
      shift
      ;;
    -h | --help)
      sed -n '2,17p' "$0"
      exit 0
      ;;
    *)
      DEST=$1
      shift
      ;;
  esac
done

PY=.venv/bin/python
if [ ! -x "$PY" ]; then
  echo "没找到运行环境（.venv）。先在项目目录里跑： uv sync"
  exit 1
fi

DB_PATH=${CLASS_HOURS_DB:-$PWD/data/app.db}
FILES_DIR=${CLASS_HOURS_FILES:-$(dirname "$DB_PATH")/files}
if [ ! -f "$DB_PATH" ]; then
  echo "找不到数据库：$DB_PATH"
  echo "（如果数据搬到别处了，先 export CLASS_HOURS_DB=... 再跑）"
  exit 1
fi

DEST=${DEST:-$(dirname "$DB_PATH")/backups}
STAMP=$(date +%Y%m%d_%H%M%S)
TARGET="$DEST/课时记录-$STAMP"
mkdir -p "$TARGET"

echo "==> 备份账本（一致的快照，不怕程序正在写）"
"$PY" - "$DB_PATH" "$TARGET/app.db" <<'PY'
import pathlib
import sqlite3
import sys

src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
con = sqlite3.connect(str(src), timeout=30)
con.execute("PRAGMA busy_timeout = 30000")
out = sqlite3.connect(str(dst))
try:
    con.backup(out)
finally:
    out.close()
    con.close()
print(f"    {src} -> {dst.name}（{dst.stat().st_size / 1024:.0f} KB）")
PY

if [ -d "$FILES_DIR" ]; then
  echo "==> 备份照片、海报和导出表格"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a "$FILES_DIR/" "$TARGET/files/"
  else
    mkdir -p "$TARGET/files"
    cp -a "$FILES_DIR/." "$TARGET/files/"
  fi
  echo "    $(find "$TARGET/files" -type f | wc -l | tr -d ' ') 个文件，$(du -sh "$TARGET/files" | cut -f1)"
else
  echo "（没找到 $FILES_DIR，跳过照片）"
fi

# 只保留最近 KEEP 份；名字对不上的一律不碰
if [ "$KEEP" -gt 0 ]; then
  TOTAL=$(ls -1d "$DEST"/课时记录-* 2>/dev/null | wc -l | tr -d ' ')
  if [ "$TOTAL" -gt "$KEEP" ]; then
    echo "==> 清理旧备份（保留最近 $KEEP 份）"
    ls -1d "$DEST"/课时记录-* 2>/dev/null | sort | head -n $((TOTAL - KEEP)) | while IFS= read -r old; do
      case "$old" in
        "$DEST"/课时记录-*)
          rm -rf -- "$old"
          echo "    删掉 $(basename "$old")"
          ;;
      esac
    done
  fi
fi

echo
echo "备份好了：$TARGET"
echo "这份 $(du -sh "$TARGET" | cut -f1)，备份目录现在一共 $(du -sh "$DEST" | cut -f1)"
echo
echo "提醒：备份和原始数据在同一块盘上，挡不住硬盘坏。"
echo "隔段时间拿 U 盘 / 移动硬盘再备一份： ./scripts/backup-data.sh /media/你的U盘名/课时记录"
