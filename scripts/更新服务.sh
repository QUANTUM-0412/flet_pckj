#!/usr/bin/env bash
# 从 GitHub 拉最新代码 → 更新依赖 → 重启服务。
# 服务器的日常更新就用这个，不用再打包上传。
#
# 用法：
#   ./scripts/更新服务.sh                # 全套
#   ./scripts/更新服务.sh --no-restart   # 只更新，不碰服务（没装 systemd 服务时用）
#
# 注意：服务器上不要手改代码，改了会挡住 git pull。
set -eu

cd "$(dirname "$0")/.." || exit 1

if [ ! -d .git ]; then
  echo "这个目录不是 git 仓库（可能是用部署包解出来的）。"
  echo "想这样更新，先按 docs/UbuntuServer部署.md 里的「用 GitHub 托管代码」改成 git clone。"
  exit 1
fi

if [ -n "$(git status --porcelain)" ]; then
  echo "注意：这个目录里有没提交的改动，git pull 可能会失败。"
  echo "（服务器上一般不该有；下面先列出来你看看）"
  git status --short
  echo
fi

echo "==> 拉最新代码"
git pull --ff-only

echo "==> 更新依赖"
if command -v uv >/dev/null 2>&1; then
  uv sync
else
  echo "没找到 uv，跳过装依赖（装了 uv 才会自动更新）。"
fi

if [ "${1:-}" = "--no-restart" ]; then
  echo "按 --no-restart 要求，没有动服务。"
  exit 0
fi

if command -v systemctl >/dev/null 2>&1 && systemctl list-unit-files class-hours.service >/dev/null 2>&1; then
  echo "==> 重启服务"
  sudo systemctl restart class-hours
  systemctl --no-pager --lines=3 status class-hours || true
else
  echo "没装 class-hours 服务，先不用重启。"
  echo "（sudo ./scripts/安装服务.sh 可以装成开机自启的服务）"
fi
