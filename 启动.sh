#!/usr/bin/env bash
# Linux（Ubuntu Server 等）上用这个启动课时记录平台（Mac 上用 启动.command）
#
# 用法：在项目目录里敲  ./启动.sh
# 想让它开机自启、关掉终端也不停：sudo ./scripts/安装服务.sh
cd "$(dirname "$0")" || exit 1

if [ -x .venv/bin/python ]; then
  .venv/bin/python main.py
elif command -v uv >/dev/null 2>&1; then
  echo "第一次跑，正在装运行环境（要联网，稍等一下）……"
  if ! uv sync; then
    echo "装失败了，看看上面的报错。装好以后再跑一次 ./启动.sh"
    read -r -p "按回车键关闭窗口"
    exit 1
  fi
  .venv/bin/python main.py
else
  echo "没找到运行环境（.venv），也没找到 uv。"
  echo "先装 uv： curl -LsSf https://astral.sh/uv/install.sh | sh"
  echo "重开一个终端，再回到项目目录跑 ./启动.sh"
  read -r -p "按回车键关闭窗口"
fi
