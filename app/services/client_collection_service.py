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
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.repositories.switch import SwitchRepository
from app.services.api_client import BaseApiClient, get_api_client

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

    def __init__(
        self,
        api_client: BaseApiClient | None = None,
        use_mock: bool = False,
    ) -> None:
        self.api_client = api_client or get_api_client(use_mock=use_mock)

        # Parser instances (skeleton — parse() 待 Fetcher 完成後實作)
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
    ) -> dict[str, Any]:
        """
        主入口：對所有 active switch 採集客戶端資料。

        Returns:
            採集統計 {total, success, failed, errors, client_records_count}
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
                    )
                    results["success"] += 1
                    results["client_records_count"] += len(records)
                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append({
                        "switch": switch.hostname,
                        "error": str(e),
                    })
                    logger.error(
                        "Failed to collect client data from %s: %s",
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
    ) -> list[ClientRecord]:
        """
        單台 switch 的完整採集流程 (Phase 1 → 2 → 3 → 4)。

        Returns:
            寫入 DB 的 ClientRecord 列表。
        """
        site = switch.site.value
        sw_ip = switch.ip_address

        # ── Phase 1: 並行 Type A Fetchers ────────────────────────
        raw = await self._phase1_parallel_fetch(site, sw_ip)
        intermediates = self._phase1_parse(raw)

        # ── Phase 2: 依賴呼叫 ────────────────────────────────────
        await self._phase2_dependent_fetch(
            site, sw_ip, intermediates,
        )

        # ── Phase 3: 組裝 ClientRecord ───────────────────────────
        records = self._phase3_assemble(
            switch_hostname=switch.hostname,
            maintenance_id=maintenance_id,
            phase=phase,
            intermediates=intermediates,
        )

        # ── Phase 4: 寫入 DB ─────────────────────────────────────
        await self._phase4_save(session, records)

        logger.info(
            "Collected %d client records from %s",
            len(records), switch.hostname,
        )
        return records

    # ── Phase 1: 並行呼叫 Type A Fetchers ────────────────────────

    async def _phase1_parallel_fetch(
        self, site: str, sw_ip: str,
    ) -> _FetcherResults:
        """
        並行呼叫 3 個 Type A Fetchers:
        get_mac_table, get_arp_table, get_interface_status

        全部只需 switch_ip，無依賴。
        """
        raw = _FetcherResults()

        mac_task = self.api_client.fetch(site, "get_mac_table", sw_ip)
        arp_task = self.api_client.fetch(site, "get_arp_table", sw_ip)
        if_task = self.api_client.fetch(site, "get_interface_status", sw_ip)

        raw.mac_table_raw, raw.arp_table_raw, raw.interface_status_raw = (
            await asyncio.gather(mac_task, arp_task, if_task)
        )

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
        site: str,
        sw_ip: str,
        intermediates: _ParsedIntermediates,
    ) -> None:
        """
        Phase 2: 依賴 Phase 1 結果的呼叫。

        2a. get_acl_number — 需要 interface 清單 (從 mac_table)
        2b. ping_many — 需要客戶端 IP 清單 (從 mac_table + arp_table)

        兩者互不依賴，可並行。
        """
        # 2a: 取出有 MAC 的 interface 清單
        unique_interfaces = {
            e.interface_name for e in intermediates.mac_entries
        }

        # 2b: 透過 MAC → IP 對應取出客戶端 IP
        mac_to_ip = {e.mac_address: e.ip_address for e in intermediates.arp_entries}
        client_ips = [
            mac_to_ip[e.mac_address]
            for e in intermediates.mac_entries
            if e.mac_address in mac_to_ip
        ]

        # 並行呼叫 ACL + ping_many
        acl_task = self._fetch_acl(site, sw_ip, unique_interfaces)
        ping_task = self._fetch_ping_many(site, sw_ip, client_ips)

        acl_raw, ping_raw = await asyncio.gather(acl_task, ping_task)

        # Parse
        intermediates.acl_entries = self._acl_parser.parse(acl_raw)
        intermediates.ping_entries = self._ping_parser.parse(ping_raw)

    async def _fetch_acl(
        self,
        site: str,
        sw_ip: str,
        interfaces: set[str],
    ) -> str:
        """
        呼叫 get_acl_number Fetcher。

        Fetcher 內部已處理 per-interface 迴圈並聚合結果，
        所以從 service 角度只需一次呼叫。
        """
        # Fetcher 封裝後只需 switch_ip，內部自行迭代 interface
        return await self.api_client.fetch(
            site, "get_acl_number", sw_ip,
        )

    async def _fetch_ping_many(
        self,
        site: str,
        sw_ip: str,
        client_ips: list[str],
    ) -> str:
        """
        呼叫 ping_many Fetcher。

        TODO: 目前透過 api_client.fetch() 呼叫，需確認 ping_many API
              如何接收 target IP 清單（query param / POST body）。
              暫時以 switch_ip 呼叫，Fetcher 端需自行取得 targets。
        """
        if not client_ips:
            return ""

        # TODO: 實際呼叫方式可能需要調整，例如:
        #   - POST body: api_client.post(site, "ping_many", sw_ip, body=client_ips)
        #   - Query param: api_client.fetch(site, "ping_many", sw_ip + "?targets=ip1,ip2")
        # 目前先以標準 fetch 呼叫，Fetcher 端可從 switch 的 ARP table 自行取得 targets
        return await self.api_client.fetch(
            site, "ping_many", sw_ip,
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
        now = datetime.utcnow()

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


def get_client_collection_service(
    use_mock: bool = False,
) -> ClientCollectionService:
    """Get or create ClientCollectionService instance."""
    global _client_collection_service
    if _client_collection_service is None:
        _client_collection_service = ClientCollectionService(
            use_mock=use_mock,
        )
    return _client_collection_service
