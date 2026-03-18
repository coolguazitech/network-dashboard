#!/bin/sh
set -e

# =============================================================================
# 自動執行資料庫遷移
#
# 處理三種情境：
# 1. alembic 管理的 DB 且已在 head → 跳過
# 2. alembic 管理的 DB 但不在 head → upgrade
# 3. create_all 建的 DB（無 alembic_version 表）→ 先 stamp 再 upgrade
# =============================================================================

echo "Checking database migration state..."

# 用 Python 偵測 DB 狀態，避免 alembic CLI 的 INFO log 干擾判斷
DB_STATE=$(python3 -c "
from sqlalchemy import create_engine, inspect, text
from app.core.config import settings

engine = create_engine(settings.database_url)
try:
    with engine.connect() as conn:
        tables = inspect(conn).get_table_names()
        has_alembic = 'alembic_version' in tables
        has_tables = 'collection_batches' in tables

        if has_alembic:
            row = conn.execute(text('SELECT version_num FROM alembic_version')).fetchone()
            if row:
                print(f'stamped:{row[0]}')
            else:
                # alembic_version 表存在但是空的
                print('create_all' if has_tables else 'fresh')
        elif has_tables:
            print('create_all')
        else:
            print('fresh')
finally:
    engine.dispose()
" 2>/dev/null) || DB_STATE="unknown"

echo "Database state: $DB_STATE"

case "$DB_STATE" in
    stamped:*)
        CURRENT_REV="${DB_STATE#stamped:}"
        HEAD_REV=$(python3 -c "
from alembic.config import Config
from alembic.script import ScriptDirectory
cfg = Config('alembic.ini')
script = ScriptDirectory.from_config(cfg)
print(script.get_heads()[0])
" 2>/dev/null) || HEAD_REV=""

        if [ "$CURRENT_REV" = "$HEAD_REV" ]; then
            echo "Database is already at latest migration ($CURRENT_REV). Skipping."
        else
            echo "Database at $CURRENT_REV, upgrading to $HEAD_REV..."
            if alembic upgrade head 2>&1; then
                echo "Alembic migration completed."
            else
                echo "WARNING: Alembic migration failed. Continuing startup..."
            fi
        fi
        ;;

    create_all)
        # create_all DB：stamp 到修正 migration 之前，然後 upgrade 跑 patch migrations
        echo "Detected create_all database (no alembic_version). Stamping..."
        # stamp 到最後一個「create_all 已涵蓋」的 revision
        # 之後的 i4c5d6e7f8g9, j5d6e7f8g9h0, k6e7f8g9h0i1 有防禦性檢查，安全執行
        if alembic stamp 9622f91e33ff 2>&1; then
            echo "Stamped to 9622f91e33ff. Running pending migrations..."
            if alembic upgrade head 2>&1; then
                echo "Alembic migration completed (create_all DB patched)."
            else
                echo "WARNING: Alembic upgrade failed on create_all DB. Continuing startup..."
            fi
        else
            echo "WARNING: Alembic stamp failed. Continuing startup..."
        fi
        ;;

    fresh)
        # 全新 DB → app 會用 create_all 建表，這裡不做事
        echo "Fresh database. Tables will be created by application startup."
        ;;

    *)
        echo "WARNING: Could not determine DB state ($DB_STATE). Attempting upgrade..."
        if alembic upgrade head 2>&1; then
            echo "Alembic migration completed."
        else
            echo "WARNING: Alembic migration failed. Continuing startup..."
        fi
        ;;
esac

# 啟動應用
exec "$@"
