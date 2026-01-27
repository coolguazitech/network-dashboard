"""
Data Collection Service.

Responsible for collecting raw data from external API and storing to DB.

採集流程：
1. 從設備清單獲取目標設備（switches 表或 MaintenanceDeviceList）
2. 對每台設備呼叫外部 API 取得原始資料
3. 使用 Parser 解析原始資料
4. 存入 typed record 表供指標評估使用
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from app.core.enums import MaintenancePhase, PlatformType, VendorType
from app.db.base import get_session_context
from app.db.models import Switch, MaintenanceDeviceList
from app.parsers import BaseParser, parser_registry
from app.repositories.switch import SwitchRepository
from app.repositories.typed_records import TypedRecordRepository, get_typed_repo
from app.services.api_client import BaseApiClient, get_api_client

logger = logging.getLogger(__name__)

# 需要從 MaintenanceDeviceList 取新設備的採集類型
MAINTENANCE_DEVICE_COLLECTIONS = {"ping"}


class DataCollectionService:
    """
    Service for collecting data from external API.

    Flow:
    1. Get list of active switches
    2. For each switch, call external API
    3. Parse raw output using appropriate parser
    4. Store parsed data to collection_records table
    """

    def __init__(
        self,
        api_client: BaseApiClient | None = None,
        use_mock: bool = False,
    ) -> None:
        """
        Initialize service.

        Args:
            api_client: API client instance (optional)
            use_mock: Use mock API client for testing
        """
        self.api_client = api_client or get_api_client(use_mock=use_mock)

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

        根據 collection_type 決定設備來源：
        - ping: 從 MaintenanceDeviceList 取新設備
        - 其他: 從 switches 表取活躍設備

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
        # Ping 需要從 MaintenanceDeviceList 取新設備
        if collection_type in MAINTENANCE_DEVICE_COLLECTIONS:
            return await self._collect_for_maintenance_devices(
                collection_type=collection_type,
                phase=phase,
                maintenance_id=maintenance_id,
            )

        # 其他從 switches 表取設備
        return await self._collect_for_switches(
            collection_type=collection_type,
            phase=phase,
            maintenance_id=maintenance_id,
        )

    async def _collect_for_switches(
        self,
        collection_type: str,
        phase: MaintenancePhase,
        maintenance_id: str | None,
    ) -> dict[str, Any]:
        """從 switches 表採集資料。"""
        results = {
            "collection_type": collection_type,
            "phase": phase.value,
            "total": 0,
            "success": 0,
            "failed": 0,
            "errors": [],
        }

        async with get_session_context() as session:
            switch_repo = SwitchRepository(session)
            typed_repo = get_typed_repo(collection_type, session)

            # Get all active switches
            switches = await switch_repo.get_active_switches()
            results["total"] = len(switches)

            for switch in switches:
                try:
                    await self._collect_for_switch(
                        switch=switch,
                        collection_type=collection_type,
                        phase=phase,
                        maintenance_id=maintenance_id,
                        typed_repo=typed_repo,
                    )
                    results["success"] += 1

                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append({
                        "switch": switch.hostname,
                        "error": str(e),
                    })
                    logger.error(
                        f"Failed to collect {collection_type} "
                        f"from {switch.hostname}: {e}"
                    )

        return results

    async def _collect_for_maintenance_devices(
        self,
        collection_type: str,
        phase: MaintenancePhase,
        maintenance_id: str | None,
    ) -> dict[str, Any]:
        """
        從 MaintenanceDeviceList 取新設備進行採集。

        用於 ping 等需要針對新設備採集的採集類型。
        """
        results = {
            "collection_type": collection_type,
            "phase": phase.value,
            "total": 0,
            "success": 0,
            "failed": 0,
            "errors": [],
        }

        if not maintenance_id:
            logger.warning(
                f"No maintenance_id provided for {collection_type}, skipping"
            )
            return results

        async with get_session_context() as session:
            typed_repo = get_typed_repo(collection_type, session)

            # 從 MaintenanceDeviceList 取新設備
            stmt = select(MaintenanceDeviceList).where(
                MaintenanceDeviceList.maintenance_id == maintenance_id
            )
            result = await session.execute(stmt)
            devices = result.scalars().all()
            results["total"] = len(devices)

            for device in devices:
                try:
                    await self._collect_for_maintenance_device(
                        device=device,
                        collection_type=collection_type,
                        phase=phase,
                        maintenance_id=maintenance_id,
                        typed_repo=typed_repo,
                    )
                    results["success"] += 1

                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append({
                        "switch": device.new_hostname,
                        "error": str(e),
                    })
                    logger.error(
                        f"Failed to collect {collection_type} "
                        f"from {device.new_hostname}: {e}"
                    )

        return results

    async def _collect_for_maintenance_device(
        self,
        device: MaintenanceDeviceList,
        collection_type: str,
        phase: MaintenancePhase,
        maintenance_id: str,
        typed_repo: TypedRecordRepository,  # type: ignore[type-arg]
    ) -> None:
        """
        對單一 MaintenanceDeviceList 設備進行採集。

        Args:
            device: MaintenanceDeviceList 記錄
            collection_type: 採集類型
            phase: 階段
            maintenance_id: 歲修 ID
            typed_repo: Typed record 儲存庫
        """
        # 使用新設備的 vendor 決定 parser（處理大小寫）
        vendor = (
            VendorType(device.new_vendor.lower())
            if device.new_vendor
            else VendorType.HPE
        )

        # 根據 vendor 決定 platform（簡化處理）
        platform_map = {
            VendorType.HPE: PlatformType.HPE_COMWARE,
            VendorType.CISCO: PlatformType.CISCO_NXOS,
        }
        platform = platform_map.get(vendor, PlatformType.HPE_COMWARE)

        # 取得 parser
        parser = parser_registry.get(
            vendor=vendor,
            platform=platform,
            indicator_type=collection_type,
        )

        if parser is None:
            raise ValueError(
                f"No parser found for {vendor}/{platform}/{collection_type}"
            )

        # 建立 API function name
        api_function = f"get_{collection_type}"

        # 使用新設備 IP 呼叫外部 API
        raw_output = await self.api_client.fetch(
            site="maintenance",  # 使用特定 site 標識
            function=api_function,
            switch_ip=device.new_ip_address,
        )

        # 解析原始資料
        parsed_items = parser.parse(raw_output)

        # 存入 typed table（使用 new_hostname 作為 switch_hostname）
        await typed_repo.save_batch(
            switch_hostname=device.new_hostname,
            raw_data=raw_output,
            parsed_items=parsed_items,
            phase=phase,
            maintenance_id=maintenance_id,
        )

        # 同步 ping 可達性到 MaintenanceDeviceList
        if collection_type == "ping" and parsed_items:
            from datetime import datetime
            device.is_reachable = parsed_items[0].is_reachable
            device.last_check_at = datetime.utcnow()

        logger.info(
            f"Collected {collection_type} from {device.new_hostname}: "
            f"{len(parsed_items)} items"
        )

    async def _collect_for_switch(
        self,
        switch: Switch,
        collection_type: str,
        phase: MaintenancePhase,
        maintenance_id: str | None,
        typed_repo: TypedRecordRepository,  # type: ignore[type-arg]
    ) -> None:
        """
        Collect data for a single switch.

        Args:
            switch: Switch model instance
            collection_type: Collection type (e.g. "transceiver")
            phase: Maintenance phase
            maintenance_id: Maintenance job ID
            typed_repo: Typed record repository
        """
        # Get appropriate parser
        parser = parser_registry.get(
            vendor=switch.vendor,
            platform=switch.platform,
            indicator_type=collection_type,
        )

        if parser is None:
            raise ValueError(
                f"No parser found for {switch.vendor}/{switch.platform}"
                f"/{collection_type}"
            )

        # Build API function name from collection type
        api_function = f"get_{collection_type}"

        # Call external API
        raw_output = await self.api_client.fetch(
            site=switch.site.value,
            function=api_function,
            switch_ip=switch.ip_address,
        )

        # Parse raw output
        parsed_items = parser.parse(raw_output)

        # Save to typed table
        await typed_repo.save_batch(
            switch_hostname=switch.hostname,
            raw_data=raw_output,
            parsed_items=parsed_items,
            phase=phase,
            maintenance_id=maintenance_id or "",
        )

        logger.info(
            f"Collected {collection_type} from {switch.hostname}: "
            f"{len(parsed_items)} items"
        )

    async def collect_for_specific_switches(
        self,
        switch_hostnames: list[str],
        collection_type: str,
        phase: MaintenancePhase = MaintenancePhase.NEW,
        maintenance_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Collect data for specific switches only.

        Args:
            switch_hostnames: List of switch hostnames
            collection_type: Collection type (e.g. "transceiver")
            phase: Maintenance phase
            maintenance_id: Maintenance job ID

        Returns:
            dict: Collection summary
        """
        results = {
            "collection_type": collection_type,
            "phase": phase.value,
            "total": len(switch_hostnames),
            "success": 0,
            "failed": 0,
            "errors": [],
        }

        async with get_session_context() as session:
            switch_repo = SwitchRepository(session)
            typed_repo = get_typed_repo(collection_type, session)

            for hostname in switch_hostnames:
                switch = await switch_repo.get_by_hostname(hostname)

                if switch is None:
                    results["failed"] += 1
                    results["errors"].append({
                        "switch": hostname,
                        "error": "Switch not found",
                    })
                    continue

                try:
                    await self._collect_for_switch(
                        switch=switch,
                        collection_type=collection_type,
                        phase=phase,
                        maintenance_id=maintenance_id,
                        typed_repo=typed_repo,
                    )
                    results["success"] += 1

                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append({
                        "switch": hostname,
                        "error": str(e),
                    })

        return results


# Singleton instance
_collection_service: DataCollectionService | None = None


def get_collection_service(use_mock: bool = False) -> DataCollectionService:
    """
    Get or create DataCollectionService instance.

    Args:
        use_mock: Use mock API client

    Returns:
        DataCollectionService instance
    """
    global _collection_service
    if _collection_service is None:
        _collection_service = DataCollectionService(use_mock=use_mock)
    return _collection_service
