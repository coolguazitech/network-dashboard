#!/bin/sh
set -e

# =============================================================================
# 自動執行資料庫遷移
#
# 處理四種情境：
# 1. alembic 管理的 DB 且已在 head → 跳過
# 2. alembic 管理的 DB 但不在 head → upgrade
# 3. create_all 建的 DB（無 alembic_version 表）→ 先 stamp 再 upgrade
# 4. 全新空 DB → create_all 建表 + stamp head
#
# K8s 相容：啟動前等待 DB 就緒（最多 60 秒）
# =============================================================================

# ── Step 0: 等待 DB 就緒 ────────────────────────────────────────────────────
echo "Waiting for database to be ready..."
MAX_RETRIES=30
RETRY_INTERVAL=2
RETRY_COUNT=0

while [ "$RETRY_COUNT" -lt "$MAX_RETRIES" ]; do
    if python3 -c "
from sqlalchemy import create_engine, text
from app.core.config import settings
engine = create_engine(settings.database_url, connect_args={'connect_timeout': 3})
try:
    with engine.connect() as conn:
        conn.execute(text('SELECT 1'))
    print('ok')
finally:
    engine.dispose()
" 2>/dev/null | grep -q "ok"; then
        echo "Database is ready."
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "  Database not ready (attempt $RETRY_COUNT/$MAX_RETRIES). Retrying in ${RETRY_INTERVAL}s..."
    sleep "$RETRY_INTERVAL"
done

if [ "$RETRY_COUNT" -ge "$MAX_RETRIES" ]; then
    echo "ERROR: Database not ready after $((MAX_RETRIES * RETRY_INTERVAL))s. Starting app anyway..."
fi

# ── Step 1: 偵測 DB 狀態 ────────────────────────────────────────────────────
echo "Checking database migration state..."

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

# ── Step 2: 執行對應動作 ────────────────────────────────────────────────────
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
        # 之後的 migration 有防禦性檢查（_col_exists / _index_exists），安全執行
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
        # 全新空 DB → 用 create_all 建立所有表，然後 stamp 到 head
        echo "Fresh database detected. Creating all tables..."
        if python3 -c "
from sqlalchemy import create_engine
from app.db.base import Base
from app.db import models  # noqa: register all models
from app.core.config import settings

engine = create_engine(settings.database_url)
Base.metadata.create_all(bind=engine)
engine.dispose()
print('Tables created successfully')
" 2>&1; then
            echo "Tables created. Stamping alembic to head..."
            if alembic stamp head 2>&1; then
                echo "Alembic stamped to head. Database fully initialized."
            else
                echo "WARNING: Alembic stamp failed after create_all. Continuing startup..."
            fi
        else
            echo "ERROR: create_all failed. App will retry on startup..."
        fi
        ;;

    *)
        # DB 連線成功但狀態不明 → 嘗試 upgrade
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
