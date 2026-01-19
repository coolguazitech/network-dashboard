"""
Database initialization script.

Creates all tables defined in models.py.
Run this once before starting the application.
"""
import asyncio

from app.db.base import init_db


async def main() -> None:
    """Initialize database."""
    print("Initializing database...")
    try:
        await init_db()
        print("✅ Database initialized successfully!")
        print("   All tables created.")
    except Exception as e:
        print(f"❌ Error initializing database: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
