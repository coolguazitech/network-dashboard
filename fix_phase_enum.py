import asyncio
from sqlalchemy import text
from app.db.base import engine

async def fix_phase():
    async with engine.begin() as conn:
        print("Altering collection_records table...")
        # 將 phase 改為 VARCHAR 以避免 ENUM 問題
        await conn.execute(text(
            "ALTER TABLE collection_records MODIFY COLUMN phase VARCHAR(20) NOT NULL DEFAULT 'new'"
        ))
        
        try:
            await conn.execute(text(
                "ALTER TABLE indicator_results MODIFY COLUMN phase VARCHAR(20) NOT NULL DEFAULT 'new'"
            ))
            print("Altered indicator_results table.")
        except Exception as e:
            print(f"Skipping indicator_results: {e}")

        print("Schema updated successfully.")

if __name__ == "__main__":
    asyncio.run(fix_phase())
