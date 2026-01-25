from sqlalchemy import text
from app.db.base import engine
import asyncio

async def check_phase():
    async with engine.begin() as conn:
        result = await conn.execute(text("SHOW COLUMNS FROM collection_records LIKE 'phase'"))
        row = result.fetchone()
        print(f"Column info: {row}")

if __name__ == "__main__":
    asyncio.run(check_phase())
