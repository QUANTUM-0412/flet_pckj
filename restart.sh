#!/usr/bin/env bash
# Linux（包括树莓派）上的安全重启入口。
cd "$(dirname "$0")" || exit 1
exec ./scripts/restart-server.sh
