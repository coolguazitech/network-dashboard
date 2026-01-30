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
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import ClientDetectionStatus, MaintenancePhase, TenantGroup
from app.db.base import get_session_context
from app.db.models import (
    ClientRecord, Switch, MaintenanceMacList, MaintenanceDeviceList,
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
from app.repositories.switch import SwitchRepository

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
        phase: MaintenancePhase,
        session: AsyncSession,
    ) -> dict[str, TenantGroup]:
        """
        載入設備的 tenant_group 對應表。

        Args:
            maintenance_id: 歲修 ID
            phase: 階段 (OLD/NEW)
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
            if phase == MaintenancePhase.OLD:
                ip = device.old_ip_address
            else:
                ip = device.new_ip_address
            ip_to_tenant_group[ip] = device.tenant_group or TenantGroup.F18

        logger.info(
            "Loaded device tenant_groups for %s: %d devices",
            maintenance_id, len(ip_to_tenant_group),
        )
        return ip_to_tenant_group

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

        async with httpx.AsyncClient() as http:
            async with get_session_context() as session:
                # 載入 MAC 白名單 - 只採集在白名單中的 MAC
                mac_whitelist = await self._load_mac_whitelist(
                    maintenance_id, session,
                )

                if not mac_whitelist:
                    logger.warning(
                        "No MAC whitelist found for %s, "
                        "skipping client collection",
                        maintenance_id,
                    )
                    return results

                # 載入設備 tenant_group 對應表 (用於 GNMS Ping)
                device_tenant_groups = await self._load_device_tenant_groups(
                    maintenance_id, phase, session,
                )

                switch_repo = SwitchRepository(session)
                switches = await switch_repo.get_active_switches()
                results["total"] = len(switches)

                for switch in switches:
                    try:
                        records = await self._collect_for_switch(
                            switch=switch,
                            maintenance_id=maintenance_id,
                            phase=phase,
                            session=session,
                            mac_whitelist=mac_whitelist,
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

    async def detect_clients(
        self,
        maintenance_id: str,
    ) -> dict[str, Any]:
        """
        偵測客戶端狀態。

        流程：
        1. 從 MaintenanceMacList 載入所有 Client（IP + MAC + tenant_group）
        2. 從最新的 ClientRecord 取得 ARP 資料
        3. 檢查 IP-MAC 匹配：若 ARP 中的 IP-MAC 對應與用戶輸入不符 → MISMATCH
        4. 按 tenant_group 分組，呼叫 GNMS Ping 檢查可達性
        5. 更新 MaintenanceMacList.detection_status

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
            "errors": [],
        }

        async with get_session_context() as session:
            # 載入 Client 清單
            clients = await self._load_client_list(maintenance_id, session)
            results["total"] = len(clients)

            if not clients:
                logger.warning("No clients found for %s", maintenance_id)
                return results

            # 先重置所有 clients 的偵測狀態為 NOT_CHECKED
            # 確保每次偵測都是全新的開始
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

            # 從 ClientRecord 取得最新的 ARP 資料（MAC → IP）
            arp_mac_to_ip = await self._get_latest_arp_mapping(
                maintenance_id, session,
            )

            # 檢查 IP-MAC 匹配，找出不匹配的 clients
            mismatch_client_ids = set()
            for client in clients:
                mac_upper = client.mac_address.upper()
                if mac_upper in arp_mac_to_ip:
                    arp_ip = arp_mac_to_ip[mac_upper]
                    if arp_ip != client.ip_address:
                        # ARP 中的 IP 與用戶輸入不符
                        mismatch_client_ids.add(client.id)
                        await self._update_client_detection_status(
                            session, client.id, ClientDetectionStatus.MISMATCH,
                        )
                        results["mismatch"] += 1

            # 過濾掉已標記為 MISMATCH 的 clients
            ping_clients = [
                c for c in clients
                if c.id not in mismatch_client_ids
            ]

            # 按 tenant_group 分組
            by_tenant: dict[TenantGroup, list[MaintenanceMacList]] = {}
            for client in ping_clients:
                tg = client.tenant_group or TenantGroup.F18
                by_tenant.setdefault(tg, []).append(client)

            # 對每個 tenant_group 呼叫 GNMS Ping
            for tenant_group, group_clients in by_tenant.items():
                client_ips = [c.ip_address for c in group_clients]

                try:
                    reachable_ips = await self._ping_client_ips(
                        client_ips, tenant_group,
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
            "%d not_detected",
            maintenance_id,
            results["detected"],
            results["mismatch"],
            results["not_detected"],
        )
        return results

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
    ) -> set[str]:
        """
        使用 GNMS Ping 檢查客戶端 IP 可達性。

        Args:
            client_ips: 要 ping 的客戶端 IP 列表
            tenant_group: Tenant group

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
        switch: Switch,
        maintenance_id: str,
        phase: MaintenancePhase,
        session: AsyncSession,
        mac_whitelist: set[str],
        device_tenant_groups: dict[str, TenantGroup],
        source: str | None = None,
        brand: str | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> list[ClientRecord]:
        """
        單台 switch 的完整採集流程 (Phase 1 → 2 → 3 → 4)。

        Args:
            switch: 目標設備
            maintenance_id: 歲修 ID
            phase: 階段
            session: DB session
            mac_whitelist: MAC 白名單，只採集在此清單中的 MAC
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

        # ── Phase 2: 依賴呼叫 (使用 GNMS Ping) ──────────────
        await self._phase2_dependent_fetch(
            switch, intermediates,
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
        )

        # ── Phase 4: 寫入 DB ───────────────────────────────
        await self._phase4_save(session, records)

        logger.info(
            "Collected %d client records from %s",
            len(records), switch.hostname,
        )
        return records

    # ── Phase 1: 並行呼叫 Type A Fetchers ────────────────────────

    async def _phase1_parallel_fetch(
        self,
        switch: Switch,
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
        switch: Switch,
        intermediates: _ParsedIntermediates,
        tenant_group: TenantGroup,
        source: str | None = None,
        brand: str | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        """
        Phase 2: 依賴 Phase 1 結果的呼叫。

        2a. acl — 需要 interface 清單 (從 mac_table)
        2b. gnms_ping — 使用 switch IP + tenant_group 呼叫 GNMS Ping API

        兩者互不依賴，可並行。
        """
        # 2a: 取出有 MAC 的 interface 清單
        unique_interfaces = sorted({
            e.interface_name
            for e in intermediates.mac_entries
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

        # 2b: GNMS Ping - 使用 switch IP + tenant_group
        gnms_ping_ctx = FetchContext(
            **base_kwargs,
            params={
                "switch_ips": [switch.ip_address],
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
        # 轉換為 PingManyData 格式供後續處理使用
        intermediates.ping_entries = self._parse_gnms_ping_result(
            ping_result.raw_output,
            intermediates,
        )

    def _parse_gnms_ping_result(
        self,
        raw_output: str,
        intermediates: _ParsedIntermediates,
    ) -> list[PingManyData]:
        """
        解析 GNMS Ping 結果並映射到客戶端 IP。

        GNMS Ping 回傳的是 switch-level 結果，需要映射到所有客戶端 IP。
        如果 switch 可達，則該 switch 上的所有客戶端都視為可達。

        Args:
            raw_output: GNMS Ping 原始輸出 (CSV: IP,Reachable,Latency_ms)
            intermediates: 中間資料（包含 MAC/ARP entries）

        Returns:
            客戶端 IP 的 ping 結果列表
        """
        # 解析 GNMS Ping 結果 (switch-level)
        switch_reachable = True  # 預設可達
        lines = raw_output.strip().split("\n")
        for line in lines[1:]:  # 跳過 header
            parts = line.split(",")
            if len(parts) >= 2:
                reachable_str = parts[1].strip().lower()
                switch_reachable = reachable_str == "true"
                break  # 只有一個 switch

        # 建立 MAC → IP 對應
        mac_to_ip = {
            e.mac_address: e.ip_address
            for e in intermediates.arp_entries
        }

        # 將 switch-level 結果映射到所有客戶端 IP
        ping_entries: list[PingManyData] = []
        for mac_entry in intermediates.mac_entries:
            ip = mac_to_ip.get(mac_entry.mac_address)
            if ip:
                ping_entries.append(PingManyData(
                    ip_address=ip,
                    is_reachable=switch_reachable,
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
    ) -> list[ClientRecord]:
        """
        將各 Fetcher 的中間資料拼裝為 ClientRecord。

        只處理在 mac_whitelist 中的 MAC，確保資料與歲修設定一致。

        以 MAC 為主鍵遍歷 mac_table，關聯其他資料：
        - arp_table: mac → ip
        - interface_status: interface → speed / duplex / link_status
        - acl: interface → acl_number
        - ping_many: ip → is_reachable

        Args:
            switch_hostname: 交換機主機名
            maintenance_id: 歲修 ID
            phase: 階段
            intermediates: Fetcher 解析後的中間資料
            mac_whitelist: MAC 白名單（大寫），只處理在此清單中的 MAC
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

            ip = mac_to_ip.get(mac_entry.mac_address)
            if_data = if_status_map.get(mac_entry.interface_name)
            acl_number = acl_map.get(mac_entry.interface_name)

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
                # Ping
                ping_reachable=(
                    ping_map.get(ip) if ip else None
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
