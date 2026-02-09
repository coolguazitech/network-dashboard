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

import asyncio
import logging
from typing import Any

import httpx
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.enums import DeviceType
from app.db.base import get_session_context
from app.db.models import CollectionError, MaintenanceDeviceList, UplinkExpectation
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
        from app.services.change_cache import IndicatorChangeCache

        self.change_cache = IndicatorChangeCache()

    async def collect_indicator_data(
        self,
        collection_type: str,
        maintenance_id: str | None = None,
        force_checkpoint: bool = False,
    ) -> dict[str, Any]:
        """
        Collect data for a specific collection type.

        從 MaintenanceDeviceList 取設備進行採集。

        Args:
            collection_type: Data type (e.g., "transceiver", "ping", "mac-table")
            maintenance_id: APM maintenance ID
            force_checkpoint: True 時強制寫入 DB（整點 checkpoint）

        Returns:
            dict: Collection summary with success/fail counts
        """
        return await self._collect_for_maintenance_devices(
            collection_type=collection_type,
            maintenance_id=maintenance_id,
            force_checkpoint=force_checkpoint,
        )

    async def _collect_for_maintenance_devices(
        self,
        collection_type: str,
        maintenance_id: str | None,
        force_checkpoint: bool = False,
    ) -> dict[str, Any]:
        """
        從 MaintenanceDeviceList 取設備進行採集。

        用於 ping 等需要針對設備採集的採集類型。
        """
        results: dict[str, Any] = {
            "collection_type": collection_type,
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

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                return await self._do_collect(
                    collection_type=collection_type,
                    maintenance_id=maintenance_id,
                    force_checkpoint=force_checkpoint,
                    results=results,
                )
            except Exception as e:
                if "Deadlock" in str(e) and attempt < max_retries:
                    logger.warning(
                        "Deadlock on %s, retrying (%d/%d)",
                        collection_type, attempt + 1, max_retries,
                    )
                    # 重置 results 以便重試
                    results["success"] = 0
                    results["failed"] = 0
                    results["errors"] = []
                    await asyncio.sleep(0.3 * (attempt + 1))
                    continue
                raise

        return results  # unreachable, but satisfies type checker

    async def _do_collect(
        self,
        collection_type: str,
        maintenance_id: str,
        force_checkpoint: bool,
        results: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute collection with a fresh session (retryable on deadlock)."""
        import time as _time

        t0 = _time.monotonic()
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
                            maintenance_id=maintenance_id,
                            typed_repo=typed_repo,
                            http=http,
                            uplink_expectations=uplink_expectations.get(
                                device.new_hostname, []
                            ),
                            force_checkpoint=force_checkpoint,
                        )
                        results["success"] += 1
                        await self._clear_collection_error(
                            session, maintenance_id,
                            collection_type, device.new_hostname,
                        )

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
                        await self._upsert_collection_error(
                            session, maintenance_id,
                            collection_type, device.new_hostname,
                            str(e),
                        )
                        # 寫入 SystemLog 以便管理員定位問題
                        from app.services.system_log import write_log, format_error_detail
                        await write_log(
                            level="WARNING",
                            source="service",
                            summary=f"設備採集失敗: {device.new_hostname} ({collection_type})",
                            detail=format_error_detail(
                                exc=e,
                                context={
                                    "設備": device.new_hostname,
                                    "採集類型": collection_type,
                                    "歲修": maintenance_id,
                                    "廠商": device.new_vendor or "unknown",
                                },
                            ),
                            module="data_collection",
                            maintenance_id=maintenance_id,
                        )

        elapsed = _time.monotonic() - t0
        logger.info(
            "%s for %s: %d/%d ok, %.2fs",
            collection_type,
            maintenance_id,
            results["success"],
            results["total"],
            elapsed,
        )
        return results

    async def _collect_for_maintenance_device(
        self,
        device: MaintenanceDeviceList,
        collection_type: str,
        maintenance_id: str,
        typed_repo: TypedRecordRepository,  # type: ignore[type-arg]
        http: httpx.AsyncClient | None = None,
        uplink_expectations: list[dict[str, str]] | None = None,
        force_checkpoint: bool = False,
    ) -> None:
        """
        對單一 MaintenanceDeviceList 設備進行採集。

        Args:
            device: MaintenanceDeviceList 記錄
            collection_type: 採集類型
            maintenance_id: 歲修 ID
            typed_repo: Typed record 儲存庫
            http: HTTP client（由外層注入）
            uplink_expectations: Uplink 期望值（供 MockUplinkFetcher 使用）
        """
        # 非 ping 採集須先確認新設備可達；ping 本身就是可達性檢查
        # 不可達是預期狀態（尚未 ping 通），靜默跳過即可，不記錄為 CollectionError
        if collection_type != "ping" and device.is_reachable is not True:
            logger.debug(
                "跳過 %s/%s 採集：設備不可達 (is_reachable=%s)",
                device.new_hostname, collection_type, device.is_reachable,
            )
            return

        device_type = DeviceType(device.new_vendor or "HPE")

        # 取得 parser
        parser = parser_registry.get(
            device_type=device_type,
            indicator_type=collection_type,
        )

        if parser is None:
            raise ValueError(
                f"No parser found for "
                f"{device_type}/{collection_type}"
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
            device_type=device_type,
            is_old_device=False,
            tenant_group=device.tenant_group,  # 從資料庫讀取
            params=params,
            http=http,
            maintenance_id=maintenance_id,
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

        # 變更偵測：hash 比對，跳過未變化的 DB 寫入
        data_changed = self.change_cache.has_changed(
            maintenance_id, collection_type,
            device.new_hostname, parsed_items,
        )

        # 同步 ping 可達性到 MaintenanceDeviceList (新設備)
        # 不受快取影響，每次都更新
        if collection_type == "ping" and parsed_items:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            device.is_reachable = parsed_items[0].is_reachable
            device.last_check_at = now

        if not data_changed and not force_checkpoint:
            logger.debug(
                "No change for %s/%s, skipping DB write",
                collection_type, device.new_hostname,
            )
        else:
            # 有變化或 checkpoint → 寫入 typed table
            await typed_repo.save_batch(
                switch_hostname=device.new_hostname,
                raw_data=raw_output,
                parsed_items=parsed_items,
                maintenance_id=maintenance_id,
            )
            logger.info(
                "Collected %s from %s: %d items%s",
                collection_type,
                device.new_hostname,
                len(parsed_items),
                " (checkpoint)" if force_checkpoint and not data_changed else "",
            )

        # 同步 ping 可達性到 MaintenanceDeviceList (舊設備)
        # 這允許時間軸收斂模型：舊設備從可達變不可達，新設備從不可達變可達
        if collection_type == "ping" and device.old_ip_address:
            if device.old_ip_address == device.new_ip_address:
                # 新舊 IP 相同 → 不需重複 ping，直接同步可達性
                device.old_is_reachable = device.is_reachable
                device.old_last_check_at = device.last_check_at
            else:
                # 新舊 IP 不同 → 需要分別 ping 舊設備
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)

                old_fetcher = fetcher_registry.get_or_raise(collection_type)
                old_ctx = FetchContext(
                    switch_ip=device.old_ip_address,
                    switch_hostname=device.old_hostname,
                    device_type=DeviceType(device.old_vendor or "HPE"),
                    is_old_device=True,
                    tenant_group=device.tenant_group,  # 從資料庫讀取
                    http=http,
                    maintenance_id=maintenance_id,
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

    @staticmethod
    async def _clear_collection_error(
        session: Any,
        maintenance_id: str,
        collection_type: str,
        hostname: str,
    ) -> None:
        """成功採集後清除該設備的錯誤紀錄。"""
        await session.execute(
            delete(CollectionError).where(
                CollectionError.maintenance_id == maintenance_id,
                CollectionError.collection_type == collection_type,
                CollectionError.switch_hostname == hostname,
            )
        )

    @staticmethod
    async def _upsert_collection_error(
        session: Any,
        maintenance_id: str,
        collection_type: str,
        hostname: str,
        error_msg: str,
    ) -> None:
        """採集失敗時 UPSERT 錯誤紀錄。"""
        from datetime import datetime, timezone

        # 查詢是否已存在
        stmt = select(CollectionError).where(
            CollectionError.maintenance_id == maintenance_id,
            CollectionError.collection_type == collection_type,
            CollectionError.switch_hostname == hostname,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.error_message = error_msg
            existing.occurred_at = datetime.now(timezone.utc)
        else:
            session.add(CollectionError(
                maintenance_id=maintenance_id,
                collection_type=collection_type,
                switch_hostname=hostname,
                error_message=error_msg,
                occurred_at=datetime.now(timezone.utc),
            ))


# Singleton instance
_collection_service: DataCollectionService | None = None


def get_collection_service() -> DataCollectionService:
    """Get or create DataCollectionService instance."""
    global _collection_service
    if _collection_service is None:
        _collection_service = DataCollectionService()
    return _collection_service
