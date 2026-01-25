#!/usr/bin/env python3
"""Check database values."""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.db.base import get_session_context
from app.db.models import Switch
from sqlalchemy import select


async def main():
    async with get_session_context() as session:
        stmt = select(Switch)
        result = await session.execute(stmt)
        switches = result.scalars().all()

        print("Switches in database:")
        for switch in switches:
            print(f"\nHostname: {switch.hostname}")
            print(f"  IP: {switch.ip_address}")
            print(f"  Vendor (type): {type(switch.vendor).__name__}")
            print(f"  Vendor (value): {switch.vendor}")
            print(f"  Vendor (repr): {repr(switch.vendor)}")
            print(f"  Platform (type): {type(switch.platform).__name__}")
            print(f"  Platform (value): {switch.platform}")
            print(f"  Platform (repr): {repr(switch.platform)}")


if __name__ == "__main__":
    asyncio.run(main())
