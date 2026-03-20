"""
Seed a ~400-device topology for TEST-SNMP-FIX maintenance.

Topology structure (tree-like enterprise network):
  - 4 Core switches (CORE-01 ~ CORE-04), full mesh
  - 16 AGG switches (AGG-01 ~ AGG-16), each dual-uplink to 2 Cores
  - 384 Edge switches (EDGE-001 ~ EDGE-384), each uplink to 1 AGG
  Total: 404 devices

Link status mix:
  - Core<->AGG: all expected_pass
  - AGG<->Edge: most expected_pass, ~20 expected_fail (missing links)
  - Some discovered-only links (not in expectations)

Indicator failures seeded on ~15 devices for red-node testing.
"""
import asyncio
import random
from datetime import datetime, timezone

from sqlalchemy import text, delete as sa_delete

from app.db.base import get_session_context, engine
from app.db.models import (
    Base,
    CollectionBatch,
    LatestCollectionBatch,
    MaintenanceDeviceList,
    MaintenanceConfig,
    NeighborRecord,
    UplinkExpectation,
    InterfaceErrorRecord,
)

MAINT = "TEST-SNMP-FIX"
random.seed(42)
now = datetime.now(timezone.utc)


def build_topology():
    """Build devices, links, and expectations."""
    devices = []  # (hostname, ip, vendor)
    lldp_links = []  # (src, local_if, dst, remote_if)
    expectations = []  # (hostname, local_if, expected_neighbor, expected_if)

    # === Core switches (4) - full mesh ===
    cores = []
    for i in range(1, 5):
        hostname = f"CORE-{i:02d}"
        ip = f"10.0.0.{i}"
        devices.append((hostname, ip, "HPE"))
        cores.append(hostname)

    # Core full mesh: each pair connected
    core_port = {}  # track next available port per core
    for c in cores:
        core_port[c] = 1
    for i, c1 in enumerate(cores):
        for c2 in cores[i + 1:]:
            p1 = core_port[c1]
            p2 = core_port[c2]
            core_port[c1] += 1
            core_port[c2] += 1
            lldp_links.append((c1, f"TenGE1/0/{p1}", c2, f"TenGE1/0/{p2}"))
            expectations.append((c1, f"TenGE1/0/{p1}", c2, f"TenGE1/0/{p2}"))
            expectations.append((c2, f"TenGE1/0/{p2}", c1, f"TenGE1/0/{p1}"))

    # === AGG switches (16) ===
    aggs = []
    for i in range(1, 17):
        hostname = f"AGG-{i:02d}"
        ip = f"10.1.{i}.1"
        devices.append((hostname, ip, "HPE"))
        aggs.append(hostname)

    # Each AGG dual-uplinks to 2 cores
    for idx, agg in enumerate(aggs):
        c1 = cores[idx % 4]
        c2 = cores[(idx + 1) % 4]
        p1 = core_port[c1]
        p2 = core_port[c2]
        core_port[c1] += 1
        core_port[c2] += 1
        # AGG uplink ports: GE1/0/49, GE1/0/50
        lldp_links.append((agg, "GE1/0/49", c1, f"TenGE1/0/{p1}"))
        lldp_links.append((agg, "GE1/0/50", c2, f"TenGE1/0/{p2}"))
        expectations.append((agg, "GE1/0/49", c1, f"TenGE1/0/{p1}"))
        expectations.append((agg, "GE1/0/50", c2, f"TenGE1/0/{p2}"))

    # === Edge switches (384, 24 per AGG) ===
    edges = []
    fail_edges = set()  # edges with missing uplinks (expected_fail)
    edge_idx = 0
    for agg_i, agg in enumerate(aggs):
        agg_port = 1
        for j in range(24):
            edge_idx += 1
            hostname = f"EDGE-{edge_idx:03d}"
            ip = f"10.2.{agg_i + 1}.{j + 10}"
            devices.append((hostname, ip, "HPE"))
            edges.append(hostname)

            local_if = "GE1/0/49"
            remote_if = f"GE1/0/{agg_port}"
            agg_port += 1

            # ~5% edges have missing uplinks (expected_fail)
            if random.random() < 0.05:
                fail_edges.add(hostname)
                # Add expectation but NO lldp link
                expectations.append((hostname, local_if, agg, remote_if))
            else:
                lldp_links.append((hostname, local_if, agg, remote_if))
                expectations.append((hostname, local_if, agg, remote_if))

    # Add ~10 "discovered" links (found by LLDP but not in expectations)
    # Simulate cross-connects between edges in same AGG
    for _ in range(10):
        e1 = random.choice(edges)
        e2 = random.choice(edges)
        if e1 != e2:
            lldp_links.append((e1, "GE1/0/48", e2, "GE1/0/48"))

    return devices, lldp_links, expectations, fail_edges


