#!/usr/bin/env python3
"""
Initialize test database with tables and sample switches.

This script:
1. Creates all database tables
2. Adds test switches that match Mock Server devices
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.enums import PlatformType, SiteType, VendorType
from app.db.base import init_db, get_session_context
from app.db.models import Switch


async def create_test_switches():
    """Create test switches matching Mock Server scenarios."""
    async with get_session_context() as session:
        # Check if switches already exist
        from sqlalchemy import select

        stmt = select(Switch).where(Switch.hostname == "switch-new-01")
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            print("✅ Test switches already exist")
            return

        # Create test switches
        switches = [
            Switch(
                hostname="switch-new-01",
                ip_address="10.0.1.1",
                vendor=VendorType.CISCO,
                platform=PlatformType.CISCO_NXOS,
                site=SiteType.T_SITE,
                is_active=True,
                description="Cisco Nexus Test Switch",
            ),
            Switch(
                hostname="switch-new-02",
                ip_address="10.0.1.2",
                vendor=VendorType.HPE,
                platform=PlatformType.HPE_COMWARE,
                site=SiteType.T_SITE,
                is_active=True,
                description="HPE Comware Test Switch",
            ),
        ]

        session.add_all(switches)
        await session.commit()

        print("✅ Created 2 test switches:")
        for switch in switches:
            print(f"   - {switch.hostname} ({switch.ip_address}) - {switch.vendor}/{switch.platform}")


async def main():
    """Main entry point."""
    print("=" * 60)
    print("Initializing Test Database")
    print("=" * 60)

    # Step 1: Create tables
    print("\n1. Creating database tables...")
    try:
        await init_db()
        print("✅ Database tables created")
    except Exception as e:
        print(f"⚠️  Tables may already exist: {e}")

    # Step 2: Create test switches
    print("\n2. Creating test switches...")
    await create_test_switches()

    print("\n" + "=" * 60)
    print("✅ Database initialization complete!")
    print("=" * 60)
    print("\nYou can now run:")
    print("  python scripts/seed_test_data.py --scenario 01_baseline")


if __name__ == "__main__":
    asyncio.run(main())
