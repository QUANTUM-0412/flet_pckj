#!/usr/bin/env bash
# 把项目打成一个 tar.gz，方便拷到 Ubuntu Server（或者别的机器）上。
#
# 跟 git 不一样：这个包**连 data 文件夹一起带走**（数据库、上传的照片、海报），
# 所以搬过去就是原样，不用再单独搬数据。
#
# 用法：
#   ./scripts/make-deploy-package.sh                    # 打在项目上一级目录
#   ./scripts/make-deploy-package.sh /tmp/别的名字.tar.gz  # 指定输出位置
set -eu

cd "$(dirname "$0")/.." || exit 1
PROJECT_DIR=$PWD
NAME=$(basename "$PROJECT_DIR")
PARENT=$(dirname "$PROJECT_DIR")
STAMP=$(date +%Y%m%d)
OUT=${1:-"$PARENT/${NAME}-部署包-${STAMP}.tar.gz"}

# 不要打进去的东西：运行环境（到服务器上重新 uv sync）、缓存、Mac 垃圾文件
tar \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  --exclude='.flet/storage' \
  -czf "$OUT" \
  -C "$PARENT" "$NAME"

echo "打包好了：$OUT"
echo "大小：$(du -h "$OUT" | cut -f1)"

# 顺手检查一下，别把运行环境或者缓存打进去（有的话说明 exclude 没生效）
CONTENTS=$(tar -tzf "$OUT")
if printf '%s\n' "$CONTENTS" | grep -qE '(^|/)(\.venv|__pycache__)/|\.DS_Store'; then
  echo "注意：包里混进了 .venv / __pycache__ / .DS_Store，检查一下上面的 tar 命令。"
fi
if printf '%s\n' "$CONTENTS" | grep -qE "(^|/)data/app\.db$"; then
  echo "数据（data/app.db）在包里。"
else
  echo "注意：包里没有 data/app.db —— 如果是要搬记录，先确认 Mac 上 data 文件夹还在。"
fi
echo
echo "拷到服务器以后："
echo "  cd ~ && tar -xzf <这个文件> && cd $NAME && uv sync && ./start.sh"
