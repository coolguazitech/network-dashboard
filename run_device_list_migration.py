"""
執行 maintenance_device_list 表重新設計 migration。

用法：
    python run_device_list_migration.py
"""
import asyncio
from pathlib import Path
from sqlalchemy import text
from app.db.base import engine


async def run_migration():
    """執行 migration SQL。"""
    migration_path = Path(__file__).parent / "migrations"
    migration_file = migration_path / "redesign_maintenance_device_list.sql"
    
    if not migration_file.exists():
        print(f"❌ Migration 檔案不存在: {migration_file}")
        return
    
    sql_content = migration_file.read_text(encoding="utf-8")
    
    # 移除註解行
    lines = []
    for line in sql_content.split('\n'):
        line_stripped = line.strip()
        if not line_stripped.startswith('--'):
            lines.append(line)
    sql_content = '\n'.join(lines)
    
    # 分割 SQL 語句
    statements = []
    for s in sql_content.split(';'):
        s = s.strip()
        if s:
            statements.append(s)
    
    async with engine.begin() as conn:
        for stmt in statements:
            if stmt:
                try:
                    print(f"執行: {stmt[:60]}...")
                    await conn.execute(text(stmt))
                    print("  ✓ 成功")
                except Exception as e:
                    print(f"  ⚠ 警告: {e}")
        
        await conn.commit()
    
    print("\n✅ Migration 完成！")


if __name__ == "__main__":
    asyncio.run(run_migration())
