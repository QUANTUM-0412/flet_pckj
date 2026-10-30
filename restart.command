#!/bin/bash
# 快速重启正式服务：先停掉占着端口的旧进程，再正常启动。
cd "$(dirname "$0")" || exit 1
exec ./scripts/restart-server.sh