async def main():
    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    devices, lldp_links, expectations, fail_edges = build_topology()
    print(f"Devices: {len(devices)}")
    print(f"LLDP links: {len(lldp_links)}")
    print(f"Expectations: {len(expectations)}")
    print(f"Expected-fail edges: {len(fail_edges)}")

    async with get_session_context() as s:
        # === Clean existing data ===
        await s.execute(text(
            "DELETE FROM neighbor_records WHERE maintenance_id = :m"
        ), {"m": MAINT})
        await s.execute(text(
            "DELETE FROM uplink_expectations WHERE maintenance_id = :m"
        ), {"m": MAINT})
        await s.execute(text(
            "DELETE FROM collection_batches "
            "WHERE maintenance_id = :m "
            "AND collection_type IN ('get_uplink_lldp','get_uplink_cdp')"
        ), {"m": MAINT})
        await s.execute(text(
            "DELETE FROM latest_collection_batches "
            "WHERE maintenance_id = :m "
            "AND collection_type IN ('get_uplink_lldp','get_uplink_cdp')"
        ), {"m": MAINT})
        await s.execute(text(
            "DELETE FROM maintenance_device_list WHERE maintenance_id = :m"
        ), {"m": MAINT})

        # Ensure maintenance config exists
        existing = (await s.execute(text(
            "SELECT id FROM maintenance_configs WHERE maintenance_id = :m"
        ), {"m": MAINT})).first()
        if not existing:
            s.add(MaintenanceConfig(
                maintenance_id=MAINT,
                name="SNMP Fix Test (400 devices)",
            ))
            await s.flush()

        # === Create devices ===
        for hostname, ip, vendor in devices:
            s.add(MaintenanceDeviceList(
                maintenance_id=MAINT,
                new_hostname=hostname,
                new_ip_address=ip,
                new_vendor=vendor,
                old_hostname=hostname,
                old_ip_address=ip,
                old_vendor=vendor,
            ))
        await s.flush()
        print(f"Created {len(devices)} devices")

        # === Create LLDP neighbor records (batch by source) ===
        src_links = {}
        for src, local_if, dst, remote_if in lldp_links:
            src_links.setdefault(src, []).append((local_if, dst, remote_if))

        link_count = 0
        for src, links in src_links.items():
            batch = CollectionBatch(
                collection_type="get_uplink_lldp",
                switch_hostname=src,
                maintenance_id=MAINT,
                raw_data=f"LLDP neighbors: {len(links)} entries",
                item_count=len(links),
                collected_at=now,
            )
            s.add(batch)
            await s.flush()

            for local_if, dst, remote_if in links:
                s.add(NeighborRecord(
                    batch_id=batch.id,
                    switch_hostname=src,
                    maintenance_id=MAINT,
                    collected_at=now,
                    local_interface=local_if,
                    remote_hostname=dst,
                    remote_interface=remote_if,
                ))
                link_count += 1

            # Update latest batch pointer
            await s.execute(
                sa_delete(LatestCollectionBatch).where(
                    LatestCollectionBatch.maintenance_id == MAINT,
                    LatestCollectionBatch.collection_type == "get_uplink_lldp",
                    LatestCollectionBatch.switch_hostname == src,
                )
            )
            s.add(LatestCollectionBatch(
                maintenance_id=MAINT,
                collection_type="get_uplink_lldp",
                switch_hostname=src,
                batch_id=batch.id,
                data_hash="seed_topo",
                collected_at=now,
                last_checked_at=now,
            ))

        await s.flush()
        print(f"Created {link_count} LLDP neighbor records")

        # === Create uplink expectations ===
        for hostname, local_if, expected_neighbor, expected_if in expectations:
            s.add(UplinkExpectation(
                maintenance_id=MAINT,
                hostname=hostname,
                local_interface=local_if,
                expected_neighbor=expected_neighbor,
                expected_interface=expected_if,
            ))
        await s.flush()
        print(f"Created {len(expectations)} uplink expectations")

        # === Seed indicator failures (~15 devices with CRC growth) ===
        fail_devices = random.sample(
            [d[0] for d in devices if d[0].startswith("EDGE-")],
            min(15, len(devices)),
        )
        for hostname in fail_devices:
            # Create 2 error_count batches (need 2 for delta detection)
            for batch_num, crc_val in [(1, 100), (2, 150)]:
                batch = CollectionBatch(
                    collection_type="get_error_count",
                    switch_hostname=hostname,
                    maintenance_id=MAINT,
                    raw_data=f"Error count batch {batch_num}",
                    item_count=1,
                    collected_at=now,
                )
                s.add(batch)
                await s.flush()

                s.add(InterfaceErrorRecord(
                    batch_id=batch.id,
                    switch_hostname=hostname,
                    maintenance_id=MAINT,
                    collected_at=now,
                    interface_name="GE1/0/12",
                    crc_errors=crc_val,
                ))

                if batch_num == 2:
                    await s.execute(
                        sa_delete(LatestCollectionBatch).where(
                            LatestCollectionBatch.maintenance_id == MAINT,
                            LatestCollectionBatch.collection_type == "get_error_count",
                            LatestCollectionBatch.switch_hostname == hostname,
                        )
                    )
                    s.add(LatestCollectionBatch(
                        maintenance_id=MAINT,
                        collection_type="get_error_count",
                        switch_hostname=hostname,
                        batch_id=batch.id,
                        data_hash="seed_err",
                        collected_at=now,
                        last_checked_at=now,
                    ))

        await s.flush()
        print(f"Created CRC growth data for {len(fail_devices)} devices")
        print(f"  Fail devices: {', '.join(sorted(fail_devices)[:5])}...")

    print()
    print("=== Summary ===")
    print(f"  Maintenance: {MAINT}")
    print(f"  Devices: {len(devices)} (4 Core + 16 AGG + 384 Edge)")
    print(f"  LLDP links: {link_count}")
    print(f"  Uplink expectations: {len(expectations)}")
    print(f"  Expected-fail links: {len(fail_edges)} edges missing uplinks")
    print(f"  Red nodes (CRC growth): {len(fail_devices)}")
    print()
    print("Open topology at: http://localhost:8000 -> TEST-SNMP-FIX -> Topology")


asyncio.run(main())
