"""
Run database migration for checkpoints and reference clients.
"""
import asyncio
from sqlalchemy import text
from app.db.base import engine

async def run_migration():
    """執行遷移腳本。"""
    
    with open('migrations/add_checkpoints_and_reference_clients.sql', 'r') as f:
        sql = f.read()
    
    async with engine.begin() as conn:
        for statement in sql.split(';'):
            if statement.strip():
                await conn.execute(text(statement))
    
    print('✅ Migration completed successfully')

if __name__ == "__main__":
    asyncio.run(run_migration())
