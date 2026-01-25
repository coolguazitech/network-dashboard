"""快速移除 topology_role 欄位"""
import asyncio
from sqlalchemy import text
from app.db.base import get_async_session

async def drop_topology_role():
    async for session in get_async_session():
        try:
            print("移除 topology_role 欄位...")
            await session.execute(text("ALTER TABLE client_comparisons DROP COLUMN IF EXISTS pre_topology_role"))
            await session.execute(text("ALTER TABLE client_comparisons DROP COLUMN IF EXISTS post_topology_role"))
            await session.commit()
            print("✅ 完成！")
        except Exception as e:
            print(f"❌ 錯誤: {e}")
            await session.rollback()
        finally:
            break

asyncio.run(drop_topology_role())
