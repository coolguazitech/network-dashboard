#!/bin/sh
set -e

# =============================================================================
# 自動執行資料庫遷移
#
# 處理兩種情境：
# 1. alembic 管理的 DB → 直接 upgrade head
# 2. create_all 建的 DB（無 alembic_version 表）→ 先 stamp 再 upgrade
# =============================================================================

echo "Checking database migration state..."

# 嘗試取得目前 alembic 版本
CURRENT=$(alembic current 2>&1) || true

if echo "$CURRENT" | grep -q "(head)"; then
    echo "Database is already at latest migration. Skipping."
elif echo "$CURRENT" | grep -q "[a-z0-9]"; then
    # 有版本但不是 head → 需要 upgrade
    echo "Running alembic upgrade head..."
    if alembic upgrade head; then
        echo "Alembic migration completed."
    else
        echo "WARNING: Alembic migration failed. Continuing startup..."
    fi
else
    # 沒有 alembic_version 或表是空的
    # 檢查是否是 create_all 建的 DB（主表已存在）
    HAS_TABLES=$(python3 -c "
from sqlalchemy import create_engine, inspect
from app.core.config import settings
engine = create_engine(settings.database_url)
insp = inspect(engine)
tables = insp.get_table_names()
print('yes' if 'collection_batches' in tables else 'no')
engine.dispose()
" 2>/dev/null) || HAS_TABLES="no"

    if [ "$HAS_TABLES" = "yes" ]; then
        # create_all DB：stamp 到最新版，然後跑 upgrade（確保差異欄位被修正）
        echo "Detected create_all database (no alembic_version). Stamping to latest..."
        # stamp 到 head 前一版，然後 upgrade 跑最後幾個 migration
        # 找到最後一個「建表」migration（9622f91e33ff），stamp 到那裡
        # 這樣 i4c5d6e7f8g9, j5d6e7f8g9h0, k6e7f8g9h0i1 會被執行
        alembic stamp 9622f91e33ff 2>/dev/null || true
        echo "Running pending migrations..."
        if alembic upgrade head; then
            echo "Alembic migration completed (create_all DB patched)."
        else
            echo "WARNING: Alembic migration failed on create_all DB. Continuing startup..."
        fi
    else
        # 全新 DB → 正常 upgrade（會建表）
        echo "Fresh database detected. Running alembic upgrade head..."
        if alembic upgrade head; then
            echo "Alembic migration completed."
        else
            echo "WARNING: Alembic migration failed. Continuing startup..."
        fi
    fi
fi

# 啟動應用
exec "$@"
