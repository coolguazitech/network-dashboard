"""移除 ping_latency_ms、hostname 和 topology_role 欄位

使用此腳本來清理資料庫，移除不再使用的欄位。
"""
import asyncio
from sqlalchemy import text
from app.db.base import get_async_session


async def remove_columns():
    """移除 client_records 和 client_comparisons 表中不再使用的欄位。"""
    
    async for session in get_async_session():
        try:
            print("開始移除不需要的欄位...")
            
            # 移除 client_records 表的欄位
            print("  - 移除 client_records.ping_latency_ms")
            await session.execute(text("ALTER TABLE client_records DROP COLUMN IF EXISTS ping_latency_ms"))
            
            print("  - 移除 client_records.hostname")
            await session.execute(text("ALTER TABLE client_records DROP COLUMN IF EXISTS hostname"))
            
            # 移除 client_comparisons 表的欄位
            print("  - 移除 client_comparisons.pre_ping_latency_ms")
            await session.execute(text("ALTER TABLE client_comparisons DROP COLUMN IF EXISTS pre_ping_latency_ms"))
            
            print("  - 移除 client_comparisons.pre_hostname")
            await session.execute(text("ALTER TABLE client_comparisons DROP COLUMN IF EXISTS pre_hostname"))
            
            print("  - 移除 client_comparisons.post_ping_latency_ms")
            await session.execute(text("ALTER TABLE client_comparisons DROP COLUMN IF EXISTS post_ping_latency_ms"))
            
            print("  - 移除 client_comparisons.post_hostname")
            await session.execute(text("ALTER TABLE client_comparisons DROP COLUMN IF EXISTS post_hostname"))
            
            print("  - 移除 client_comparisons.pre_topology_role")
            await session.execute(text("ALTER TABLE client_comparisons DROP COLUMN IF EXISTS pre_topology_role"))
            
            print("  - 移除 client_comparisons.post_topology_role")
            await session.execute(text("ALTER TABLE client_comparisons DROP COLUMN IF EXISTS post_topology_role"))
            
            await session.commit()
            print("✅ 成功移除所有不需要的欄位！")
            
        except Exception as e:
            print(f"❌ 錯誤: {e}")
            await session.rollback()
        finally:
            break


if __name__ == "__main__":
    print("=" * 60)
    print("資料庫遷移：移除不再使用的欄位")
    print("=" * 60)
    asyncio.run(remove_columns())
