"""
Client Collection Service.

客戶端資料採集服務 — 實作 Phase 1-4 流程。

Phase 1: 並行呼叫 Type A Fetchers (mac_table, arp_table, interface_status)
Phase 2: 依賴呼叫 (get_acl_number + ping_many)，與 Phase 1 的結果組合
Phase 3: 組裝 ClientRecord（純記憶體運算）
Phase 4: 寫入 client_records 表

每台 switch 獨立執行 Phase 1-4，完成後整體採集結果回傳。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import ClientDetectionStatus, MaintenancePhase, TenantGroup
from app.db.base import get_session_context
from app.core.types import SwitchInfo
from app.db.models import (
    ClientRecord, MaintenanceMacList, MaintenanceDeviceList, ArpSource,
)
from app.parsers.client_parsers import (
    AclParser,
    ArpParser,
    InterfaceStatusParser,
    MacTableParser,
    PingManyParser,
)
from app.parsers.protocols import (
    AclData,
    ArpData,
    InterfaceStatusData,
    MacTableData,
    PingManyData,
)
from app.fetchers.base import FetchContext
from app.fetchers.registry import fetcher_registry
# SwitchRepository 已移除，改用 MaintenanceDeviceList

logger = logging.getLogger(__name__)


# ── Fetcher raw output 容器 ──────────────────────────────────────


class _FetcherResults:
    """Phase 1 回傳的 raw output 暫存。"""

    def __init__(self) -> None:
        self.mac_table_raw: str = ""
        self.arp_table_raw: str = ""
        self.interface_status_raw: str = ""


class _ParsedIntermediates:
    """Phase 1 parse 後的中間資料。"""

    def __init__(self) -> None:
        self.mac_entries: list[MacTableData] = []
        self.arp_entries: list[ArpData] = []
        self.if_entries: list[InterfaceStatusData] = []
        self.acl_entries: list[AclData] = []
        self.ping_entries: list[PingManyData] = []


# ── Service ──────────────────────────────────────────────────────


class ClientCollectionService:
    """
    客戶端資料採集服務。

    負責對每台 active switch 採集 MAC / ARP / InterfaceStatus / ACL / Ping
    並組裝成 ClientRecord 寫入 DB。

    此服務只處理「客戶端資料」（Fetchers 9-13）。
    8 個指標的 Fetchers (1-8) 由既有的 DataCollectionService 處理。
    """

    def __init__(self) -> None:
        # Parser instances
        self._mac_parser = MacTableParser()
        self._arp_parser = ArpParser()
        self._if_parser = InterfaceStatusParser()
        self._acl_parser = AclParser()
        self._ping_parser = PingManyParser()

    # ── 設備資訊載入 ─────────────────────────────────────────────

    async def _load_device_tenant_groups(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> dict[str, TenantGroup]:
        """
        載入設備的 tenant_group 對應表。

        同時載入新舊設備的 IP，確保都有對應的 tenant_group。

        Args:
            maintenance_id: 歲修 ID
            session: DB session

        Returns:
            {switch_ip: tenant_group} 對應表
        """
        from sqlalchemy import select

        stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        devices = result.scalars().all()

        ip_to_tenant_group: dict[str, TenantGroup] = {}
        for device in devices:
            tenant_group = device.tenant_group or TenantGroup.F18
            # 加入舊設備 IP
            if device.old_ip_address:
                ip_to_tenant_group[device.old_ip_address] = tenant_group
            # 加入新設備 IP（如果與舊設備相同則會覆蓋，但 tenant_group 一樣所以沒影響）
            if device.new_ip_address:
                ip_to_tenant_group[device.new_ip_address] = tenant_group

        logger.info(
            "Loaded device tenant_groups for %s: %d unique IPs",
            maintenance_id, len(ip_to_tenant_group),
        )
        return ip_to_tenant_group

    async def _load_maintenance_switches(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> list[SwitchInfo]:
        """
        從 MaintenanceDeviceList 載入設備清單，轉換為 SwitchInfo 物件。

        同時載入新舊設備，並以 IP 去重（如果 old_ip == new_ip 表示設備未更換）。
        這確保採集時可以從任一設備找到 MAC（因為 MAC 可能在舊或新設備上）。

        Args:
            maintenance_id: 歲修 ID
            session: DB session

        Returns:
            SwitchInfo 物件列表（新舊設備合併，已去重）
        """
        from sqlalchemy import select
        from app.core.enums import VendorType, PlatformType

        stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        devices = result.scalars().all()

        # 用於去重：以 IP 為 key（因為同一 IP 代表同一設備）
        seen_ips: set[str] = set()
        switches = []

        # 轉換函數
        def _create_switch(hostname: str, ip: str, vendor_str: str) -> SwitchInfo | None:
            if not ip or ip in seen_ips:
                return None
            seen_ips.add(ip)

            # 轉換 vendor 字串為 VendorType
            vendor_map = {
                "HPE": VendorType.HPE,
                "Cisco-IOS": VendorType.CISCO,
                "Cisco-NXOS": VendorType.CISCO,
            }
            vendor = vendor_map.get(vendor_str, VendorType.HPE)

            # 轉換 vendor 字串為 PlatformType
            platform_map = {
                "HPE": PlatformType.HPE_COMWARE,
                "Cisco-IOS": PlatformType.CISCO_IOS,
                "Cisco-NXOS": PlatformType.CISCO_NXOS,
            }
            platform = platform_map.get(vendor_str, PlatformType.HPE_COMWARE)

            return SwitchInfo(
                hostname=hostname,
                ip_address=ip,
                vendor=vendor,
                platform=platform,
            )

        skipped_unreachable = 0
        for device in devices:
            # 加入舊設備（只有可達的）
            if device.old_is_reachable:
                old_switch = _create_switch(
                    device.old_hostname,
                    device.old_ip_address,
                    device.old_vendor,
                )
                if old_switch:
                    switches.append(old_switch)
            elif device.old_hostname:
                skipped_unreachable += 1

            # 加入新設備（只有可達的，如果 IP 與舊設備相同則跳過，因為已去重）
            if device.is_reachable:
                new_switch = _create_switch(
                    device.new_hostname,
                    device.new_ip_address,
                    device.new_vendor,
                )
                if new_switch:
                    switches.append(new_switch)
            elif device.new_hostname:
                skipped_unreachable += 1

        if skipped_unreachable > 0:
            logger.info(
                "Skipped %d unreachable devices for %s",
                skipped_unreachable, maintenance_id,
            )

        logger.info(
            "Loaded %d unique reachable switches for %s (from %d device records)",
            len(switches), maintenance_id, len(devices),
        )
        return switches

    # ── MAC 白名單載入 ─────────────────────────────────────────

    async def _load_mac_whitelist(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> set[str]:
        """
        從 MaintenanceMacList 載入該歲修的 MAC 白名單。

        只有在白名單中的 MAC 才會被採集和寫入 ClientRecord。
        這確保資料流與歲修設定一致。

        Args:
            maintenance_id: 歲修 ID
            session: DB session

        Returns:
            MAC 地址集合（大寫，用於快速查找）
        """
        from sqlalchemy import select

        stmt = select(MaintenanceMacList.mac_address).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        macs = result.scalars().all()

        # 統一轉大寫以便比對
        whitelist = {mac.upper() for mac in macs}

        logger.info(
            "Loaded MAC whitelist for %s: %d MACs",
            maintenance_id, len(whitelist),
        )
        return whitelist

    async def _load_arp_source_switches(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> list[SwitchInfo]:
        """
        從 ArpSource 設定載入 ARP 來源設備，轉換為 SwitchInfo 物件。

        ArpSource 指定從哪些 Router/Gateway 獲取 ARP Table。
        這些設備必須存在於 MaintenanceDeviceList 中。

        資料流邏輯：
        1. 先查詢 ArpSource 設定
        2. 如果沒有設定，返回空列表（表示沒有 ARP 來源）
        3. 如果有設定，從 MaintenanceDeviceList 找出對應的設備資訊

        Args:
            maintenance_id: 歲修 ID
            session: DB session

        Returns:
            ARP 來源 SwitchInfo 物件列表（按 priority 排序）
        """
        from sqlalchemy import select, or_
        from app.core.enums import VendorType, PlatformType

        # 1. 載入 ArpSource 設定
        arp_stmt = select(ArpSource).where(
            ArpSource.maintenance_id == maintenance_id
        ).order_by(ArpSource.priority)

        result = await session.execute(arp_stmt)
        arp_sources = result.scalars().all()

        if not arp_sources:
            logger.info(
                "No ArpSource configured for %s - ARP fetch will be skipped",
                maintenance_id,
            )
            return []

        # 2. 取得所有 ArpSource hostname
        arp_hostnames = {src.hostname for src in arp_sources}

        # 3. 從 MaintenanceDeviceList 載入對應的設備資訊
        device_stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id,
            or_(
                MaintenanceDeviceList.new_hostname.in_(arp_hostnames),
                MaintenanceDeviceList.old_hostname.in_(arp_hostnames),
            ),
        )

        device_result = await session.execute(device_stmt)
        devices = device_result.scalars().all()

        # 4. 建立 hostname → device 對應表
        hostname_to_device: dict[str, MaintenanceDeviceList] = {}
        for device in devices:
            if device.new_hostname in arp_hostnames:
                hostname_to_device[device.new_hostname] = device
            if device.old_hostname in arp_hostnames:
                hostname_to_device[device.old_hostname] = device

        # 5. 按 ArpSource 的 priority 順序轉換為 SwitchInfo 物件
        switches = []
        for arp_src in arp_sources:
            device = hostname_to_device.get(arp_src.hostname)
            if not device:
                logger.warning(
                    "ArpSource %s not found in MaintenanceDeviceList for %s",
                    arp_src.hostname, maintenance_id,
                )
                continue

            # 判斷使用新設備還是舊設備，並檢查可達性
            if device.new_hostname == arp_src.hostname:
                hostname = device.new_hostname
                ip = device.new_ip_address
                vendor_str = device.new_vendor
                is_reachable = device.is_reachable
            else:
                hostname = device.old_hostname
                ip = device.old_ip_address
                vendor_str = device.old_vendor
                is_reachable = device.old_is_reachable

            if not ip:
                logger.warning(
                    "ArpSource %s has no IP address",
                    arp_src.hostname,
                )
                continue

            # 檢查設備可達性（必須先執行 ping collection 更新此欄位）
            # is_reachable 為 None 表示尚未檢查，視為可嘗試連線
            if is_reachable is False:
                logger.info(
                    "ArpSource %s is not reachable, skipping ARP fetch",
                    arp_src.hostname,
                )
                continue

            # 轉換 vendor 字串為 VendorType
            vendor_map = {
                "HPE": VendorType.HPE,
                "Cisco-IOS": VendorType.CISCO,
                "Cisco-NXOS": VendorType.CISCO,
            }
            vendor = vendor_map.get(vendor_str, VendorType.HPE)

            # 轉換 vendor 字串為 PlatformType
            platform_map = {
                "HPE": PlatformType.HPE_COMWARE,
                "Cisco-IOS": PlatformType.CISCO_IOS,
                "Cisco-NXOS": PlatformType.CISCO_NXOS,
            }
            platform = platform_map.get(vendor_str, PlatformType.HPE_COMWARE)

            switches.append(SwitchInfo(
                hostname=hostname,
                ip_address=ip,
                vendor=vendor,
                platform=platform,
            ))

        logger.info(
            "Loaded %d ArpSource switches for %s: %s",
            len(switches),
            maintenance_id,
            [s.hostname for s in switches],
        )
        return switches

    async def _load_client_list(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> list[MaintenanceMacList]:
        """
        載入完整的 Client 清單（包含 IP、MAC、tenant_group）。

        用於：
        1. GNMS Ping 客戶端 IP（按 tenant_group 分組）
        2. 檢查 ARP IP-MAC 是否匹配

        Args:
            maintenance_id: 歲修 ID
            session: DB session

        Returns:
            Client 清單（MaintenanceMacList 物件列表）
        """
        from sqlalchemy import select

        stmt = select(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        clients = result.scalars().all()

        logger.info(
            "Loaded client list for %s: %d clients",
            maintenance_id, len(clients),
        )
        return list(clients)

    async def _update_client_detection_status(
        self,
        session: AsyncSession,
        client_id: int,
        status: ClientDetectionStatus,
    ) -> None:
        """
        更新 Client 的偵測狀態。

        Args:
            session: DB session
            client_id: MaintenanceMacList.id
            status: 新的偵測狀態
        """
        from sqlalchemy import update

        stmt = (
            update(MaintenanceMacList)
            .where(MaintenanceMacList.id == client_id)
            .values(detection_status=status)
        )
        await session.execute(stmt)

    # ── public entry point ───────────────────────────────────────

    async def collect_client_data(
        self,
        maintenance_id: str,
        phase: MaintenancePhase = MaintenancePhase.NEW,
        source: str | None = None,
        brand: str | None = None,
    ) -> dict[str, Any]:
        """
        主入口：對所有 active switch 採集客戶端資料。

        即使沒有設備或沒有 Client 清單，也會寫入一筆空的快照標記，
        確保 Checkpoint 列表有時間點可選。

        Args:
            maintenance_id: 歲修 ID
            phase: 階段
            source: Data source (FNA/DNA)
            brand: Device brand (HPE/Cisco-IOS/Cisco-NXOS)

        Returns:
            採集統計
        """
        results: dict[str, Any] = {
            "collection_type": "client",
            "phase": phase.value,
            "maintenance_id": maintenance_id,
            "total": 0,
            "success": 0,
            "failed": 0,
            "errors": [],
            "client_records_count": 0,
        }

        now = datetime.now(timezone.utc)

        async with httpx.AsyncClient() as http:
            async with get_session_context() as session:
                # 先檢查是否有設定 ArpSource
                # 如果沒有設定，代表用戶還沒配置好，不應該採集資料
                from sqlalchemy import func
                arp_count_stmt = select(func.count()).select_from(ArpSource).where(
                    ArpSource.maintenance_id == maintenance_id
                )
                arp_count_result = await session.execute(arp_count_stmt)
                arp_count = arp_count_result.scalar()

                if arp_count == 0:
                    logger.warning(
                        "No ArpSource configured for %s - skipping client data collection. "
                        "Please configure ARP sources first.",
                        maintenance_id,
                    )
                    # 寫入快照標記以記錄這個時間點
                    await self._write_snapshot_marker(
                        session=session,
                        maintenance_id=maintenance_id,
                        phase=phase,
                        collected_at=now,
                    )
                    return results

                # 載入完整的 Client 清單（包含 MAC 和用戶輸入的 IP）
                client_list = await self._load_client_list(
                    maintenance_id, session,
                )

                # 從 MaintenanceDeviceList 載入設備清單（新舊設備都載入）
                switches = await self._load_maintenance_switches(
                    maintenance_id, session,
                )
                results["total"] = len(switches)

                # 即使沒有 Client 或沒有設備，也要寫入快照時間點標記
                # 這確保 Checkpoint 列表有時間點可選
                if not client_list or not switches:
                    await self._write_snapshot_marker(
                        session=session,
                        maintenance_id=maintenance_id,
                        phase=phase,
                        collected_at=now,
                    )
                    logger.info(
                        "Wrote snapshot marker for %s (no clients: %s, no switches: %s)",
                        maintenance_id,
                        not client_list,
                        not switches,
                    )
                    return results

                # 建立 MAC → Client 對應表（用於匹配和 ping）
                mac_to_client = {
                    c.mac_address.upper(): c for c in client_list
                }
                mac_whitelist = set(mac_to_client.keys())

                # 載入設備 tenant_group 對應表 (用於 GNMS Ping)
                device_tenant_groups = await self._load_device_tenant_groups(
                    maintenance_id, session,
                )

                for switch in switches:
                    try:
                        records = await self._collect_for_switch(
                            switch=switch,
                            maintenance_id=maintenance_id,
                            phase=phase,
                            session=session,
                            mac_whitelist=mac_whitelist,
                            mac_to_client=mac_to_client,
                            device_tenant_groups=device_tenant_groups,
                            source=source,
                            brand=brand,
                            http=http,
                        )
                        results["success"] += 1
                        results["client_records_count"] += len(
                            records,
                        )
                    except Exception as e:
                        results["failed"] += 1
                        results["errors"].append({
                            "switch": switch.hostname,
                            "error": str(e),
                        })
                        logger.error(
                            "Failed client collection %s: %s",
                            switch.hostname, e,
                        )

                # 如果沒有採集到任何 ClientRecord，仍需寫入快照標記
                if results["client_records_count"] == 0:
                    await self._write_snapshot_marker(
                        session=session,
                        maintenance_id=maintenance_id,
                        phase=phase,
                        collected_at=now,
                    )
                    logger.info(
                        "Wrote snapshot marker for %s (no records collected)",
                        maintenance_id,
                    )

        # 清理超過 30 天的舊資料
        async with get_session_context() as session:
            deleted = await self._cleanup_old_records(
                session=session,
                maintenance_id=maintenance_id,
                retention_days=30,
            )
            if deleted > 0:
                results["deleted_old_records"] = deleted
                logger.info(
                    "Cleaned up %d old client records (>30 days)",
                    deleted,
                )

        logger.info(
            "Client collection done: %d/%d switches, %d records",
            results["success"], results["total"],
            results["client_records_count"],
        )
        return results

    async def _write_snapshot_marker(
        self,
        session: AsyncSession,
        maintenance_id: str,
        phase: MaintenancePhase,
        collected_at: datetime,
    ) -> None:
        """
        寫入快照時間點標記。

        即使沒有實際採集到資料，也需要記錄這個時間點，
        確保 Checkpoint 列表有時間點可選。

        使用特殊的 MAC 地址 "SNAPSHOT_MARKER" 作為標記。
        """
        marker = ClientRecord(
            maintenance_id=maintenance_id,
            phase=phase,
            collected_at=collected_at,
            mac_address="__MARKER__",
            ip_address=None,
            switch_hostname="__SYSTEM__",
            interface_name=None,
            vlan_id=None,
            speed=None,
            duplex=None,
            link_status=None,
            ping_reachable=None,
            acl_rules_applied=None,
            acl_passes=None,
        )
        session.add(marker)
        await session.flush()

    async def detect_clients(
        self,
        maintenance_id: str,
    ) -> dict[str, Any]:
        """
        偵測客戶端狀態。

        完整流程：
        1. 從 MaintenanceMacList 載入所有 Client（IP + MAC + tenant_group）
        2. 從 MaintenanceDeviceList 載入設備清單
        3. 對每個設備即時呼叫 ARP fetcher 取得 ARP 資料
        4. 檢查每個 Client：
           - ARP 有此 MAC + IP-MAC 正確 → 繼續 ping
           - ARP 有此 MAC + IP-MAC 不正確 → MISMATCH
           - ARP 沒有此 MAC → NOT_DETECTED（網路上看不到）
        5. 對 ARP 匹配的 clients 按 tenant_group 分組呼叫 GNMS Ping
        6. Ping 通 → DETECTED，Ping 不通 → NOT_DETECTED
        7. 更新 MaintenanceMacList.detection_status

        Args:
            maintenance_id: 歲修 ID

        Returns:
            偵測統計
        """
        results = {
            "maintenance_id": maintenance_id,
            "total": 0,
            "detected": 0,
            "mismatch": 0,
            "not_detected": 0,
            "no_arp": 0,  # ARP 中找不到的數量
            "errors": [],
        }

        async with get_session_context() as session:
            # 1. 載入 Client 清單
            clients = await self._load_client_list(maintenance_id, session)
            results["total"] = len(clients)

            if not clients:
                logger.warning("No clients found for %s", maintenance_id)
                return results

            # 先重置所有 clients 的偵測狀態為 NOT_CHECKED
            from sqlalchemy import update
            reset_stmt = (
                update(MaintenanceMacList)
                .where(MaintenanceMacList.maintenance_id == maintenance_id)
                .values(detection_status=ClientDetectionStatus.NOT_CHECKED)
            )
            await session.execute(reset_stmt)
            logger.info(
                "Reset detection status for %d clients in %s",
                len(clients), maintenance_id,
            )

            # 2. 載入 ArpSource 設定的設備（不是所有設備）
            # 資料流邏輯：
            # - 先檢查 ArpSource 設定
            # - 如果有設定，從這些設備取得 ARP
            # - 如果沒有設定，返回空 ARP（模擬真實情況）
            arp_source_switches = await self._load_arp_source_switches(
                maintenance_id, session,
            )

            if not arp_source_switches:
                # 沒有設定 ArpSource，無法取得 ARP 資料
                # 所有 clients 都會被標記為 NOT_DETECTED (no_arp)
                logger.warning(
                    "No ArpSource configured for %s - all clients will be NOT_DETECTED",
                    maintenance_id,
                )
                arp_mac_to_ip = {}
            else:
                # 3. 從 ArpSource 設備取得 ARP 資料
                arp_mac_to_ip = await self._fetch_arp_from_switches(
                    arp_source_switches, maintenance_id
                )
                logger.info(
                    "Fetched ARP data from %d ArpSource switches: %d entries",
                    len(arp_source_switches), len(arp_mac_to_ip),
                )

            # 4. 檢查每個 Client 的 ARP 狀態
            arp_matched_clients: list[MaintenanceMacList] = []
            for client in clients:
                mac_upper = client.mac_address.upper()

                if mac_upper not in arp_mac_to_ip:
                    # ARP 中沒有此 MAC → 網路上看不到這個 client
                    await self._update_client_detection_status(
                        session, client.id, ClientDetectionStatus.NOT_DETECTED,
                    )
                    results["not_detected"] += 1
                    results["no_arp"] += 1
                    continue

                # ARP 中有此 MAC，檢查 IP 是否匹配
                arp_ip = arp_mac_to_ip[mac_upper]
                if arp_ip != client.ip_address:
                    # IP-MAC 不匹配
                    await self._update_client_detection_status(
                        session, client.id, ClientDetectionStatus.MISMATCH,
                    )
                    results["mismatch"] += 1
                    logger.warning(
                        "IP-MAC mismatch for %s: ARP=%s, user input=%s",
                        mac_upper, arp_ip, client.ip_address,
                    )
                    continue

                # ARP 匹配，加入 ping 清單
                arp_matched_clients.append(client)

            # 5. 按 tenant_group 分組 ping
            by_tenant: dict[TenantGroup, list[MaintenanceMacList]] = {}
            for client in arp_matched_clients:
                tg = client.tenant_group or TenantGroup.F18
                by_tenant.setdefault(tg, []).append(client)

            # 6. 對每個 tenant_group 呼叫 GNMS Ping
            for tenant_group, group_clients in by_tenant.items():
                client_ips = [c.ip_address for c in group_clients]

                try:
                    reachable_ips = await self._ping_client_ips(
                        client_ips, tenant_group, maintenance_id,
                    )

                    # 更新偵測狀態
                    for client in group_clients:
                        if client.ip_address in reachable_ips:
                            await self._update_client_detection_status(
                                session,
                                client.id,
                                ClientDetectionStatus.DETECTED,
                            )
                            results["detected"] += 1
                        else:
                            await self._update_client_detection_status(
                                session,
                                client.id,
                                ClientDetectionStatus.NOT_DETECTED,
                            )
                            results["not_detected"] += 1

                except Exception as e:
                    logger.error(
                        "GNMS Ping failed for tenant_group %s: %s",
                        tenant_group.value, e,
                    )
                    results["errors"].append({
                        "tenant_group": tenant_group.value,
                        "error": str(e),
                    })

            await session.commit()

        logger.info(
            "Client detection done for %s: %d detected, %d mismatch, "
            "%d not_detected (no_arp=%d)",
            maintenance_id,
            results["detected"],
            results["mismatch"],
            results["not_detected"],
            results["no_arp"],
        )
        return results

    async def _fetch_arp_from_switches(
        self,
        switches: list[SwitchInfo],
        maintenance_id: str,
    ) -> dict[str, str]:
        """
        從設備即時取得 ARP 資料。

        對每個設備呼叫 ARP fetcher，合併結果。

        Args:
            switches: 設備清單
            maintenance_id: 歲修 ID（用於 Mock Fetcher 計算收斂時間）

        Returns:
            {MAC_ADDRESS: IP_ADDRESS} 對應表（MAC 為大寫）
        """
        if not switches:
            return {}

        arp_fetcher = fetcher_registry.get_or_raise("arp_table")
        arp_mac_to_ip: dict[str, str] = {}

        for switch in switches:
            ctx = FetchContext(
                switch_ip=switch.ip_address,
                switch_hostname=switch.hostname,
                site=switch.site.value,
                source=None,
                brand=None,
                vendor=switch.vendor.value,
                platform=switch.platform.value,
                http=None,
                base_url=settings.external_api_server,
                timeout=settings.external_api_timeout,
                maintenance_id=maintenance_id,
            )

            try:
                result = await arp_fetcher.fetch(ctx)
                if not result.success:
                    logger.warning(
                        "ARP fetch failed for %s: %s",
                        switch.hostname, result.error,
                    )
                    continue

                # 解析 ARP 結果 (CSV: IP,MAC)
                lines = result.raw_output.strip().split("\n")
                for line in lines[1:]:  # 跳過 header
                    parts = line.split(",")
                    if len(parts) >= 2:
                        ip = parts[0].strip()
                        mac = parts[1].strip().upper()
                        if mac and ip:
                            arp_mac_to_ip[mac] = ip

            except Exception as e:
                logger.error(
                    "Failed to fetch ARP from %s: %s",
                    switch.hostname, e,
                )

        return arp_mac_to_ip

    async def _get_latest_arp_mapping(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> dict[str, str]:
        """
        從最新的 ClientRecord 取得 ARP 資料（MAC → IP 對應）。

        Args:
            maintenance_id: 歲修 ID
            session: DB session

        Returns:
            {MAC_ADDRESS: IP_ADDRESS} 對應表（MAC 為大寫）
        """
        from sqlalchemy import select, func

        # 取得每個 MAC 最新的 IP
        subq = (
            select(
                ClientRecord.mac_address,
                func.max(ClientRecord.collected_at).label("max_time"),
            )
            .where(ClientRecord.maintenance_id == maintenance_id)
            .group_by(ClientRecord.mac_address)
            .subquery()
        )

        stmt = (
            select(ClientRecord.mac_address, ClientRecord.ip_address)
            .join(
                subq,
                (ClientRecord.mac_address == subq.c.mac_address) &
                (ClientRecord.collected_at == subq.c.max_time),
            )
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.ip_address.isnot(None),
            )
        )

        result = await session.execute(stmt)
        rows = result.fetchall()

        return {row[0].upper(): row[1] for row in rows}

    async def _ping_client_ips(
        self,
        client_ips: list[str],
        tenant_group: TenantGroup,
        maintenance_id: str,
    ) -> set[str]:
        """
        使用 GNMS Ping 檢查客戶端 IP 可達性。

        Args:
            client_ips: 要 ping 的客戶端 IP 列表
            tenant_group: Tenant group
            maintenance_id: 歲修 ID（用於 Mock Fetcher 時間追蹤）

        Returns:
            可達的 IP 集合
        """
        if not client_ips:
            return set()

        gnms_ping_fetcher = fetcher_registry.get_or_raise("gnms_ping")

        ctx = FetchContext(
            switch_ip="batch",
            switch_hostname="client_detection",
            site="",
            source=None,
            brand=None,
            vendor="",
            platform="",
            http=None,
            base_url=settings.external_api_server,
            timeout=settings.external_api_timeout,
            maintenance_id=maintenance_id,
            params={
                "switch_ips": client_ips,  # 這裡傳的是 client IPs
                "tenant_group": tenant_group,
            },
        )

        result = await gnms_ping_fetcher.fetch(ctx)

        if not result.success:
            raise RuntimeError(f"GNMS Ping failed: {result.error}")

        # 解析結果 (CSV: IP,Reachable,Latency_ms)
        reachable_ips: set[str] = set()
        lines = result.raw_output.strip().split("\n")
        for line in lines[1:]:  # 跳過 header
            parts = line.split(",")
            if len(parts) >= 2:
                ip = parts[0].strip()
                reachable = parts[1].strip().lower() == "true"
                if reachable:
                    reachable_ips.add(ip)

        logger.info(
            "GNMS Ping for tenant_group %s: %d/%d reachable",
            tenant_group.value, len(reachable_ips), len(client_ips),
        )
        return reachable_ips

    async def _cleanup_old_records(
        self,
        session: AsyncSession,
        maintenance_id: str,
        retention_days: int = 30,
    ) -> int:
        """
        清理超過保留期限的舊 ClientRecord。

        Args:
            session: DB session
            maintenance_id: 歲修 ID
            retention_days: 保留天數（預設 30 天）

        Returns:
            刪除的記錄數
        """
        from sqlalchemy import delete

        cutoff_time = datetime.now(timezone.utc) - timedelta(days=retention_days)

        stmt = (
            delete(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.collected_at < cutoff_time,
            )
        )

        result = await session.execute(stmt)
        await session.commit()

        return result.rowcount or 0

    # ── per-switch orchestration ─────────────────────────────────

    async def _collect_for_switch(
        self,
        switch: SwitchInfo,
        maintenance_id: str,
        phase: MaintenancePhase,
        session: AsyncSession,
        mac_whitelist: set[str],
        mac_to_client: dict[str, MaintenanceMacList],
        device_tenant_groups: dict[str, TenantGroup],
        source: str | None = None,
        brand: str | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> list[ClientRecord]:
        """
        單台 switch 的完整採集流程 (Phase 1 → 匹配檢查 → 2 → 3 → 4)。

        Args:
            switch: 目標設備
            maintenance_id: 歲修 ID
            phase: 階段
            session: DB session
            mac_whitelist: MAC 白名單，只採集在此清單中的 MAC
            mac_to_client: {MAC: MaintenanceMacList} 對應表，用於取得用戶輸入的 IP
            device_tenant_groups: {switch_ip: tenant_group} 對應表

        Returns:
            寫入 DB 的 ClientRecord 列表。
        """
        # 取得此 switch 的 tenant_group (用於 GNMS Ping)
        tenant_group = device_tenant_groups.get(switch.ip_address, TenantGroup.F18)

        # ── Phase 1: 並行 Type A Fetchers ──────────────────
        raw = await self._phase1_parallel_fetch(
            switch, source=source, brand=brand, http=http,
        )
        intermediates = self._phase1_parse(raw)

        # ── 匹配檢查：比較 ARP TABLE 的 IP-MAC 與 Client 清單 ──────
        # 只有 IP-MAC 對應一致的 Client 才會被 ping
        matched_clients, mismatched_clients = self._match_clients_with_mac_table(
            intermediates, mac_to_client,
        )

        # 記錄 mismatch 的 Client（可用於後續更新狀態）
        if mismatched_clients:
            logger.info(
                "Found %d mismatched clients on %s",
                len(mismatched_clients), switch.hostname,
            )

        # ── Phase 2: 依賴呼叫 (使用 GNMS Ping) ──────────────
        # 只 ping IP-MAC 匹配的 Client 的用戶輸入 IP
        await self._phase2_dependent_fetch(
            switch, intermediates,
            matched_clients=matched_clients,
            tenant_group=tenant_group,
            source=source, brand=brand, http=http,
        )

        # ── Phase 3: 組裝 ClientRecord（過濾白名單）─────────
        records = self._phase3_assemble(
            switch_hostname=switch.hostname,
            maintenance_id=maintenance_id,
            phase=phase,
            intermediates=intermediates,
            mac_whitelist=mac_whitelist,
            mac_to_client=mac_to_client,
        )

        # ── Phase 4: 寫入 DB ───────────────────────────────
        await self._phase4_save(session, records)

        logger.info(
            "Collected %d client records from %s",
            len(records), switch.hostname,
        )
        return records

    def _match_clients_with_mac_table(
        self,
        intermediates: _ParsedIntermediates,
        mac_to_client: dict[str, MaintenanceMacList],
    ) -> tuple[list[MaintenanceMacList], list[MaintenanceMacList]]:
        """
        匹配檢查：比較 ARP TABLE 中的 IP-MAC 對應是否與 Client 清單一致。

        匹配邏輯：
        1. 從 MAC TABLE 取得 MAC
        2. 從 ARP TABLE 取得這個 MAC 對應的真實 IP
        3. 比較 ARP 中的真實 IP 是否與 Client 清單中用戶輸入的 IP 一致
        4. 一致 → matched（會被 ping）
        5. 不一致 → mismatched（IP-MAC 對應錯誤）

        Args:
            intermediates: Phase 1 採集的中間資料
            mac_to_client: {MAC: MaintenanceMacList} 對應表

        Returns:
            (matched_clients, mismatched_clients) 元組
        """
        # 建立 ARP TABLE 的 MAC → IP 對應
        arp_mac_to_ip: dict[str, str] = {}
        for arp_entry in intermediates.arp_entries:
            mac_upper = arp_entry.mac_address.upper()
            arp_mac_to_ip[mac_upper] = arp_entry.ip_address

        matched_clients: list[MaintenanceMacList] = []
        mismatched_clients: list[MaintenanceMacList] = []
        seen_macs: set[str] = set()

        for mac_entry in intermediates.mac_entries:
            mac_upper = mac_entry.mac_address.upper()

            # 跳過已處理的 MAC
            if mac_upper in seen_macs:
                continue
            seen_macs.add(mac_upper)

            # 檢查 MAC 是否在 Client 清單中
            if mac_upper not in mac_to_client:
                continue

            client = mac_to_client[mac_upper]

            # 檢查 ARP TABLE 中是否有這個 MAC
            if mac_upper not in arp_mac_to_ip:
                # MAC 在 MAC TABLE 中但不在 ARP TABLE 中
                # 這種情況也算匹配（只是沒有 IP 資訊）
                matched_clients.append(client)
                continue

            # 比較 ARP 中的真實 IP 與用戶輸入的 IP
            arp_ip = arp_mac_to_ip[mac_upper]
            user_ip = client.ip_address

            if arp_ip == user_ip:
                # IP-MAC 對應一致 → 匹配成功
                matched_clients.append(client)
            else:
                # IP-MAC 對應不一致 → MISMATCH
                mismatched_clients.append(client)
                logger.warning(
                    "IP-MAC mismatch for %s: ARP shows %s, user input %s",
                    mac_upper, arp_ip, user_ip,
                )

        logger.debug(
            "Match result: %d matched, %d mismatched from MAC TABLE",
            len(matched_clients), len(mismatched_clients),
        )
        return matched_clients, mismatched_clients

    # ── Phase 1: 並行呼叫 Type A Fetchers ────────────────────────

    async def _phase1_parallel_fetch(
        self,
        switch: SwitchInfo,
        source: str | None = None,
        brand: str | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> _FetcherResults:
        """
        並行呼叫 3 個 Type A Fetchers:
        mac_table, arp_table, interface_status

        全部只需 switch_ip，無依賴。
        """
        raw = _FetcherResults()

        def _ctx() -> FetchContext:
            return FetchContext(
                switch_ip=switch.ip_address,
                switch_hostname=switch.hostname,
                site=switch.site.value,
                source=source,
                brand=brand,
                vendor=switch.vendor.value,
                platform=switch.platform.value,
                http=http,
                base_url=settings.external_api_server,
                timeout=settings.external_api_timeout,
            )

        mac_f = fetcher_registry.get_or_raise("mac_table")
        arp_f = fetcher_registry.get_or_raise("arp_table")
        if_f = fetcher_registry.get_or_raise("interface_status")

        mac_r, arp_r, if_r = await asyncio.gather(
            mac_f.fetch(_ctx()),
            arp_f.fetch(_ctx()),
            if_f.fetch(_ctx()),
        )

        checks = [
            ("mac_table", mac_r),
            ("arp_table", arp_r),
            ("interface_status", if_r),
        ]
        for label, r in checks:
            if not r.success:
                raise RuntimeError(
                    f"Fetch failed for {label} on "
                    f"{switch.hostname}: {r.error}"
                )

        raw.mac_table_raw = mac_r.raw_output
        raw.arp_table_raw = arp_r.raw_output
        raw.interface_status_raw = if_r.raw_output

        return raw

    def _phase1_parse(self, raw: _FetcherResults) -> _ParsedIntermediates:
        """將 Phase 1 的 raw output 解析為中間資料。"""
        intermediates = _ParsedIntermediates()
        intermediates.mac_entries = self._mac_parser.parse(raw.mac_table_raw)
        intermediates.arp_entries = self._arp_parser.parse(raw.arp_table_raw)
        intermediates.if_entries = self._if_parser.parse(
            raw.interface_status_raw,
        )
        return intermediates

    # ── Phase 2: 依賴呼叫 ────────────────────────────────────────

    async def _phase2_dependent_fetch(
        self,
        switch: SwitchInfo,
        intermediates: _ParsedIntermediates,
        matched_clients: list[MaintenanceMacList],
        tenant_group: TenantGroup,
        source: str | None = None,
        brand: str | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        """
        Phase 2: 依賴 Phase 1 結果的呼叫。

        2a. acl — 需要 interface 清單 (從 mac_table)
        2b. gnms_ping — ping Client 清單中用戶輸入的 IP（只有 MAC 匹配的）

        兩者互不依賴，可並行。
        """
        # 2a: 取出有 MAC 的 interface 清單
        unique_interfaces = sorted({
            e.interface_name
            for e in intermediates.mac_entries
        })

        # 2b: 取得匹配的 Client 的用戶輸入 IP（不是 ARP 的 IP）
        # 只 ping 那些 MAC 在 MAC TABLE 中被採集到的 Client
        client_ips = sorted({
            client.ip_address
            for client in matched_clients
        })

        # 共用 context 欄位
        base_kwargs = {
            "switch_ip": switch.ip_address,
            "switch_hostname": switch.hostname,
            "site": switch.site.value,
            "source": source,
            "brand": brand,
            "vendor": switch.vendor.value,
            "platform": switch.platform.value,
            "http": http,
            "base_url": settings.external_api_server,
            "timeout": settings.external_api_timeout,
        }

        acl_ctx = FetchContext(
            **base_kwargs,
            params={"interfaces": unique_interfaces},
        )

        # 2b: GNMS Ping - 直接 ping client IP
        gnms_ping_ctx = FetchContext(
            **base_kwargs,
            params={
                "switch_ips": client_ips,  # 直接 ping client IP
                "tenant_group": tenant_group,
            },
        )

        acl_fetcher = fetcher_registry.get_or_raise("acl")
        gnms_ping_fetcher = fetcher_registry.get_or_raise("gnms_ping")

        acl_result, ping_result = await asyncio.gather(
            acl_fetcher.fetch(acl_ctx),
            gnms_ping_fetcher.fetch(gnms_ping_ctx),
        )

        if not acl_result.success:
            raise RuntimeError(
                f"Fetch failed for acl on "
                f"{switch.hostname}: {acl_result.error}"
            )
        if not ping_result.success:
            raise RuntimeError(
                f"Fetch failed for gnms_ping on "
                f"{switch.hostname}: {ping_result.error}"
            )

        intermediates.acl_entries = self._acl_parser.parse(
            acl_result.raw_output,
        )

        # 解析 GNMS Ping 結果 (格式: IP,Reachable,Latency_ms)
        # 直接解析每個 client IP 的可達性
        intermediates.ping_entries = self._parse_gnms_ping_result(
            ping_result.raw_output,
        )

    def _parse_gnms_ping_result(
        self,
        raw_output: str,
    ) -> list[PingManyData]:
        """
        解析 GNMS Ping 結果。

        直接解析每個 client IP 的實際可達性結果。

        Args:
            raw_output: GNMS Ping 原始輸出 (CSV: IP,Reachable,Latency_ms)

        Returns:
            每個 client IP 的 ping 結果列表
        """
        ping_entries: list[PingManyData] = []
        lines = raw_output.strip().split("\n")

        for line in lines[1:]:  # 跳過 header
            parts = line.split(",")
            if len(parts) >= 2:
                ip = parts[0].strip()
                reachable = parts[1].strip().lower() == "true"
                ping_entries.append(PingManyData(
                    ip_address=ip,
                    is_reachable=reachable,
                ))

        return ping_entries

    # ── Phase 3: 組裝 ClientRecord ───────────────────────────────

    def _phase3_assemble(
        self,
        switch_hostname: str,
        maintenance_id: str,
        phase: MaintenancePhase,
        intermediates: _ParsedIntermediates,
        mac_whitelist: set[str],
        mac_to_client: dict[str, MaintenanceMacList] | None = None,
    ) -> list[ClientRecord]:
        """
        將各 Fetcher 的中間資料拼裝為 ClientRecord。

        只處理在 mac_whitelist 中的 MAC，確保資料與歲修設定一致。

        以 MAC 為主鍵遍歷 mac_table，關聯其他資料：
        - arp_table: mac → ip
        - interface_status: interface → speed / duplex / link_status
        - acl: interface → acl_number
        - ping_many: ip → is_reachable（使用用戶輸入的 IP 查找）

        Args:
            switch_hostname: 交換機主機名
            maintenance_id: 歲修 ID
            phase: 階段
            intermediates: Fetcher 解析後的中間資料
            mac_whitelist: MAC 白名單（大寫），只處理在此清單中的 MAC
            mac_to_client: {MAC: MaintenanceMacList} 對應表，用於取得用戶輸入的 IP
        """
        now = datetime.now(timezone.utc)

        # 建立 lookup maps
        mac_to_ip: dict[str, str] = {
            e.mac_address: e.ip_address for e in intermediates.arp_entries
        }
        if_status_map: dict[str, InterfaceStatusData] = {
            e.interface_name: e for e in intermediates.if_entries
        }
        acl_map: dict[str, str | None] = {
            e.interface_name: e.acl_number for e in intermediates.acl_entries
        }
        ping_map: dict[str, bool] = {
            e.ip_address: e.is_reachable for e in intermediates.ping_entries
        }

        records: list[ClientRecord] = []
        filtered_count = 0

        for mac_entry in intermediates.mac_entries:
            # 只處理在白名單中的 MAC
            mac_upper = mac_entry.mac_address.upper()
            if mac_upper not in mac_whitelist:
                filtered_count += 1
                continue

            # IP 來自 ARP table（用於記錄）
            ip = mac_to_ip.get(mac_entry.mac_address)
            if_data = if_status_map.get(mac_entry.interface_name)
            acl_number = acl_map.get(mac_entry.interface_name)

            # Ping 結果查找：優先使用用戶輸入的 IP（因為 ping 是用用戶輸入的 IP 做的）
            # 如果沒有 mac_to_client，則 fallback 到 ARP 的 IP
            ping_lookup_ip = None
            if mac_to_client and mac_upper in mac_to_client:
                ping_lookup_ip = mac_to_client[mac_upper].ip_address
            elif ip:
                ping_lookup_ip = ip

            record = ClientRecord(
                maintenance_id=maintenance_id,
                phase=phase,
                collected_at=now,
                # MAC / IP
                mac_address=mac_entry.mac_address,
                ip_address=ip,
                # 網路連接
                switch_hostname=switch_hostname,
                interface_name=mac_entry.interface_name,
                vlan_id=mac_entry.vlan_id,
                # 介面狀態
                speed=if_data.speed if if_data else None,
                duplex=if_data.duplex if if_data else None,
                link_status=if_data.link_status if if_data else None,
                # Ping（使用用戶輸入的 IP 查找結果）
                ping_reachable=(
                    ping_map.get(ping_lookup_ip) if ping_lookup_ip else None
                ),
                # ACL
                acl_rules_applied=acl_number,
                acl_passes=(
                    (acl_number is not None) if acl_number is not None else None
                ),
            )
            records.append(record)

        if filtered_count > 0:
            logger.debug(
                "Filtered %d MACs not in whitelist from %s",
                filtered_count, switch_hostname,
            )

        return records

    # ── Phase 4: 寫入 DB ─────────────────────────────────────────

    async def _phase4_save(
        self,
        session: AsyncSession,
        records: list[ClientRecord],
    ) -> None:
        """批量寫入 ClientRecord 到 client_records 表。"""
        for record in records:
            session.add(record)
        await session.flush()


# ── Singleton ────────────────────────────────────────────────────

_client_collection_service: ClientCollectionService | None = None


def get_client_collection_service() -> ClientCollectionService:
    """Get or create ClientCollectionService instance."""
    global _client_collection_service
    if _client_collection_service is None:
        _client_collection_service = ClientCollectionService()
    return _client_collection_service
