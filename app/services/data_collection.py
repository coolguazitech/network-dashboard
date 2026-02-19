"""
API Collection Service — 純採集服務。

職責只有三件事：fetch → parse → save DB。
不做可達性判斷、不做變更偵測、不做 indicator 邏輯。
每個 API 採集項目彼此獨立，互不干涉。

採集流程：
1. 從 MaintenanceDeviceList 獲取目標設備
2. 對每台設備：
   a. Fetcher 取得 raw CLI output
   b. Parser 解析為 list[ParsedData]
   c. TypedRecordRepo.save_batch() 寫入 DB

Parser command 組合規則：
    {api_name}_{device_type}_{source}
    e.g. get_fan + hpe + dna → get_fan_hpe_dna
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from typing import Any

import httpx
from sqlalchemy import delete, select

from app.core.enums import DeviceType
from app.db.base import get_session_context
from app.db.models import CollectionError, MaintenanceDeviceList
from app.fetchers.base import FetchContext
from app.fetchers.registry import fetcher_registry
from app.parsers import parser_registry
from app.repositories.typed_records import get_typed_repo

logger = logging.getLogger(__name__)


class ApiCollectionService:
    """
    純 API 採集服務 — Scheduler 的執行引擎。

    每個 scheduler job 觸發時呼叫 collect()，傳入 api_name + source。
    對該歲修的所有設備執行 fetch → parse → save。
    """

    async def collect(
        self,
        api_name: str,
        source: str,
        maintenance_id: str,
    ) -> dict[str, Any]:
        """
        對一個歲修的所有設備採集一個 API。

        Args:
            api_name: scheduler.yaml key, e.g. "get_fan"
            source: API 來源, e.g. "FNA" or "DNA"
            maintenance_id: 歲修 ID

        Returns:
            dict: {api_name, total, success, failed, errors}
        """
        results: dict[str, Any] = {
            "api_name": api_name,
            "total": 0,
            "success": 0,
            "failed": 0,
            "errors": [],
        }

        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                return await self._do_collect(
                    api_name=api_name,
                    source=source,
                    maintenance_id=maintenance_id,
                    results=results,
                )
            except Exception as e:
                if "Deadlock" in str(e) and attempt < max_retries:
                    logger.warning(
                        "Deadlock on %s, retrying (%d/%d)",
                        api_name, attempt + 1, max_retries,
                    )
                    results["success"] = 0
                    results["failed"] = 0
                    results["errors"] = []
                    await asyncio.sleep(0.3 * (attempt + 1))
                    continue
                raise

        return results  # unreachable, but satisfies type checker

    async def _do_collect(
        self,
        api_name: str,
        source: str,
        maintenance_id: str,
        results: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute collection with a fresh session (retryable on deadlock)."""
        t0 = _time.monotonic()

        async with httpx.AsyncClient() as http:
            async with get_session_context() as session:
                # 1. Typed repo for this API
                typed_repo = get_typed_repo(api_name, session)

                # 2. Get target devices (only those with new_hostname for collection)
                stmt = select(MaintenanceDeviceList).where(
                    MaintenanceDeviceList.maintenance_id == maintenance_id,
                    MaintenanceDeviceList.new_hostname != None,  # noqa: E711
                    MaintenanceDeviceList.new_ip_address != None,  # noqa: E711
                )
                result = await session.execute(stmt)
                devices = result.scalars().all()
                results["total"] = len(devices)

                # 3. Fetch + parse + save per device
                #    每台設備用 SAVEPOINT 隔離，避免單一設備的 DB 錯誤
                #    導致 session 壞掉、後續設備全部失敗。
                for device in devices:
                    try:
                        async with session.begin_nested():
                            await self._collect_device(
                                device=device,
                                api_name=api_name,
                                source=source,
                                maintenance_id=maintenance_id,
                                typed_repo=typed_repo,
                                http=http,
                            )
                            # 成功 → 清除該設備的錯誤紀錄
                            await self._clear_collection_error(
                                session, maintenance_id,
                                api_name, device.new_hostname,
                            )
                        results["success"] += 1

                    except Exception as e:
                        results["failed"] += 1
                        results["errors"].append({
                            "switch": device.new_hostname,
                            "error": str(e),
                        })
                        logger.error(
                            "Failed %s from %s: %s",
                            api_name, device.new_hostname, e,
                        )

                        # 記錄 CollectionError（Dashboard 顯示用）
                        try:
                            async with session.begin_nested():
                                await self._upsert_collection_error(
                                    session, maintenance_id,
                                    api_name, device.new_hostname, str(e),
                                )
                        except Exception:
                            logger.error(
                                "Failed to record CollectionError for %s",
                                device.new_hostname,
                            )

                        # 寫入 SystemLog（使用獨立 session，不受主 session 影響）
                        from app.services.system_log import (
                            write_log,
                            format_error_detail,
                        )
                        await write_log(
                            level="WARNING",
                            source="service",
                            summary=f"採集失敗: {device.new_hostname} ({api_name})",
                            detail=format_error_detail(
                                exc=e,
                                context={
                                    "設備": device.new_hostname,
                                    "API": api_name,
                                    "歲修": maintenance_id,
                                    "廠商": device.new_vendor or "unknown",
                                },
                            ),
                            module="data_collection",
                            maintenance_id=maintenance_id,
                        )

                # ping_batch 特殊處理：也對老設備 IP 做 Ping
                # Ping 是唯一新舊設備都要觀察的 API
                if api_name == "ping_batch":
                    for device in devices:
                        if (device.old_hostname
                                and device.old_ip_address
                                and device.old_ip_address != device.new_ip_address):
                            try:
                                async with session.begin_nested():
                                    await self._collect_for_target(
                                        hostname=device.old_hostname,
                                        ip_address=device.old_ip_address,
                                        vendor=device.old_vendor,
                                        tenant_group=device.tenant_group,
                                        api_name=api_name,
                                        source=source,
                                        maintenance_id=maintenance_id,
                                        typed_repo=typed_repo,
                                        http=http,
                                    )
                                    await self._clear_collection_error(
                                        session, maintenance_id,
                                        api_name, device.old_hostname,
                                    )
                            except Exception as e:
                                logger.warning(
                                    "Failed %s for old device %s: %s",
                                    api_name, device.old_hostname, e,
                                )
                                try:
                                    async with session.begin_nested():
                                        await self._upsert_collection_error(
                                            session, maintenance_id,
                                            api_name, device.old_hostname,
                                            str(e),
                                        )
                                except Exception:
                                    logger.error(
                                        "Failed to record CollectionError for old device %s",
                                        device.old_hostname,
                                    )
                                from app.services.system_log import (
                                    write_log,
                                    format_error_detail,
                                )
                                await write_log(
                                    level="WARNING",
                                    source="service",
                                    summary=f"老設備採集失敗: {device.old_hostname} ({api_name})",
                                    detail=format_error_detail(
                                        exc=e,
                                        context={
                                            "設備": device.old_hostname,
                                            "IP": device.old_ip_address,
                                            "API": api_name,
                                            "歲修": maintenance_id,
                                            "類型": "舊設備",
                                        },
                                    ),
                                    module="data_collection",
                                    maintenance_id=maintenance_id,
                                )

        elapsed = _time.monotonic() - t0
        logger.info(
            "%s for %s: %d/%d ok, %.2fs",
            api_name, maintenance_id,
            results["success"], results["total"], elapsed,
        )
        return results

    async def _collect_device(
        self,
        device: MaintenanceDeviceList,
        api_name: str,
        source: str,
        maintenance_id: str,
        typed_repo: Any,
        http: httpx.AsyncClient,
    ) -> None:
        """對單一新設備執行 fetch → parse → save。"""
        await self._collect_for_target(
            hostname=device.new_hostname,
            ip_address=device.new_ip_address,
            vendor=device.new_vendor,
            tenant_group=device.tenant_group,
            api_name=api_name,
            source=source,
            maintenance_id=maintenance_id,
            typed_repo=typed_repo,
            http=http,
        )

    async def _collect_for_target(
        self,
        *,
        hostname: str,
        ip_address: str,
        vendor: str | None,
        tenant_group: str | None,
        api_name: str,
        source: str,
        maintenance_id: str,
        typed_repo: Any,
        http: httpx.AsyncClient,
    ) -> None:
        """
        對單一目標（hostname/IP）執行 fetch → parse → save。

        Parser command = {api_name}_{device_type}_{source}
        e.g. get_fan + hpe + dna → get_fan_hpe_dna
        """
        device_type = DeviceType(vendor or "HPE")

        # 1. Build parser command
        parser_command = (
            f"{api_name}_{device_type.api_value}_{source.lower()}"
        )

        # 2. Get parser (with fallback for universal parsers like ping_batch)
        parser = parser_registry.get(
            command=parser_command,
            device_type=device_type,
        )
        if parser is None:
            parser = parser_registry.get(
                command=api_name,
                device_type=device_type,
            )
        if parser is None:
            raise ValueError(
                f"No parser for '{parser_command}' "
                f"(device_type={device_type.value})"
            )

        # 3. Fetch raw data
        fetcher = fetcher_registry.get_or_raise(api_name)
        ctx = FetchContext(
            switch_ip=ip_address,
            switch_hostname=hostname,
            device_type=device_type,
            tenant_group=tenant_group,
            http=http,
            maintenance_id=maintenance_id,
        )
        result = await fetcher.fetch(ctx)
        if not result.success:
            raise RuntimeError(
                f"Fetch failed for {api_name} on "
                f"{hostname}: {result.error}"
            )

        # 4. Parse
        parsed_items = parser.parse(result.raw_output)

        # 5. Save to DB (hash 比對：未變化時回傳 None)
        batch = await typed_repo.save_batch(
            switch_hostname=hostname,
            raw_data=result.raw_output,
            parsed_items=parsed_items,
            maintenance_id=maintenance_id,
        )
        if batch is not None:
            logger.info(
                "Collected %s from %s: %d items (new batch)",
                api_name, hostname, len(parsed_items),
            )
        else:
            logger.debug(
                "Collected %s from %s: unchanged, skipped",
                api_name, hostname,
            )

    # ── Error tracking helpers ───────────────────────────────────

    @staticmethod
    async def _clear_collection_error(
        session: Any,
        maintenance_id: str,
        api_name: str,
        hostname: str,
    ) -> None:
        """成功採集後清除該設備的錯誤紀錄。"""
        await session.execute(
            delete(CollectionError).where(
                CollectionError.maintenance_id == maintenance_id,
                CollectionError.collection_type == api_name,
                CollectionError.switch_hostname == hostname,
            )
        )

    @staticmethod
    async def _upsert_collection_error(
        session: Any,
        maintenance_id: str,
        api_name: str,
        hostname: str,
        error_msg: str,
    ) -> None:
        """採集失敗時 UPSERT 錯誤紀錄。"""
        from datetime import datetime, timezone

        stmt = select(CollectionError).where(
            CollectionError.maintenance_id == maintenance_id,
            CollectionError.collection_type == api_name,
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
                collection_type=api_name,
                switch_hostname=hostname,
                error_message=error_msg,
                occurred_at=datetime.now(timezone.utc),
            ))


# Singleton
_service: ApiCollectionService | None = None


def get_collection_service() -> ApiCollectionService:
    """Get or create ApiCollectionService instance."""
    global _service
    if _service is None:
        _service = ApiCollectionService()
    return _service
