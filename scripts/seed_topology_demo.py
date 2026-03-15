"""
Seed script: 產生貼近真實場景的三層式拓樸測試資料。

架構：
  - Core:    2 台  (CORE-01 ~ CORE-02)，MLAG 互連
  - AGG:    32 台  (AGG-01 ~ AGG-32)，16 組各 2 台，組內 MLAG 互連
              Core ↔ AGG: 每對 Core-AGG 之間 1 條線
  - Edge:  320 台  (EDGE-001 ~ EDGE-320)，每組 20 台
              每台 Edge 與所屬組的 2 台 AGG fully meshed
  - Client: 5000 個 MAC，大部分接 Edge，少量接 Agg

連線統計：
  Core-Core:    1 條 (MLAG peer-link)
  AGG-AGG:     16 條 (16 組 MLAG peer-link)
  Core-AGG:    64 條 (2 Core × 32 AGG × 1 link)
  Edge-AGG:   640 條 (320×2)
  總計:       721 條

用法：
  python scripts/seed_topology_demo.py
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import random
import sys
from datetime import datetime, UTC
from pathlib import Path

# 讓 import app 正常運作
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select, text
from app.db.base import async_session_factory, engine
from app.db.models import (
    CollectionBatch,
    LatestCollectionBatch,
    MaintenanceConfig,
    MaintenanceDeviceList,
    MaintenanceMacList,
    NeighborRecord,
    UplinkExpectation,
)
from app.core.enums import TenantGroup, ClientDetectionStatus

MAINTENANCE_ID = "TOPO-DEMO"
MAINTENANCE_NAME = "拓樸示範 (354設備)"

# ── 拓樸定義 ──
N_CORE = 2
N_AGG_GROUPS = 16
N_AGG_PER_GROUP = 2   # 每組 2 台，共 32
N_EDGE_PER_GROUP = 20  # 每組 20 台，共 320
N_CLIENTS = 5000

VENDORS = ["Cisco-IOS", "Cisco-NXOS", "HPE"]


def gen_ip(prefix: str, idx: int) -> str:
    """10.{prefix}.x.y"""
    third = idx // 254
    fourth = (idx % 254) + 1
    return f"10.{prefix}.{third}.{fourth}"


def gen_mac(idx: int) -> str:
    """產生 MAC 地址"""
    b = idx.to_bytes(3, "big")
    return f"00:AA:BB:{b[0]:02X}:{b[1]:02X}:{b[2]:02X}"


def gen_client_ip(idx: int) -> str:
    """172.16.x.y"""
    third = idx // 254
    fourth = (idx % 254) + 1
    return f"172.16.{third}.{fourth}"


def build_topology():
    """
    建構三層拓樸。

    回傳:
      devices: list of dict (hostname, ip, vendor)
      links: list of (src_host, src_if, dst_host, dst_if)
      uplink_expectations: list of (hostname, local_if, expected_neighbor, expected_if)
      client_attachments: list of (mac, ip, switch_hostname, interface, vlan)
    """
    random.seed(42)  # 可重現

    devices = []
    links = []
    expectations = []

    # 追蹤每台設備下一個可用的 interface index
    next_if: dict[str, int] = {}

    def alloc_if(hostname: str, prefix: str = "Eth1") -> str:
        """分配下一個 interface"""
        idx = next_if.get(hostname, 1)
        next_if[hostname] = idx + 1
        return f"{prefix}/{idx}"

    # ── Core (2 台) ──
    cores = []
    for i in range(1, N_CORE + 1):
        hostname = f"CORE-{i:02d}"
        cores.append(hostname)
        devices.append({
            "hostname": hostname,
            "ip": gen_ip("1", i),
            "vendor": "Cisco-NXOS",
        })

    # Core 之間互連
    if len(cores) == 2:
        src_if = alloc_if(cores[0])
        dst_if = alloc_if(cores[1])
        links.append((cores[0], src_if, cores[1], dst_if))
        expectations.append((cores[0], src_if, cores[1], dst_if))

    # ── AGG (16 組 × 2 台 = 32 台) ──
    agg_groups: list[list[str]] = []  # [[AGG-01, AGG-02], [AGG-03, AGG-04], ...]
    agg_all: list[str] = []
    agg_idx = 0
    for g in range(N_AGG_GROUPS):
        group = []
        group_vendor = random.choice(["Cisco-NXOS", "Cisco-IOS"])
        for _ in range(N_AGG_PER_GROUP):
            agg_idx += 1
            hostname = f"AGG-{agg_idx:02d}"
            group.append(hostname)
            agg_all.append(hostname)
            devices.append({
                "hostname": hostname,
                "ip": gen_ip("2", agg_idx),
                "vendor": group_vendor,
            })
        agg_groups.append(group)

    # AGG 組內 MLAG peer-link（跟 Core 一樣兩台互連）
    for group in agg_groups:
        if len(group) == 2:
            src_if = alloc_if(group[0])
            dst_if = alloc_if(group[1])
            links.append((group[0], src_if, group[1], dst_if))
            expectations.append((group[0], src_if, group[1], dst_if))

    # Core ↔ AGG: 每對 Core-AGG 之間 1 條線
    N_CORE_AGG_LINKS = 1
    for core in cores:
        for agg in agg_all:
            for _ in range(N_CORE_AGG_LINKS):
                core_if = alloc_if(core)
                agg_if = alloc_if(agg)
                links.append((core, core_if, agg, agg_if))
                expectations.append((core, core_if, agg, agg_if))

    # ── Edge (16 組 × 20 台 = 320 台) ──
    edge_groups: list[list[str]] = []
    edges: list[str] = []
    edge_idx = 0
    for g in range(N_AGG_GROUPS):
        group = []
        group_edge_vendor = random.choice(VENDORS)
        for _ in range(N_EDGE_PER_GROUP):
            edge_idx += 1
            hostname = f"EDGE-{edge_idx:03d}"
            group.append(hostname)
            edges.append(hostname)
            devices.append({
                "hostname": hostname,
                "ip": gen_ip("3", edge_idx),
                "vendor": group_edge_vendor,
            })
        edge_groups.append(group)

    # Edge ↔ AGG: 每台 Edge 與所屬組的 2 台 AGG fully meshed
    for g in range(N_AGG_GROUPS):
        for edge in edge_groups[g]:
            for agg in agg_groups[g]:
                edge_if = alloc_if(edge, "Gi0")
                agg_if = alloc_if(agg)
                links.append((edge, edge_if, agg, agg_if))
                expectations.append((edge, edge_if, agg, agg_if))

    # ── Clients ──
    client_attachments = []
    for c in range(N_CLIENTS):
        mac = gen_mac(c)
        ip = gen_client_ip(c)
        vlan = random.choice([10, 20, 30, 40, 50, 100, 200])

        # 95% 接 Edge, 5% 接 Agg
        if random.random() < 0.95:
            sw = random.choice(edges)
        else:
            sw = random.choice(agg_all)

        port_num = random.randint(1, 48)
        interface = f"Gi0/{port_num}"
        client_attachments.append((mac, ip, sw, interface, vlan))

    n_core_agg_links = N_CORE * len(agg_all) * N_CORE_AGG_LINKS
    print(f"  Core: {len(cores)} 台 (MLAG pair)")
    print(f"  AGG:  {len(agg_all)} 台 ({N_AGG_GROUPS} 組×{N_AGG_PER_GROUP}，MLAG pair)")
    print(f"  Edge: {len(edges)} 台 ({N_AGG_GROUPS} 組×{N_EDGE_PER_GROUP})")
    print(f"  連線: {len(links)} 條 "
          f"(Core-Core:1, AGG-AGG:{N_AGG_GROUPS}, "
          f"Core-AGG:{n_core_agg_links}, "
          f"Edge-AGG:{len(edges) * N_AGG_PER_GROUP})")

    return devices, links, expectations, client_attachments


async def seed():
    now = datetime.now(UTC).replace(tzinfo=None)

    devices, links, expectations, clients = build_topology()
    print(f"\n拓樸生成完成: {len(devices)} 設備, {len(links)} 連線, "
          f"{len(expectations)} 期望, {len(clients)} clients")

    async with async_session_factory() as session:
        # ── 清理舊資料 ──
        print(f"\n清理舊歲修 '{MAINTENANCE_ID}'...")

        # 先刪除 neighbor_records (依賴 collection_batches)
        await session.execute(
            delete(NeighborRecord).where(
                NeighborRecord.maintenance_id == MAINTENANCE_ID
            )
        )
        await session.execute(
            delete(LatestCollectionBatch).where(
                LatestCollectionBatch.maintenance_id == MAINTENANCE_ID
            )
        )
        await session.execute(
            delete(CollectionBatch).where(
                CollectionBatch.maintenance_id == MAINTENANCE_ID
            )
        )
        await session.execute(
            delete(UplinkExpectation).where(
                UplinkExpectation.maintenance_id == MAINTENANCE_ID
            )
        )
        await session.execute(
            delete(MaintenanceDeviceList).where(
                MaintenanceDeviceList.maintenance_id == MAINTENANCE_ID
            )
        )
        # MaintenanceMacList
        try:
            await session.execute(
                delete(MaintenanceMacList).where(
                    MaintenanceMacList.maintenance_id == MAINTENANCE_ID
                )
            )
        except Exception:
            pass

        # 刪除 Maintenance 本身
        await session.execute(
            delete(MaintenanceConfig).where(
                MaintenanceConfig.maintenance_id == MAINTENANCE_ID
            )
        )
        await session.flush()

        # ── 建立歲修 ──
        print("建立歲修...")
        session.add(MaintenanceConfig(
            maintenance_id=MAINTENANCE_ID,
            name=MAINTENANCE_NAME,
            is_active=True,
        ))
        await session.flush()

        # ── 設備清單 ──
        print(f"插入 {len(devices)} 筆設備清單...")
        for dev in devices:
            session.add(MaintenanceDeviceList(
                maintenance_id=MAINTENANCE_ID,
                old_hostname=None,
                old_ip_address=None,
                old_vendor=None,
                new_hostname=dev["hostname"],
                new_ip_address=dev["ip"],
                new_vendor=dev["vendor"],
                is_replaced=False,
            ))
        await session.flush()

        # ── Uplink 期望 ──
        print(f"插入 {len(expectations)} 筆 uplink 期望...")
        seen_exp = set()
        for hostname, local_if, neighbor, neighbor_if in expectations:
            key = (hostname, neighbor)
            if key in seen_exp:
                continue
            seen_exp.add(key)
            session.add(UplinkExpectation(
                maintenance_id=MAINTENANCE_ID,
                hostname=hostname,
                local_interface=local_if,
                expected_neighbor=neighbor,
                expected_interface=neighbor_if,
            ))
        await session.flush()

        # ── LLDP 鄰居記錄 (模擬採集結果) ──
        # 先建一批 CollectionBatch + LatestCollectionBatch
        print(f"插入 {len(links)} 條連線的鄰居記錄...")

        # 按 source 設備分組
        links_by_src: dict[str, list] = {}
        for src, src_if, dst, dst_if in links:
            links_by_src.setdefault(src, []).append((src_if, dst, dst_if))
            # 反向也要有（對端設備也會回報看到我）
            links_by_src.setdefault(dst, []).append((dst_if, src, src_if))

        batch_count = 0
        for hostname, neighbors in links_by_src.items():
            # 建 CollectionBatch
            batch = CollectionBatch(
                collection_type="get_uplink_lldp",
                switch_hostname=hostname,
                maintenance_id=MAINTENANCE_ID,
                raw_data="<seeded>",
                item_count=len(neighbors),
                collected_at=now,
            )
            session.add(batch)
            await session.flush()

            # NeighborRecord
            for local_if, remote_host, remote_if in neighbors:
                session.add(NeighborRecord(
                    batch_id=batch.id,
                    switch_hostname=hostname,
                    maintenance_id=MAINTENANCE_ID,
                    collected_at=now,
                    local_interface=local_if,
                    remote_hostname=remote_host,
                    remote_interface=remote_if,
                ))

            # LatestCollectionBatch
            data_hash = hashlib.sha256(
                json.dumps(sorted(
                    [{"local_interface": li, "remote_hostname": rh, "remote_interface": ri}
                     for li, rh, ri in neighbors],
                    key=lambda x: x["local_interface"]
                )).encode()
            ).hexdigest()[:16]

            session.add(LatestCollectionBatch(
                maintenance_id=MAINTENANCE_ID,
                collection_type="get_uplink_lldp",
                switch_hostname=hostname,
                batch_id=batch.id,
                data_hash=data_hash,
                collected_at=now,
                last_checked_at=now,
            ))
            batch_count += 1

            # 每 50 個 batch flush 一次，避免記憶體太高
            if batch_count % 50 == 0:
                await session.flush()
                print(f"  ... {batch_count} / {len(links_by_src)} 設備已處理")

        await session.flush()
        print(f"  完成，共 {batch_count} 個 collection batch")

        # ── Client MAC 清單 ──
        print(f"插入 {len(clients)} 筆 client MAC...")
        for i, (mac, ip, sw, iface, vlan) in enumerate(clients):
            session.add(MaintenanceMacList(
                maintenance_id=MAINTENANCE_ID,
                mac_address=mac,
                ip_address=ip,
                tenant_group=TenantGroup.F18,
                detection_status=ClientDetectionStatus.NOT_CHECKED,
            ))
            if (i + 1) % 1000 == 0:
                await session.flush()
                print(f"  ... {i + 1} / {len(clients)} clients")

        await session.flush()

        # ── 故意讓一些期望失敗 (刪除部分 LLDP 記錄模擬連線中斷) ──
        n_edge = N_AGG_GROUPS * N_EDGE_PER_GROUP
        fail_count = max(1, int(n_edge * 0.03))
        fail_edges = random.sample(
            [f"EDGE-{i:03d}" for i in range(1, n_edge + 1)],
            fail_count
        )
        print(f"模擬 {fail_count} 台 edge 連線中斷: {fail_edges[:5]}...")
        for edge_host in fail_edges:
            await session.execute(
                delete(NeighborRecord).where(
                    NeighborRecord.maintenance_id == MAINTENANCE_ID,
                    NeighborRecord.switch_hostname == edge_host,
                )
            )

        await session.commit()
        print(f"\n===== 完成 =====")
        print(f"歲修 ID: {MAINTENANCE_ID}")
        print(f"設備: {len(devices)} 台")
        print(f"連線: {len(links)} 條")
        print(f"期望: {len(seen_exp)} 筆")
        print(f"Clients: {len(clients)} 筆")
        print(f"模擬中斷: {fail_count} 台 Edge")
        print(f"\n請到前端選擇歲修 '{MAINTENANCE_ID}' 查看拓樸！")


if __name__ == "__main__":
    asyncio.run(seed())
