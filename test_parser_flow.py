"""
Test script to verify Parser → CollectionRecord flow.

This script:
1. Simulates raw API output
2. Calls CiscoNxosTransceiverParser.parse()
3. Saves to CollectionRecord
4. Verifies the results
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import select

from app.core.enums import MaintenancePhase, PlatformType, VendorType
from app.db.base import get_session_context
from app.db.models import CollectionRecord
from app.parsers.registry import parser_registry, auto_discover_parsers


# Simulated raw API output from Cisco NX-OS device
MOCK_API_OUTPUT = """Ethernet1/1
    transceiver is present
    type is QSFP-40G-SR4
    name is CISCO-FINISAR
    part number is FTLX8571D3BCL-C2
    serial number is FNS12345678
    Temperature            30.32 C
    Voltage                3.28 V
    Current                6.45 mA
    Tx Power               -1.23 dBm
    Rx Power               -2.45 dBm

Ethernet1/2
    transceiver is present
    type is QSFP-40G-SR4
    name is CISCO-FINISAR
    part number is FTLX8571D3BCL-C2
    serial number is FNS87654321
    Temperature            28.50 C
    Voltage                3.30 V
    Current                6.30 mA
    Tx Power               -0.95 dBm
    Rx Power               -1.87 dBm
"""


async def test_parser_flow() -> None:
    """
    Test the complete flow: raw_output → parse → CollectionRecord → DB.
    """
    print("=" * 70)
    print("🧪 Testing Parser Flow: raw_output → Parse → CollectionRecord")
    print("=" * 70)

    # Step 0: Auto-discover parsers
    print("\n[Step 0] 🔎 Auto-discovering parsers...")
    try:
        auto_discover_parsers()
        print(f"✅ Parser auto-discovery complete")
        
        # Print registered parsers
        registered = parser_registry.list_parsers()
        print(f"   Registered parsers: {len(registered)}")
        for parser_key in registered:
            print(f"   - {parser_key.vendor.value} / {parser_key.platform.value} / {parser_key.indicator_type}")
    except Exception as e:
        print(f"⚠️  Auto-discovery warning: {e}")

    # Step 1: Get parser from registry
    print("\n[Step 1] 🔍 Getting Parser from Registry...")
    try:
        parser = parser_registry.get(
            vendor=VendorType.CISCO,
            platform=PlatformType.CISCO_NXOS,
            indicator_type="transceiver",
        )
        
        if parser is None:
            print(f"❌ Parser not found in registry")
            print(f"   Available parsers:")
            for p in parser_registry.list_parsers():
                print(f"   - {p}")
            return
            
        print(f"✅ Parser Found: {parser.__class__.__name__}")
    except Exception as e:
        print(f"❌ Parser lookup failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 2: Parse raw output
    print("\n[Step 2] 📝 Parsing raw API output...")
    print(f"   Raw output length: {len(MOCK_API_OUTPUT)} chars")

    try:
        parsed_results = parser.parse(MOCK_API_OUTPUT)
        print(f"✅ Parse Successful! Got {len(parsed_results)} results")

        for i, result in enumerate(parsed_results, 1):
            print(f"\n   Result {i}:")
            print(f"   - Interface: {result.interface_name}")
            print(f"   - Tx Power: {result.tx_power} dBm")
            print(f"   - Rx Power: {result.rx_power} dBm")
            print(f"   - Temperature: {result.temperature} °C")
            print(f"   - Voltage: {result.voltage} V")
            print(f"   - Serial: {result.serial_number}")
            print(f"   - Part Number: {result.part_number}")
    except Exception as e:
        print(f"❌ Parse failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 3: Convert to dict for JSON storage
    print("\n[Step 3] 🔄 Converting parsed data to JSON format...")
    try:
        parsed_data_dicts = [result.model_dump() for result in parsed_results]
        print(f"✅ Converted to {len(parsed_data_dicts)} JSON objects")
        print(f"   Sample: {parsed_data_dicts[0]}")
    except Exception as e:
        print(f"❌ Conversion failed: {e}")
        return

    # Step 4: Save to CollectionRecord
    print("\n[Step 4] 💾 Saving to CollectionRecord...")
    try:
        async with get_session_context() as session:
            # Create CollectionRecord
            record = CollectionRecord(
                indicator_type="transceiver",
                switch_hostname="switch-01",
                phase=MaintenancePhase.POST,
                maintenance_id="maint-20240118-001",
                raw_data=MOCK_API_OUTPUT,
                parsed_data=parsed_data_dicts,
                collected_at=datetime.now(),
            )

            session.add(record)
            await session.commit()

            print(f"✅ Saved to database!")
            print(f"   Record ID: {record.id}")
            print(f"   Timestamp: {record.collected_at}")
    except Exception as e:
        print(f"❌ Database save failed: {e}")
        import traceback
        traceback.print_exc()
        return

    # Step 5: Verify by querying back
    print("\n[Step 5] ✔️ Verifying by querying from database...")
    try:
        async with get_session_context() as session:
            stmt = select(CollectionRecord).where(
                CollectionRecord.switch_hostname == "switch-01",
                CollectionRecord.indicator_type == "transceiver",
            )
            result = await session.execute(stmt)
            records = result.scalars().all()

            print(f"✅ Found {len(records)} record(s) in database")

            for record in records:
                print(f"\n   Record #{record.id}:")
                print(f"   - Indicator: {record.indicator_type}")
                print(f"   - Switch: {record.switch_hostname}")
                print(f"   - Phase: {record.phase.value}")
                print(f"   - Maintenance ID: {record.maintenance_id}")
                print(f"   - Collected At: {record.collected_at}")
                print(f"   - Raw Data Length: {len(record.raw_data) if record.raw_data else 0} chars")
                print(f"   - Parsed Data: {len(record.parsed_data) if record.parsed_data else 0} items")

                if record.parsed_data:
                    for idx, item in enumerate(record.parsed_data, 1):
                        print(f"\n      Parsed Item {idx}:")
                        for key, value in item.items():
                            print(f"      - {key}: {value}")
    except Exception as e:
        print(f"❌ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return

    print("\n" + "=" * 70)
    print("✅ All tests passed! Parser flow is working correctly!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(test_parser_flow())
