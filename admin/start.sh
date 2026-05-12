#!/bin/bash
# 啟動網站後台管理伺服器
# 用法: WEBSITE_ADMIN_PASSWORD=你的密碼 ./start.sh
# 或： ./start.sh [密碼]  （不建議常駐使用，密碼會出現在 ps）

cd "$(dirname "$0")"
PASSWORD="${1:-${WEBSITE_ADMIN_PASSWORD:-}}"
PORT=8088

echo "啟動後台管理伺服器..."
if [ -n "$PASSWORD" ]; then
  export WEBSITE_ADMIN_PASSWORD="$PASSWORD"
fi
exec /opt/homebrew/bin/python3 admin_server.py --port "$PORT"
