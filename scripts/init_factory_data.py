#!/usr/bin/env python3
"""
Initialize Factory Test Data for Network Dashboard.

This script:
1. Cleans up database (removes all maintenance except TEST-100)
2. Clears TEST-100's existing data
3. Creates 4 factory categories (EQP, AMHS, SNR, OTHERS)
4. Creates ALL switches (both OLD and NEW devices)
5. Creates 34 device mappings (OLD → NEW, some devices not replaced)
6. Generates 100 MAC addresses with various scenarios
7. Assigns MACs to categories
8. Configures expectations (uplink, version, port_channel, ARP)

Device Naming Convention:
- Replaced devices: SW-OLD-{number}-{type} → SW-NEW-{number}-{type}
- Not replaced: SW-OLD-{number}-{type} → SW-OLD-{number}-{type}
- IP ranges: OLD devices use 10.1.x.x, NEW devices use 10.2.x.x
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import delete, select
from app.db.base import get_session_context
from app.db.models import (
    MaintenanceDeviceList,
    MaintenanceMacList,
    ClientCategory,
    ClientCategoryMember,
    UplinkExpectation,
    VersionExpectation,
    PortChannelExpectation,
    ArpSource,
    CollectionBatch,
    IndicatorResult,
    ClientRecord,
    ClientComparison,
    MaintenanceConfig,
)
from app.core.enums import (
    ClientDetectionStatus, VendorType, PlatformType, TenantGroup,
)

# Import shared device configuration
from factory_device_config import (
    MAINTENANCE_ID,
    TARGET_VERSION,
    DEVICES_CONFIG,
    DEVICES_NOT_REPLACED,
    get_device_mappings,
    generate_mac_addresses,
)


def generate_uplink_topology(
    device_mappings: list[tuple[str, str, str, str]]
) -> list[tuple[str, str, str, str]]:
    """
    Generate uplink expectations based on network topology.

    Uses new_hostname from device_mappings for expectations.
    """
    expectations = []

    # Create hostname map (num → new_hostname)
    hostname_map = {}
    for old_h, old_ip, new_h, new_ip in device_mappings:
        num = int(old_h.split("-")[2])
        hostname_map[num] = new_h

    # EDGE → AGG uplinks
    edge_devices = [(n, t) for n, t in DEVICES_CONFIG.items()
                    if t in ["EQP", "AMHS", "SNR", "OTHERS"]]
    agg_devices = [(n, t) for n, t in DEVICES_CONFIG.items() if t == "AGG"]

    for idx, (edge_num, edge_type) in enumerate(edge_devices):
        edge_hostname = hostname_map[edge_num]

        # Round-robin to 2 AGG switches
        agg_idx_1 = idx % len(agg_devices)
        agg_idx_2 = (idx + 1) % len(agg_devices)

        agg_num_1 = agg_devices[agg_idx_1][0]
        agg_num_2 = agg_devices[agg_idx_2][0]

        expectations.append((
            edge_hostname,
            "XGE1/0/51",
            hostname_map[agg_num_1],
            f"XGE1/0/{idx + 1}"
        ))

        expectations.append((
            edge_hostname,
            "XGE1/0/52",
            hostname_map[agg_num_2],
            f"XGE1/0/{idx + 1}"
        ))

    # AGG → CORE uplinks
    core_devices = [(n, t) for n, t in DEVICES_CONFIG.items() if t == "CORE"]

    for idx, (agg_num, agg_type) in enumerate(agg_devices):
        agg_hostname = hostname_map[agg_num]

        expectations.append((
            agg_hostname,
            "HGE1/0/25",
            hostname_map[core_devices[0][0]],
            f"HGE1/0/{idx + 1}"
        ))

        expectations.append((
            agg_hostname,
            "HGE1/0/26",
            hostname_map[core_devices[1][0]],
            f"HGE1/0/{idx + 1}"
        ))

    return expectations


def generate_port_channel_expectations(
    device_mappings: list[tuple[str, str, str, str]]
) -> list[tuple[str, str, str]]:
    """Generate Port-Channel expectations (excluding CORE)."""
    expectations = []

    for old_h, old_ip, new_h, new_ip in device_mappings:
        device_type = new_h.split("-")[-1]

        if device_type == "CORE":
            continue  # CORE doesn't have Port-Channel
        elif device_type == "AGG":
            expectations.append((
                new_h,
                "BAGG1",
                "HGE1/0/25;HGE1/0/26"
            ))
        else:  # EDGE devices
            expectations.append((
                new_h,
                "BAGG1",
                "XGE1/0/51;XGE1/0/52"
            ))

    return expectations


async def cleanup_database(session):
    """Clean up database: remove all except TEST-100, clear TEST-100 data."""
    print("\n=== Phase 1: Database Cleanup ===")

    # Delete all maintenance-related data except TEST-100
    print("Removing other maintenance data...")
    tables_with_maintenance_id = [
        ClientComparison,
        ClientRecord,
        IndicatorResult,
        CollectionBatch,
        ArpSource,
        PortChannelExpectation,
        VersionExpectation,
        UplinkExpectation,
        ClientCategory,
        MaintenanceDeviceList,
        MaintenanceMacList,
        MaintenanceConfig,
    ]

    for table in tables_with_maintenance_id:
        stmt = delete(table).where(table.maintenance_id != MAINTENANCE_ID)
        result = await session.execute(stmt)
        print(f"  - Deleted {result.rowcount} rows from "
              f"{table.__tablename__}")

    # Delete ClientCategoryMember entries for categories not in TEST-100
    stmt = select(ClientCategory.id).where(
        ClientCategory.maintenance_id == MAINTENANCE_ID
    )
    result = await session.execute(stmt)
    test_100_category_ids = [row[0] for row in result.all()]

    if test_100_category_ids:
        stmt = delete(ClientCategoryMember).where(
            ClientCategoryMember.category_id.notin_(test_100_category_ids)
        )
    else:
        stmt = delete(ClientCategoryMember)
    result = await session.execute(stmt)
    print(f"  - Deleted {result.rowcount} rows from client_category_members")

    # Clear TEST-100's existing data
    print(f"\nClearing existing {MAINTENANCE_ID} data...")

    # First, delete ClientCategoryMember for TEST-100 categories
    if test_100_category_ids:
        stmt = delete(ClientCategoryMember).where(
            ClientCategoryMember.category_id.in_(test_100_category_ids)
        )
        result = await session.execute(stmt)
        print(f"  - Cleared {result.rowcount} rows from "
              f"client_category_members (TEST-100)")

    for table in tables_with_maintenance_id:
        stmt = delete(table).where(table.maintenance_id == MAINTENANCE_ID)
        result = await session.execute(stmt)
        print(f"  - Cleared {result.rowcount} rows from "
              f"{table.__tablename__}")

    await session.commit()
    print("✓ Database cleanup complete")


async def create_maintenance_config(session):
    """Create MaintenanceConfig entry."""
    print("\n=== Phase 1.5: Creating Maintenance Config ===")

    from datetime import datetime, timezone

    config = MaintenanceConfig(
        maintenance_id=MAINTENANCE_ID,
        name="Factory Test Maintenance",
        start_date=datetime.now(timezone.utc),
        is_active=True,
    )
    session.add(config)
    await session.commit()
    print(f"✓ Created MaintenanceConfig for {MAINTENANCE_ID}")


async def create_categories(session):
    """Create 4 factory categories."""
    print("\n=== Phase 2: Creating Categories ===")

    categories = [
        {
            "name": "EQP",
            "description": "Equipment",
            "color": "#3B82F6",
            "sort_order": 1
        },
        {
            "name": "AMHS",
            "description": "Automated Material Handling System",
            "color": "#10B981",
            "sort_order": 2
        },
        {
            "name": "SNR",
            "description": "Storage Network",
            "color": "#F59E0B",
            "sort_order": 3
        },
        {
            "name": "OTHERS",
            "description": "Other Devices",
            "color": "#6B7280",
            "sort_order": 4
        },
    ]

    for cat_data in categories:
        category = ClientCategory(
            maintenance_id=MAINTENANCE_ID,
            **cat_data
        )
        session.add(category)
        print(f"  ✓ Created category: {cat_data['name']}")

    await session.commit()
    print("✓ Categories created")


async def create_maintenance_device_list(session):
    """Create MaintenanceDeviceList entries (for frontend device list page)."""
    print("\n=== Phase 4.5: Creating Maintenance Device List ===")

    mappings_data = get_device_mappings()

    # Tenant group options for round-robin assignment
    tenant_groups = [TenantGroup.F18, TenantGroup.F6, TenantGroup.AP, TenantGroup.F14, TenantGroup.F12]

    for idx, (old_h, old_ip, new_h, new_ip) in enumerate(mappings_data):
        # Assign tenant_group based on device type or round-robin
        device_type = old_h.split("-")[-1]
        if device_type == "CORE":
            tg = TenantGroup.F18
        elif device_type == "AGG":
            tg = TenantGroup.F6
        else:
            # Round-robin for edge devices
            tg = tenant_groups[idx % len(tenant_groups)]

        device = MaintenanceDeviceList(
            maintenance_id=MAINTENANCE_ID,
            old_hostname=old_h,
            old_ip_address=old_ip,
            old_vendor="HPE",
            new_hostname=new_h,
            new_ip_address=new_ip,
            new_vendor="HPE",
            use_same_port=True,
            tenant_group=tg,
            is_reachable=None,  # Will be set by data collection
            description=None,
        )
        session.add(device)

    await session.commit()
    print(f"✓ Created {len(mappings_data)} entries in MaintenanceDeviceList (with tenant_group)")


async def create_mac_list(session):
    """Create 100 Client entries (IP + MAC + tenant_group) and assign to categories."""
    print("\n=== Phase 5: Creating Client List ===")

    stmt = select(ClientCategory).where(
        ClientCategory.maintenance_id == MAINTENANCE_ID
    )
    result = await session.execute(stmt)
    categories = {cat.name: cat for cat in result.scalars().all()}

    all_macs = generate_mac_addresses()

    total_clients = 0
    for category_name, client_list in all_macs.items():
        for mac_address, ip_address, tenant_group, description in client_list:
            # Map tenant_group string to enum
            tg_enum = TenantGroup(tenant_group)

            mac_entry = MaintenanceMacList(
                maintenance_id=MAINTENANCE_ID,
                mac_address=mac_address,
                ip_address=ip_address,
                tenant_group=tg_enum,
                detection_status=ClientDetectionStatus.NOT_CHECKED,
                description=description,
            )
            session.add(mac_entry)

        category = categories[category_name]
        for mac_address, ip_address, tenant_group, description in client_list:
            member = ClientCategoryMember(
                category_id=category.id,
                mac_address=mac_address,
                description=description,
            )
            session.add(member)

        total_clients += len(client_list)
        print(f"  ✓ Created {len(client_list)} clients for category "
              f"{category_name}")

    await session.commit()
    print(f"✓ Total {total_clients} clients created (IP + MAC + tenant_group)")


async def create_uplink_expectations_db(session):
    """Create uplink expectations based on topology."""
    print("\n=== Phase 6: Creating Uplink Expectations ===")

    device_mappings = get_device_mappings()
    uplinks = generate_uplink_topology(device_mappings)

    for hostname, local_if, neighbor, neighbor_if in uplinks:
        expectation = UplinkExpectation(
            maintenance_id=MAINTENANCE_ID,
            hostname=hostname,
            local_interface=local_if,
            expected_neighbor=neighbor,
            expected_interface=neighbor_if,
        )
        session.add(expectation)

    await session.commit()
    print(f"✓ Created {len(uplinks)} uplink expectations")


async def create_version_expectations_db(session):
    """Create version expectations (all devices upgrade to target version)."""
    print("\n=== Phase 7: Creating Version Expectations ===")

    device_mappings = get_device_mappings()

    for old_h, old_ip, new_h, new_ip in device_mappings:
        expectation = VersionExpectation(
            maintenance_id=MAINTENANCE_ID,
            hostname=new_h,  # Use new_hostname
            expected_versions=TARGET_VERSION,
        )
        session.add(expectation)

    await session.commit()
    print(f"✓ Created {len(device_mappings)} version expectations "
          f"(target: {TARGET_VERSION})")


async def create_port_channel_expectations_db(session):
    """Create Port-Channel expectations."""
    print("\n=== Phase 8: Creating Port-Channel Expectations ===")

    device_mappings = get_device_mappings()
    port_channels = generate_port_channel_expectations(device_mappings)

    for hostname, po_name, members in port_channels:
        expectation = PortChannelExpectation(
            maintenance_id=MAINTENANCE_ID,
            hostname=hostname,
            port_channel=po_name,
            member_interfaces=members,
        )
        session.add(expectation)

    await session.commit()
    print(f"✓ Created {len(port_channels)} Port-Channel expectations")


async def create_arp_sources_db(session):
    """Create ARP sources (both OLD and NEW CORE IPs)."""
    print("\n=== Phase 9: Creating ARP Sources ===")

    device_mappings = get_device_mappings()
    core_mappings = [(o, oi, n, ni) for o, oi, n, ni in device_mappings
                     if "CORE" in o]

    arp_sources = []
    for idx, (old_h, old_ip, new_h, new_ip) in enumerate(core_mappings):
        # Add OLD CORE
        arp_old = ArpSource(
            maintenance_id=MAINTENANCE_ID,
            hostname=old_h,
            priority=(idx + 1) * 10,
            description="OLD CORE device"
        )
        session.add(arp_old)
        arp_sources.append(arp_old)

        # Add NEW CORE (if different)
        if new_h != old_h:
            arp_new = ArpSource(
                maintenance_id=MAINTENANCE_ID,
                hostname=new_h,
                priority=(idx + 1) * 10 + 5,
                description="NEW CORE device"
            )
            session.add(arp_new)
            arp_sources.append(arp_new)

    await session.commit()
    print(f"✓ Created {len(arp_sources)} ARP sources (OLD and NEW CORE)")


async def print_summary(session):
    """Print initialization summary."""
    print("\n" + "=" * 60)
    print("INITIALIZATION SUMMARY")
    print("=" * 60)

    # Categories
    stmt = select(ClientCategory).where(
        ClientCategory.maintenance_id == MAINTENANCE_ID
    )
    result = await session.execute(stmt)
    categories = result.scalars().all()
    print(f"Categories: {len(categories)}")
    for cat in categories:
        print(f"  - {cat.name}: {cat.description}")

    # Clients (MAC + IP + tenant_group)
    stmt = select(MaintenanceMacList).where(
        MaintenanceMacList.maintenance_id == MAINTENANCE_ID
    )
    result = await session.execute(stmt)
    clients = result.scalars().all()
    print(f"\nClients (IP+MAC): {len(clients)}")

    # Maintenance Device List
    stmt = select(MaintenanceDeviceList).where(
        MaintenanceDeviceList.maintenance_id == MAINTENANCE_ID
    )
    result = await session.execute(stmt)
    devices = result.scalars().all()
    replaced = sum(1 for d in devices if d.old_hostname != d.new_hostname)
    same = sum(1 for d in devices if d.old_hostname == d.new_hostname)
    print(f"\nDevice List: {len(devices)}")
    print(f"  - Being replaced (OLD → NEW): {replaced}")
    print(f"  - NOT replaced (OLD → OLD): {same}")

    # Expectations
    stmt = select(UplinkExpectation).where(
        UplinkExpectation.maintenance_id == MAINTENANCE_ID
    )
    result = await session.execute(stmt)
    uplinks = result.scalars().all()
    print(f"\nUplink Expectations: {len(uplinks)}")

    stmt = select(VersionExpectation).where(
        VersionExpectation.maintenance_id == MAINTENANCE_ID
    )
    result = await session.execute(stmt)
    versions = result.scalars().all()
    print(f"Version Expectations: {len(versions)} "
          f"(all target: {TARGET_VERSION})")

    stmt = select(PortChannelExpectation).where(
        PortChannelExpectation.maintenance_id == MAINTENANCE_ID
    )
    result = await session.execute(stmt)
    port_channels = result.scalars().all()
    print(f"Port-Channel Expectations: {len(port_channels)}")

    stmt = select(ArpSource).where(
        ArpSource.maintenance_id == MAINTENANCE_ID
    )
    result = await session.execute(stmt)
    arp_sources = result.scalars().all()
    print(f"ARP Sources: {len(arp_sources)} (OLD and NEW CORE IPs)")

    print("\n" + "=" * 60)
    print("✓ Factory data initialization complete!")
    print("=" * 60)


async def main():
    """Main initialization function."""
    print("=" * 60)
    print("Network Dashboard - Factory Data Initialization")
    print("=" * 60)

    # 確保所有表存在（含新增的 typed tables）
    from app.db.base import init_db
    await init_db()

    async with get_session_context() as session:
        try:
            await cleanup_database(session)
            await create_maintenance_config(session)
            await create_categories(session)
            await create_maintenance_device_list(session)
            await create_mac_list(session)
            await create_uplink_expectations_db(session)
            await create_version_expectations_db(session)
            await create_port_channel_expectations_db(session)
            await create_arp_sources_db(session)
            await print_summary(session)
        except Exception as e:
            print(f"\n❌ Error during initialization: {e}")
            import traceback
            traceback.print_exc()
            raise


if __name__ == "__main__":
    asyncio.run(main())
