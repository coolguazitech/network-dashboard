"""
Data Collection Service.

Responsible for collecting raw data from external API and storing to DB.

採集流程：
1. 從 MaintenanceDeviceList 獲取目標設備
2. 對每台設備呼叫外部 Fetcher 取得原始資料
3. 使用 Parser 解析原始資料
4. 存入 typed record 表供指標評估使用
"""
from __future__ import annotations

import logging
from typing import Any

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.enums import MaintenancePhase, PlatformType, VendorType
from app.db.base import get_session_context
from app.db.models import MaintenanceDeviceList, UplinkExpectation
from app.fetchers.base import FetchContext
from app.fetchers.registry import fetcher_registry
from app.parsers import parser_registry
from app.repositories.typed_records import (
    TypedRecordRepository,
    get_typed_repo,
)

logger = logging.getLogger(__name__)


class DataCollectionService:
    """
    Service for collecting data from external API.

    Flow:
    1. Get list of devices from MaintenanceDeviceList
    2. For each device, call Fetcher to get raw data
    3. Parse raw output using appropriate parser
    4. Store parsed data to typed record table
    """

    def __init__(self) -> None:
        """Initialize service."""
        pass

    async def collect_indicator_data(
        self,
        collection_type: str,
        phase: MaintenancePhase = MaintenancePhase.NEW,
        maintenance_id: str | None = None,
        url: str | None = None,
        source: str | None = None,
        brand: str | None = None,
    ) -> dict[str, Any]:
        """
        Collect data for a specific collection type.

        從 MaintenanceDeviceList 取設備進行採集。

        Args:
            collection_type: Data type (e.g., "transceiver", "ping", "mac-table")
            phase: Maintenance phase (OLD/NEW)
            maintenance_id: APM maintenance ID
            url: External API endpoint URL (from scheduler config)
            source: Data source identifier (FNA/DNA)
            brand: Device brand (HPE/Cisco-IOS/Cisco-NXOS)

        Returns:
            dict: Collection summary with success/fail counts
        """
        return await self._collect_for_maintenance_devices(
            collection_type=collection_type,
            phase=phase,
            maintenance_id=maintenance_id,
            source=source,
            brand=brand,
        )

    async def _collect_for_maintenance_devices(
        self,
        collection_type: str,
        phase: MaintenancePhase,
        maintenance_id: str | None,
        source: str | None = None,
        brand: str | None = None,
    ) -> dict[str, Any]:
        """
        從 MaintenanceDeviceList 取設備進行採集。

        用於 ping 等需要針對設備採集的採集類型。
        """
        results: dict[str, Any] = {
            "collection_type": collection_type,
            "phase": phase.value,
            "total": 0,
            "success": 0,
            "failed": 0,
            "errors": [],
        }

        if not maintenance_id:
            logger.warning(
                "No maintenance_id for %s, skipping",
                collection_type,
            )
            return results

        async with httpx.AsyncClient() as http:
            async with get_session_context() as session:
                typed_repo = get_typed_repo(
                    collection_type, session,
                )

                stmt = select(MaintenanceDeviceList).where(
                    MaintenanceDeviceList.maintenance_id
                    == maintenance_id
                )
                result = await session.execute(stmt)
                devices = result.scalars().all()
                results["total"] = len(devices)

                # 預先載入 uplink 期望值（供 MockUplinkFetcher 使用）
                uplink_expectations: dict[str, list[dict[str, str]]] = {}
                if collection_type == "uplink":
                    uplink_expectations = await self._load_uplink_expectations(
                        session, maintenance_id
                    )

                for device in devices:
                    try:
                        await self._collect_for_maintenance_device(
                            device=device,
                            collection_type=collection_type,
                            phase=phase,
                            maintenance_id=maintenance_id,
                            typed_repo=typed_repo,
                            source=source,
                            brand=brand,
                            http=http,
                            uplink_expectations=uplink_expectations.get(
                                device.new_hostname, []
                            ),
                        )
                        results["success"] += 1

                    except Exception as e:
                        results["failed"] += 1
                        results["errors"].append({
                            "switch": device.new_hostname,
                            "error": str(e),
                        })
                        logger.error(
                            "Failed to collect %s from %s: %s",
                            collection_type,
                            device.new_hostname,
                            e,
                        )

        return results

    async def _collect_for_maintenance_device(
        self,
        device: MaintenanceDeviceList,
        collection_type: str,
        phase: MaintenancePhase,
        maintenance_id: str,
        typed_repo: TypedRecordRepository,  # type: ignore[type-arg]
        source: str | None = None,
        brand: str | None = None,
        http: httpx.AsyncClient | None = None,
        uplink_expectations: list[dict[str, str]] | None = None,
    ) -> None:
        """
        對單一 MaintenanceDeviceList 設備進行採集。

        Args:
            device: MaintenanceDeviceList 記錄
            collection_type: 採集類型
            phase: 階段
            maintenance_id: 歲修 ID
            typed_repo: Typed record 儲存庫
            source: Data source identifier (FNA/DNA)
            brand: Device brand (HPE/Cisco-IOS/Cisco-NXOS)
            http: HTTP client（由外層注入）
            uplink_expectations: Uplink 期望值（供 MockUplinkFetcher 使用）
        """
        # 使用新設備的 vendor 決定 parser（處理 Cisco-IOS/Cisco-NXOS 等格式）
        vendor_str = (device.new_vendor or "").lower()
        if vendor_str.startswith("cisco"):
            vendor = VendorType.CISCO
        elif vendor_str.startswith("hpe") or vendor_str.startswith("aruba"):
            vendor = VendorType.HPE
        else:
            vendor = VendorType.HPE

        # 根據 vendor 和原始 vendor_str 決定 platform
        if vendor == VendorType.CISCO:
            if "nxos" in vendor_str:
                platform = PlatformType.CISCO_NXOS
            else:
                platform = PlatformType.CISCO_IOS
        else:
            platform = PlatformType.HPE_COMWARE

        # 取得 parser
        parser = parser_registry.get(
            vendor=vendor,
            platform=platform,
            indicator_type=collection_type,
        )

        if parser is None:
            raise ValueError(
                f"No parser found for "
                f"{vendor}/{platform}/{collection_type}"
            )

        # 透過 Fetcher 取得原始資料
        fetcher = fetcher_registry.get_or_raise(collection_type)

        # 建立 params（包含 uplink 期望值供 MockFetcher 使用）
        params: dict[str, Any] = {}
        if uplink_expectations:
            params["uplink_expectations"] = uplink_expectations

        ctx = FetchContext(
            switch_ip=device.new_ip_address,
            switch_hostname=device.new_hostname,
            site="maintenance",
            source=source,
            brand=brand,
            vendor=vendor.value,
            platform=platform.value,
            params=params,
            http=http,
            base_url=settings.external_api_server,
            timeout=settings.external_api_timeout,
        )
        result = await fetcher.fetch(ctx)
        if not result.success:
            raise RuntimeError(
                f"Fetch failed for {collection_type} on "
                f"{device.new_hostname}: {result.error}"
            )
        raw_output = result.raw_output

        # 解析原始資料
        parsed_items = parser.parse(raw_output)

        # 存入 typed table
        await typed_repo.save_batch(
            switch_hostname=device.new_hostname,
            raw_data=raw_output,
            parsed_items=parsed_items,
            phase=phase,
            maintenance_id=maintenance_id,
        )

        # 同步 ping 可達性到 MaintenanceDeviceList (新設備)
        if collection_type == "ping" and parsed_items:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            device.is_reachable = parsed_items[0].is_reachable
            device.last_check_at = now

        logger.info(
            "Collected %s from %s: %d items",
            collection_type,
            device.new_hostname,
            len(parsed_items),
        )

        # 同步 ping 可達性到 MaintenanceDeviceList (舊設備)
        # 這允許時間軸收斂模型：舊設備從可達變不可達，新設備從不可達變可達
        if collection_type == "ping" and device.old_ip_address:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)

            # 對舊設備執行 ping
            old_fetcher = fetcher_registry.get_or_raise(collection_type)
            old_ctx = FetchContext(
                switch_ip=device.old_ip_address,
                switch_hostname=device.old_hostname,
                site="maintenance",
                source=source,
                brand=brand,
                vendor=vendor.value,
                platform=platform.value,
                http=http,
                base_url=settings.external_api_server,
                timeout=settings.external_api_timeout,
            )
            try:
                old_result = await old_fetcher.fetch(old_ctx)
                if old_result.success:
                    old_parsed = parser.parse(old_result.raw_output)
                    if old_parsed:
                        device.old_is_reachable = old_parsed[0].is_reachable
                        device.old_last_check_at = now
                        logger.info(
                            "Collected ping from OLD device %s: reachable=%s",
                            device.old_hostname,
                            device.old_is_reachable,
                        )
            except Exception as e:
                logger.warning(
                    "Failed to ping OLD device %s: %s",
                    device.old_hostname,
                    e,
                )

    async def _load_uplink_expectations(
        self,
        session: Any,
        maintenance_id: str,
    ) -> dict[str, list[dict[str, str]]]:
        """
        載入 Uplink 期望值，按 hostname 分組。

        Returns:
            dict: hostname -> list of {local_interface, expected_neighbor, expected_interface}
        """
        from collections import defaultdict

        stmt = select(UplinkExpectation).where(
            UplinkExpectation.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        expectations = result.scalars().all()

        grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
        for exp in expectations:
            grouped[exp.hostname].append({
                "local_interface": exp.local_interface,
                "expected_neighbor": exp.expected_neighbor,
                "expected_interface": exp.expected_interface,
            })

        return dict(grouped)


# Singleton instance
_collection_service: DataCollectionService | None = None


def get_collection_service() -> DataCollectionService:
    """Get or create DataCollectionService instance."""
    global _collection_service
    if _collection_service is None:
        _collection_service = DataCollectionService()
    return _collection_service
