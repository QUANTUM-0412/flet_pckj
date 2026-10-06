#!/bin/bash
# 双击这个文件就能启动课时记录平台
cd "$(dirname "$0")" || exit 1

if [ -x .venv/bin/python ]; then
  .venv/bin/python main.py
else
  echo "没找到运行环境（.venv 文件夹）。"
  echo "请在项目目录里先执行： uv sync"
  read -r -p "按回车键关闭窗口"
fi
