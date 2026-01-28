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
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import MaintenancePhase
from app.db.base import get_session_context
from app.db.models import ClientRecord, Switch
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

        logger.info(
            "Client collection done: %d/%d switches, %d records",
            results["success"], results["total"],
            results["client_records_count"],
        )
        return results

    # ── per-switch orchestration ─────────────────────────────────

    async def _collect_for_switch(
        self,
        switch: Switch,
        maintenance_id: str,
        phase: MaintenancePhase,
        session: AsyncSession,
        source: str | None = None,
        brand: str | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> list[ClientRecord]:
        """
        單台 switch 的完整採集流程 (Phase 1 → 2 → 3 → 4)。

        Returns:
            寫入 DB 的 ClientRecord 列表。
        """
        # ── Phase 1: 並行 Type A Fetchers ──────────────────
        raw = await self._phase1_parallel_fetch(
            switch, source=source, brand=brand, http=http,
        )
        intermediates = self._phase1_parse(raw)

        # ── Phase 2: 依賴呼叫 ──────────────────────────────
        await self._phase2_dependent_fetch(
            switch, intermediates,
            source=source, brand=brand, http=http,
        )

        # ── Phase 3: 組裝 ClientRecord ─────────────────────
        records = self._phase3_assemble(
            switch_hostname=switch.hostname,
            maintenance_id=maintenance_id,
            phase=phase,
            intermediates=intermediates,
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
        source: str | None = None,
        brand: str | None = None,
        http: httpx.AsyncClient | None = None,
    ) -> None:
        """
        Phase 2: 依賴 Phase 1 結果的呼叫。

        2a. acl — 需要 interface 清單 (從 mac_table)
        2b. ping_many — 需要客戶端 IP 清單 (從 arp)

        兩者互不依賴，可並行。
        """
        # 2a: 取出有 MAC 的 interface 清單
        unique_interfaces = sorted({
            e.interface_name
            for e in intermediates.mac_entries
        })

        # 2b: 透過 MAC → IP 對應取出客戶端 IP
        mac_to_ip = {
            e.mac_address: e.ip_address
            for e in intermediates.arp_entries
        }
        client_ips = [
            mac_to_ip[e.mac_address]
            for e in intermediates.mac_entries
            if e.mac_address in mac_to_ip
        ]

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
        ping_ctx = FetchContext(
            **base_kwargs,
            params={"target_ips": client_ips},
        )

        acl_fetcher = fetcher_registry.get_or_raise("acl")
        ping_fetcher = fetcher_registry.get_or_raise("ping_many")

        acl_result, ping_result = await asyncio.gather(
            acl_fetcher.fetch(acl_ctx),
            ping_fetcher.fetch(ping_ctx),
        )

        if not acl_result.success:
            raise RuntimeError(
                f"Fetch failed for acl on "
                f"{switch.hostname}: {acl_result.error}"
            )
        if not ping_result.success:
            raise RuntimeError(
                f"Fetch failed for ping_many on "
                f"{switch.hostname}: {ping_result.error}"
            )

        intermediates.acl_entries = self._acl_parser.parse(
            acl_result.raw_output,
        )
        intermediates.ping_entries = self._ping_parser.parse(
            ping_result.raw_output,
        )

    # ── Phase 3: 組裝 ClientRecord ───────────────────────────────

    def _phase3_assemble(
        self,
        switch_hostname: str,
        maintenance_id: str,
        phase: MaintenancePhase,
        intermediates: _ParsedIntermediates,
    ) -> list[ClientRecord]:
        """
        將各 Fetcher 的中間資料拼裝為 ClientRecord。

        以 MAC 為主鍵遍歷 mac_table，關聯其他資料：
        - arp_table: mac → ip
        - interface_status: interface → speed / duplex / link_status
        - acl: interface → acl_number
        - ping_many: ip → is_reachable
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

        for mac_entry in intermediates.mac_entries:
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
                acl_passes=(acl_number is not None) if acl_number is not None else None,
            )
            records.append(record)

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
