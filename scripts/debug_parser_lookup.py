#!/usr/bin/env python3
"""Debug parser lookup issue."""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.db.base import get_session_context
from app.repositories.switch import SwitchRepository
from app.parsers.registry import parser_registry

# Import plugins
import app.parsers.plugins  # noqa: F401


async def main():
    async with get_session_context() as session:
        switch_repo = SwitchRepository(session)
        switches = await switch_repo.get_active_switches()

        print(f"Found {len(switches)} active switches\n")

        for switch in switches:
            print(f"Switch: {switch.hostname}")
            print(f"  vendor (type): {type(switch.vendor)}")
            print(f"  vendor (value): {switch.vendor}")
            print(f"  platform (type): {type(switch.platform)}")
            print(f"  platform (value): {switch.platform}")

            # Try to get parser
            indicator_type = "transceiver"
            parser = parser_registry.get(
                vendor=switch.vendor,
                platform=switch.platform,
                indicator_type=indicator_type,
            )

            if parser:
                print(f"  ✅ Found {indicator_type} parser: {parser.__class__.__name__}")
            else:
                print(f"  ❌ No {indicator_type} parser found!")
                print(f"     Looking for: {switch.vendor}/{switch.platform}/{indicator_type}")

                # Try to understand why
                from app.parsers.protocols import ParserKey

                key = ParserKey(
                    vendor=switch.vendor,
                    platform=switch.platform,
                    indicator_type=indicator_type,
                )
                print(f"     ParserKey: {key}")
                print(f"     ParserKey hash: {hash(key)}")

                # List available keys
                all_keys = parser_registry.list_parsers()
                matching = [k for k in all_keys if k.indicator_type == indicator_type]
                print(f"     Available {indicator_type} parsers:")
                for k in matching:
                    print(f"       - {k.vendor}/{k.platform} (hash: {hash(k)})")
                    if k.vendor == switch.vendor and k.platform == switch.platform:
                        print(f"         THIS SHOULD MATCH!")
                        print(f"         k.vendor == switch.vendor: {k.vendor == switch.vendor}")
                        print(f"         k.platform == switch.platform: {k.platform == switch.platform}")
                        print(f"         k == key: {k == key}")

            print()


if __name__ == "__main__":
    asyncio.run(main())
