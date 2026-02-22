#!/bin/sh
set -e

# 自動執行資料庫遷移（冪等，已是最新版則不做任何事）
echo "Running alembic upgrade head..."
if alembic upgrade head; then
    echo "Alembic migration completed."
else
    echo "WARNING: Alembic migration failed (DB may already be up-to-date). Continuing startup..."
fi

# 啟動應用
exec "$@"
