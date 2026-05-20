#!/bin/bash
# 终端启动: bash start.sh

cd "$(dirname "$0")"
chmod +x "启动茅台抢单.command" 2>/dev/null || true
exec ./启动茅台抢单.command
