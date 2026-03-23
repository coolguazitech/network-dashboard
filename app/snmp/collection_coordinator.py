"""
SNMP Collection Coordinator — Device-Centric Collection Rounds.

取代舊的 job-centric 架構（每個 collector type 各自遍歷所有設備），
改為 device-centric：遍歷設備，對每台設備執行該輪次所有 collectors。

優勢：
1. 每台設備只探測一次 community（不論跑幾個 collector）
2. 不通設備一次判定，整台跳過（不會每個 collector 各等一次 timeout）
3. 不依賴 ping 結果過濾（移除 chicken-and-egg 問題）
4. 可預測的完成時間（設備數 / 併發數 × 每台耗時）
5. DB 連線更少（每台設備一次 session 寫入所有 collector 結果）
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from app.core.config import settings
from app.core.enums import DeviceType
from app.db.base import get_session_context
from app.db.models import CollectionError, MaintenanceDeviceList
from app.repositories.typed_records import get_typed_repo
from app.snmp.collector_base import BaseSnmpCollector
from app.snmp.engine import SnmpTimeoutError
from app.snmp.session_cache import SnmpSessionCache

logger = logging.getLogger(__name__)


@dataclass
class DeviceResult:
    """Collection result for a single device."""

    hostname: str
    ip: str
    status: str  # "ok", "unreachable", "partial"
    collector_results: dict[str, str] = field(default_factory=dict)
    # collector_results: {api_name: "ok" | "timeout" | "error"}


@dataclass
class RoundResult:
    """Aggregate result for one collection round."""

    round_name: str
    total_devices: int = 0
    ok: int = 0
    unreachable: int = 0
    partial: int = 0
    elapsed: float = 0.0
    per_collector: dict[str, dict[str, int]] = field(default_factory=dict)
    # per_collector: {api_name: {"ok": N, "timeout": N, "error": N}}


class CollectionCoordinator:
    """
    Device-centric SNMP collection coordinator.

    Instead of N jobs each iterating all devices, iterates devices once
    and runs all applicable collectors per device.
    """

    def __init__(
        self,
        engine: Any,
        collectors: dict[str, BaseSnmpCollector],
        semaphore: asyncio.Semaphore,
    ) -> None:
        self._engine = engine
        self._collectors = collectors
        self._semaphore = semaphore

    async def run_round(
        self,
        round_name: str,
        collector_names: list[str],
        maintenance_id: str,
    ) -> RoundResult:
        """
        Execute a collection round for one maintenance.

        Args:
            round_name: Human-readable name (e.g., "fast_round", "full_round")
            collector_names: List of api_names to run this round
            maintenance_id: Target maintenance ID

        Returns:
            RoundResult with per-device, per-collector breakdown
        """
        t0 = _time.monotonic()

        # Resolve collectors for this round
        collectors = []
        for name in collector_names:
            c = self._collectors.get(name)
            if c is None:
                logger.warning("Unknown collector '%s', skipping", name)
                continue
            collectors.append(c)

        if not collectors:
            logger.warning("No valid collectors for round '%s'", round_name)
            return RoundResult(round_name=round_name)

        # Load ALL devices — do NOT filter by is_reachable.
        # Let session_cache negative cache handle unreachable devices.
        # This eliminates the chicken-and-egg problem where first ping
        # hasn't run yet so is_reachable is NULL and SNMP skips everything.
        async with get_session_context() as session:
            from sqlalchemy import select

            stmt = select(MaintenanceDeviceList).where(
                MaintenanceDeviceList.maintenance_id == maintenance_id,
                MaintenanceDeviceList.new_hostname != None,  # noqa: E711
                MaintenanceDeviceList.new_ip_address != None,  # noqa: E711
            )
            result = await session.execute(stmt)
            devices = result.scalars().all()
            # Snapshot device info while session is open
            device_infos = [
                {
                    "hostname": d.new_hostname,
                    "ip": d.new_ip_address,
                    "vendor": d.new_vendor,
                }
                for d in devices
            ]

        if not device_infos:
            logger.info(
                "Round '%s' for %s: no devices found",
                round_name, maintenance_id,
            )
            return RoundResult(round_name=round_name)

        # Fresh session cache per round (instance-level caches reset,
        # class-level community/negative caches persist across rounds)
        session_cache = SnmpSessionCache(
            engine=self._engine,
            communities=settings.snmp_community_list,
            port=settings.snmp_port,
            timeout=settings.snmp_timeout,
            retries=settings.snmp_retries,
        )

        # Collect all devices concurrently, bounded by global semaphore
        device_results = await asyncio.gather(
            *[
                self._collect_device(
                    device_info=dev,
                    collectors=collectors,
                    session_cache=session_cache,
                    maintenance_id=maintenance_id,
                )
                for dev in device_infos
            ],
            return_exceptions=True,
        )

        # Aggregate results
        round_result = RoundResult(
            round_name=round_name,
            total_devices=len(device_infos),
        )
        for api_name in collector_names:
            round_result.per_collector[api_name] = {
                "ok": 0, "timeout": 0, "error": 0,
            }

        for dr in device_results:
            if isinstance(dr, Exception):
                logger.error(
                    "Unexpected error in round '%s': %s", round_name, dr,
                )
                round_result.partial += 1
                continue

            if dr.status == "ok":
                round_result.ok += 1
            elif dr.status == "unreachable":
                round_result.unreachable += 1
            else:
                round_result.partial += 1

            for api_name, status in dr.collector_results.items():
                if api_name in round_result.per_collector:
                    bucket = "ok" if status == "ok" else (
                        "timeout" if status in ("timeout", "unreachable") else "error"
                    )
                    round_result.per_collector[api_name][bucket] += 1

        round_result.elapsed = _time.monotonic() - t0

        logger.info(
            "Round '%s' for %s: %d devices "
            "(%d ok, %d unreachable, %d partial) in %.1fs",
            round_name, maintenance_id,
            round_result.total_devices,
            round_result.ok, round_result.unreachable,
            round_result.partial, round_result.elapsed,
        )

        return round_result

    # Per-device hard timeout inside semaphore.
    # Even if individual PDUs timeout properly, a device with 10 collectors
    # could block a slot for 10 × 8s = 80s. This cap ensures the slot is
    # freed in bounded time regardless of what happens inside.
    _DEVICE_HARD_TIMEOUT: float = 90.0  # seconds; fast_round(2)≈16s, full_round(8)≈64s

    async def _collect_device(
        self,
        device_info: dict[str, str | None],
        collectors: list[BaseSnmpCollector],
        session_cache: SnmpSessionCache,
        maintenance_id: str,
    ) -> DeviceResult:
        """
        Collect all specified indicators from a single device.

        Flow:
        1. Acquire semaphore (bounded concurrency)
        2. Probe community ONCE via session_cache.get_target()
        3. Run each collector sequentially (sharing the same target)
        4. Write all results to DB in a single session

        Hard timeout: entire SNMP phase (probe + all collectors) is wrapped
        in asyncio.wait_for() so one slow device can never block a semaphore
        slot indefinitely.
        """
        hostname = device_info["hostname"] or ""
        ip = device_info["ip"] or ""
        vendor = device_info["vendor"]
        device_type = DeviceType(vendor or "HPE")

        collector_outcomes: list[tuple[str, str, str | None, list[BaseModel]]] = []
        device_unreachable = False
        all_ok = True

        async with self._semaphore:
            try:
                collector_outcomes, device_unreachable, all_ok = (
                    await asyncio.wait_for(
                        self._snmp_phase(
                            ip=ip,
                            hostname=hostname,
                            device_type=device_type,
                            collectors=collectors,
                            session_cache=session_cache,
                        ),
                        timeout=self._DEVICE_HARD_TIMEOUT,
                    )
                )
            except asyncio.TimeoutError:
                logger.warning(
                    "Device %s (%s) exceeded hard timeout (%.0fs), "
                    "marking all collectors as timeout",
                    hostname, ip, self._DEVICE_HARD_TIMEOUT,
                )
                device_unreachable = True
                all_ok = False
                collector_outcomes = [
                    (c.api_name, "timeout",
                     f"Device hard timeout ({self._DEVICE_HARD_TIMEOUT:.0f}s): {ip}",
                     [])
                    for c in collectors
                ]

        # Phase 3: DB write — OUTSIDE semaphore to free slot faster
        await self._save_device_results(
            hostname=hostname,
            maintenance_id=maintenance_id,
            collector_outcomes=collector_outcomes,
        )

        if device_unreachable:
            return DeviceResult(
                hostname=hostname,
                ip=ip,
                status="unreachable",
                collector_results={
                    c.api_name: "unreachable" for c in collectors
                },
            )

        status = "ok" if all_ok else "partial"
        return DeviceResult(
            hostname=hostname,
            ip=ip,
            status=status,
            collector_results={
                api_name: outcome
                for api_name, outcome, _, _ in collector_outcomes
            },
        )

    async def _snmp_phase(
        self,
        ip: str,
        hostname: str,
        device_type: DeviceType,
        collectors: list[BaseSnmpCollector],
        session_cache: SnmpSessionCache,
    ) -> tuple[list[tuple[str, str, str | None, list[BaseModel]]], bool, bool]:
        """
        SNMP probe + all collectors for one device.

        Separated from _collect_device so it can be wrapped in wait_for().
        Returns: (collector_outcomes, device_unreachable, all_ok)
        """
        collector_outcomes: list[tuple[str, str, str | None, list[BaseModel]]] = []

        # Phase 1: Community probe
        try:
            target = await session_cache.get_target(ip)
        except SnmpTimeoutError:
            return (
                [(c.api_name, "unreachable", f"SNMP unreachable: {ip}", [])
                 for c in collectors],
                True,   # device_unreachable
                False,  # all_ok
            )

        # Phase 2: Run each collector sequentially (sharing target)
        all_ok = True
        for collector in collectors:
            try:
                raw_text, parsed_items = await collector.collect_with_retry(
                    target=target,
                    device_type=device_type,
                    session_cache=session_cache,
                    engine=self._engine,
                    max_retries=settings.snmp_collector_retries,
                )
                collector_outcomes.append(
                    (collector.api_name, "ok", None, parsed_items),
                )
            except SnmpTimeoutError as e:
                collector_outcomes.append(
                    (collector.api_name, "timeout", str(e), []),
                )
                all_ok = False
            except Exception as e:
                logger.error(
                    "Collector %s failed for %s: %s",
                    collector.api_name, hostname, e,
                )
                collector_outcomes.append(
                    (collector.api_name, "error", str(e), []),
                )
                all_ok = False

        return collector_outcomes, False, all_ok

    async def _save_device_results(
        self,
        hostname: str,
        maintenance_id: str,
        collector_outcomes: list[tuple[str, str, str | None, list[BaseModel]]],
    ) -> None:
        """
        Save all collector results for one device in a single DB session.

        Args:
            collector_outcomes: List of (api_name, status, error_msg, parsed_items)
        """
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                async with get_session_context() as session:
                    for api_name, status, error_msg, parsed_items in collector_outcomes:
                        typed_repo = get_typed_repo(api_name, session)

                        if status == "ok":
                            await typed_repo.save_batch(
                                switch_hostname=hostname,
                                raw_data=None,
                                parsed_items=parsed_items,
                                maintenance_id=maintenance_id,
                            )
                            await _clear_collection_error(
                                session, maintenance_id, api_name, hostname,
                            )
                        else:
                            # Save empty batch so UI shows status
                            await typed_repo.save_batch(
                                switch_hostname=hostname,
                                raw_data=f"[SNMP_{status.upper()}] {error_msg}",
                                parsed_items=[],
                                maintenance_id=maintenance_id,
                            )
                            await _upsert_collection_error(
                                session, maintenance_id,
                                api_name, hostname, error_msg or status,
                            )
                return  # success
            except Exception as e:
                if "Deadlock" in str(e) and attempt < max_retries:
                    logger.warning(
                        "Deadlock saving results for %s, retry %d/%d",
                        hostname, attempt + 1, max_retries,
                    )
                    await asyncio.sleep(0.3 * (attempt + 1))
                    continue
                logger.error(
                    "Failed to save results for %s: %s", hostname, e,
                )
                # Log to system_log for visibility
                try:
                    from app.services.system_log import format_error_detail, write_log
                    await write_log(
                        level="WARNING",
                        source="service",
                        summary=f"DB write failed: {hostname}",
                        detail=format_error_detail(
                            exc=e,
                            context={
                                "device": hostname,
                                "maintenance": maintenance_id,
                            },
                        ),
                        module="collection_coordinator",
                        maintenance_id=maintenance_id,
                    )
                except Exception:
                    pass
                return


# ── Error tracking helpers ─────────────────────────────────────


async def _clear_collection_error(
    session: Any,
    maintenance_id: str,
    api_name: str,
    hostname: str,
) -> None:
    """Clear error record after successful collection."""
    from sqlalchemy import delete

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

    from sqlalchemy import select

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
