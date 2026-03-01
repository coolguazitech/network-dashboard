"""
SNMP Collection Service.

與 ApiCollectionService 完全相同的介面，用於 SNMP 模式。
ACL 和 Ping 自動 delegate 給 ApiCollectionService（SNMP 無法處理這些）。
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from typing import Any

from pydantic import BaseModel
from sqlalchemy import delete, select

from app.core.config import settings
from app.core.enums import DeviceType
from app.db.base import get_session_context
from app.db.models import CollectionError, MaintenanceDeviceList
from app.repositories.typed_records import get_typed_repo
from app.snmp.collector_base import BaseSnmpCollector
from app.snmp.engine import AsyncSnmpEngine, SnmpEngineConfig
from app.snmp.session_cache import SnmpSessionCache

logger = logging.getLogger(__name__)

# APIs that stay on REST regardless of COLLECTION_MODE
_API_PASSTHROUGH = frozenset({
    "get_static_acl",
    "get_dynamic_acl",
    "gnms_ping",
    "ping_batch",
})


def _build_collector_map() -> dict[str, BaseSnmpCollector]:
    """Build registry of api_name → SNMP collector instances."""
    from app.snmp.collectors.channel_group import ChannelGroupCollector
    from app.snmp.collectors.error_count import ErrorCountCollector
    from app.snmp.collectors.fan import FanCollector
    from app.snmp.collectors.interface_status import InterfaceStatusCollector
    from app.snmp.collectors.mac_table import MacTableCollector
    from app.snmp.collectors.neighbor_cdp import NeighborCdpCollector
    from app.snmp.collectors.neighbor_lldp import NeighborLldpCollector
    from app.snmp.collectors.power import PowerCollector
    from app.snmp.collectors.transceiver import TransceiverCollector
    from app.snmp.collectors.version import VersionCollector

    collectors: list[BaseSnmpCollector] = [
        FanCollector(),
        PowerCollector(),
        VersionCollector(),
        TransceiverCollector(),
        ErrorCountCollector(),
        ChannelGroupCollector(),
        NeighborLldpCollector(),
        NeighborCdpCollector(),
        MacTableCollector(),
        InterfaceStatusCollector(),
    ]
    return {c.api_name: c for c in collectors}


class SnmpCollectionService:
    """
    SNMP collection service — same interface as ApiCollectionService.

    For api_names that have no SNMP collector (ACL, ping),
    delegates to ApiCollectionService.
    """

    def __init__(self) -> None:
        if settings.snmp_mock:
            from app.snmp.mock_engine import MockSnmpEngine
            self._engine: Any = MockSnmpEngine()
            logger.info("SNMP collection using MOCK engine (no real devices)")
        else:
            engine_config = SnmpEngineConfig(
                max_repetitions=settings.snmp_max_repetitions,
                walk_timeout=settings.snmp_walk_timeout,
            )
            self._engine = AsyncSnmpEngine(config=engine_config)
        self._collectors = _build_collector_map()
        self._api_fallback: Any = None  # lazy init

    def _get_api_fallback(self) -> Any:
        """Lazy-init ApiCollectionService to avoid circular imports."""
        if self._api_fallback is None:
            from app.services.data_collection import ApiCollectionService
            self._api_fallback = ApiCollectionService()
        return self._api_fallback

    async def collect(
        self,
        api_name: str,
        source: str,
        maintenance_id: str,
    ) -> dict[str, Any]:
        """
        Same signature and return type as ApiCollectionService.collect().
        """
        # Passthrough to API for non-SNMP indicators
        if api_name in _API_PASSTHROUGH:
            return await self._get_api_fallback().collect(
                api_name=api_name,
                source=source,
                maintenance_id=maintenance_id,
            )

        collector = self._collectors.get(api_name)
        if collector is None:
            logger.warning(
                "No SNMP collector for '%s', falling back to API", api_name,
            )
            return await self._get_api_fallback().collect(
                api_name=api_name,
                source=source,
                maintenance_id=maintenance_id,
            )

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
                    collector=collector,
                    maintenance_id=maintenance_id,
                    results=results,
                )
            except Exception as e:
                if "Deadlock" in str(e) and attempt < max_retries:
                    logger.warning(
                        "Deadlock on SNMP %s, retrying (%d/%d)",
                        api_name, attempt + 1, max_retries,
                    )
                    results["success"] = 0
                    results["failed"] = 0
                    results["errors"] = []
                    await asyncio.sleep(0.3 * (attempt + 1))
                    continue
                raise

        return results  # unreachable

    async def _do_collect(
        self,
        api_name: str,
        collector: BaseSnmpCollector,
        maintenance_id: str,
        results: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute SNMP collection with parallel device fetching."""
        t0 = _time.monotonic()
        sem = asyncio.Semaphore(settings.snmp_concurrency)

        # Fresh session cache per collection cycle
        session_cache = SnmpSessionCache(
            engine=self._engine,
            communities=settings.snmp_community_list,
            port=settings.snmp_port,
            timeout=settings.snmp_timeout,
            retries=settings.snmp_retries,
        )

        # 1. Load target devices
        async with get_session_context() as session:
            stmt = select(MaintenanceDeviceList).where(
                MaintenanceDeviceList.maintenance_id == maintenance_id,
                MaintenanceDeviceList.new_hostname != None,  # noqa: E711
                MaintenanceDeviceList.new_ip_address != None,  # noqa: E711
            )
            result = await session.execute(stmt)
            devices = result.scalars().all()
            results["total"] = len(devices)

        # 2. Collect all devices in parallel
        async def _collect_one(device: MaintenanceDeviceList) -> str:
            async with sem:
                async with get_session_context() as dev_session:
                    typed_repo = get_typed_repo(api_name, dev_session)
                    hostname = device.new_hostname
                    ip_address = device.new_ip_address
                    try:
                        await self._collect_for_target(
                            hostname=hostname,
                            ip_address=ip_address,
                            vendor=device.new_vendor,
                            api_name=api_name,
                            maintenance_id=maintenance_id,
                            collector=collector,
                            session_cache=session_cache,
                            typed_repo=typed_repo,
                        )
                        await _clear_collection_error(
                            dev_session, maintenance_id,
                            api_name, hostname,
                        )
                        return "ok"
                    except Exception as e:
                        logger.error(
                            "SNMP %s failed for %s: %s",
                            api_name, hostname, e,
                        )
                        try:
                            await _upsert_collection_error(
                                dev_session, maintenance_id,
                                api_name, hostname, str(e),
                            )
                        except Exception:
                            logger.error(
                                "Failed to record CollectionError for %s",
                                hostname,
                            )
                        from app.services.system_log import (
                            format_error_detail,
                            write_log,
                        )
                        await write_log(
                            level="WARNING",
                            source="service",
                            summary=(
                                f"SNMP 採集失敗: {hostname} ({api_name})"
                            ),
                            detail=format_error_detail(
                                exc=e,
                                context={
                                    "設備": hostname,
                                    "API": api_name,
                                    "歲修": maintenance_id,
                                    "模式": "SNMP",
                                    "廠商": device.new_vendor or "unknown",
                                },
                            ),
                            module="snmp_collection",
                            maintenance_id=maintenance_id,
                        )
                        # Save empty batch so UI shows "0 items" status
                        try:
                            await typed_repo.save_batch(
                                switch_hostname=hostname,
                                raw_data=f"[SNMP_ERROR] {e}",
                                parsed_items=[],
                                maintenance_id=maintenance_id,
                            )
                        except Exception:
                            logger.error(
                                "Failed to save null batch for %s/%s",
                                api_name, hostname,
                            )
                        return "fail"

        outcomes = await asyncio.gather(
            *[_collect_one(d) for d in devices],
        )
        results["success"] = outcomes.count("ok")
        results["failed"] = outcomes.count("fail")

        elapsed = _time.monotonic() - t0
        logger.info(
            "SNMP %s for %s: %d/%d ok, %.2fs",
            api_name, maintenance_id,
            results["success"], results["total"], elapsed,
        )
        return results

    async def _collect_for_target(
        self,
        *,
        hostname: str,
        ip_address: str,
        vendor: str | None,
        api_name: str,
        maintenance_id: str,
        collector: BaseSnmpCollector,
        session_cache: SnmpSessionCache,
        typed_repo: Any,
    ) -> None:
        """Collect from a single device via SNMP and save to DB."""
        device_type = DeviceType(vendor or "HPE")

        # 1. Get SNMP target (community auto-detection)
        target = await session_cache.get_target(ip_address)

        # 2. SNMP collect with retry
        raw_text, parsed_items = await collector.collect_with_retry(
            target=target,
            device_type=device_type,
            session_cache=session_cache,
            engine=self._engine,
            max_retries=settings.snmp_collector_retries,
        )

        # 3. Save to DB (same as ApiCollectionService)
        batch = await typed_repo.save_batch(
            switch_hostname=hostname,
            raw_data=raw_text,
            parsed_items=parsed_items,
            maintenance_id=maintenance_id,
        )
        if batch is not None:
            logger.info(
                "SNMP collected %s from %s: %d items (new batch)",
                api_name, hostname, len(parsed_items),
            )
        else:
            logger.debug(
                "SNMP collected %s from %s: unchanged, skipped",
                api_name, hostname,
            )


# ── Error tracking helpers (same as ApiCollectionService) ─────────


async def _clear_collection_error(
    session: Any,
    maintenance_id: str,
    api_name: str,
    hostname: str,
) -> None:
    """Clear error record after successful collection."""
    await session.execute(
        delete(CollectionError).where(
            CollectionError.maintenance_id == maintenance_id,
            CollectionError.collection_type == api_name,
            CollectionError.switch_hostname == hostname,
        )
    )


async def _upsert_collection_error(
    session: Any,
    maintenance_id: str,
    api_name: str,
    hostname: str,
    error_msg: str,
) -> None:
    """Upsert error record on collection failure."""
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
_service: SnmpCollectionService | None = None


def get_snmp_collection_service() -> SnmpCollectionService:
    """Get or create SnmpCollectionService instance."""
    global _service
    if _service is None:
        _service = SnmpCollectionService()
    return _service
