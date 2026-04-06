#!/bin/bash
# 啟動網站後台管理伺服器
# 用法: ./start.sh [密碼]

cd "$(dirname "$0")"
PASSWORD="${1:-whalelawyer}"
PORT=8088

echo "啟動後台管理伺服器..."
exec /opt/homebrew/bin/python3 admin_server.py --port "$PORT" --password "$PASSWORD"
