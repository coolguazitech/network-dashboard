"""
Scheduler Service.

Architecture (v2.20.0 — continuous collection loop):
  - collection_loop (continuous): 完成即開始下一輪，無固定間隔
      SNMP round (ALL collectors) → API passthrough (ACL) → client_collection → cooldown → repeat
  - device_ping (15s): batch ICMP via GNMSPING API
  - client_ping (15s): batch ICMP for client IPs
  - retention (30min): cleanup old data

採集週期純粹取決於設備數量：5 台設備 ≈ 30s/輪（近即時），200 台 ≈ 5min/輪。
每輪結束後立即觸發 client_collection，確保資料一致性。
"""
from __future__ import annotations

import asyncio
import logging
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Scheduler for collection and periodic jobs.

    採集使用連續迴圈（完成即開始下一輪），Ping / Retention 使用 APScheduler 定時。
    """

    def __init__(self) -> None:
        """Initialize scheduler."""
        self.scheduler = AsyncIOScheduler(
            job_defaults={
                "max_instances": 1,
                "coalesce": True,
                "misfire_grace_time": 30,
            },
        )
        # Switch collection service based on COLLECTION_MODE
        from app.core.config import settings
        if settings.collection_mode == "snmp":
            from app.snmp.collection_service import SnmpCollectionService
            self.collection_service = SnmpCollectionService()  # type: ignore[assignment]
            logger.info("Using SNMP collection mode (device-centric rounds)")
        else:
            from app.services.data_collection import ApiCollectionService
            self.collection_service = ApiCollectionService()
            logger.info("Using API collection mode")
        self._jobs: dict[str, str] = {}  # job_name -> job_id
        self._loop_task: asyncio.Task | None = None  # continuous collection loop
        self._loop_stop = asyncio.Event()  # signal to stop the loop

    # ── Continuous Collection Loop ──────────────────────────────

    def start_collection_loop(
        self,
        snmp_collectors: list[str],
        api_collectors: list[dict[str, str]],
        min_round_gap: int = 10,
    ) -> None:
        """
        啟動連續採集迴圈。

        每輪依序執行：
        1. SNMP round（所有 SNMP collectors，by 設備）
        2. API passthrough（ACL 等 REST collectors）
        3. client_collection（組裝 ClientRecord + sync cases）
        4. cooldown（min_round_gap 秒）

        完成即開始下一輪，不等固定間隔。

        Args:
            snmp_collectors: List of SNMP collector api_names
            api_collectors: List of {"name": ..., "source": ...} dicts
            min_round_gap: Minimum seconds between rounds
        """
        if self._loop_task and not self._loop_task.done():
            logger.warning("Collection loop already running, skipping")
            return

        self._loop_stop.clear()
        self._loop_task = asyncio.create_task(
            self._collection_loop(
                snmp_collectors=snmp_collectors,
                api_collectors=api_collectors,
                min_round_gap=min_round_gap,
            ),
            name="collection_loop",
        )

        # Auto-restart on unexpected crash (DB blip, unhandled error, etc.)
        def _on_loop_done(task: asyncio.Task) -> None:
            if self._loop_stop.is_set():
                return  # intentional shutdown, don't restart
            exc = task.exception() if not task.cancelled() else None
            if exc is not None:
                logger.error(
                    "Collection loop crashed (%s), restarting in 10s...", exc,
                )
            elif task.cancelled():
                logger.warning("Collection loop was cancelled unexpectedly, restarting in 10s...")
            else:
                return  # normal exit (shouldn't happen, but harmless)

            async def _delayed_restart() -> None:
                await asyncio.sleep(10)
                if not self._loop_stop.is_set():
                    self.start_collection_loop(
                        snmp_collectors=snmp_collectors,
                        api_collectors=api_collectors,
                        min_round_gap=min_round_gap,
                    )

            asyncio.ensure_future(_delayed_restart())

        self._loop_task.add_done_callback(_on_loop_done)

        logger.info(
            "Started continuous collection loop: "
            "%d SNMP collectors + %d API collectors, min_gap=%ds",
            len(snmp_collectors), len(api_collectors), min_round_gap,
        )

    async def _collection_loop(
        self,
        snmp_collectors: list[str],
        api_collectors: list[dict[str, str]],
        min_round_gap: int,
    ) -> None:
        """
        連續採集迴圈主體。

        每輪自動計時，完成後等待 min_round_gap 秒再開始下一輪。
        無活躍歲修時，每 30 秒 check 一次。
        """
        round_number = 0
        # 首輪延遲 5 秒，讓其他服務（DB、Ping）先就位
        await asyncio.sleep(5)

        while not self._loop_stop.is_set():
            round_number += 1
            t0 = _time.monotonic()

            try:
                maintenance_ids = await self._get_active_maintenance_ids()
                if not maintenance_ids:
                    logger.debug("No active maintenances, waiting 30s")
                    try:
                        await asyncio.wait_for(
                            self._loop_stop.wait(), timeout=30,
                        )
                    except asyncio.TimeoutError:
                        pass
                    continue

                logger.info(
                    "=== Collection round #%d start (%d maintenances) ===",
                    round_number, len(maintenance_ids),
                )

                # ── Phase 1: SNMP round (all collectors, device-centric) ──
                if snmp_collectors:
                    await self._run_snmp_phase(
                        snmp_collectors, maintenance_ids, round_number,
                    )

                # ── Phase 2: API passthrough (ACL etc.) ──
                if api_collectors:
                    await self._run_api_phase(
                        api_collectors, maintenance_ids,
                    )

                # ── Phase 3: Client collection (組裝 + case sync) ──
                await self._run_client_collection()

                elapsed = _time.monotonic() - t0
                logger.info(
                    "=== Collection round #%d done: %.1fs ===",
                    round_number, elapsed,
                )

            except Exception as e:
                elapsed = _time.monotonic() - t0
                logger.error(
                    "Collection round #%d failed after %.1fs: %s",
                    round_number, elapsed, e,
                )
                try:
                    from app.services.system_log import write_log, format_error_detail
                    await write_log(
                        level="ERROR",
                        source="scheduler",
                        summary=f"採集輪次 #{round_number} 失敗 ({type(e).__name__})",
                        detail=format_error_detail(
                            exc=e,
                            context={"輪次": round_number},
                        ),
                        module="collection_loop",
                    )
                except Exception:
                    logger.error(
                        "Failed to write system log for round #%d failure",
                        round_number,
                    )

            # ── Cooldown ──
            try:
                await asyncio.wait_for(
                    self._loop_stop.wait(), timeout=min_round_gap,
                )
                break  # stop signal received
            except asyncio.TimeoutError:
                pass  # normal cooldown finished, continue loop

        logger.info("Collection loop stopped after %d rounds", round_number)

    async def _run_snmp_phase(
        self,
        collector_names: list[str],
        maintenance_ids: list[str],
        round_number: int,
    ) -> None:
        """Phase 1: SNMP device-centric collection."""
        svc = self.collection_service
        for mid in maintenance_ids:
            try:
                if hasattr(svc, "collect_round"):
                    result = await svc.collect_round(
                        round_name=f"round_{round_number}",
                        collector_names=collector_names,
                        maintenance_id=mid,
                    )
                    logger.info(
                        "SNMP round #%d for %s: %d/%d ok, %d unreachable, %.1fs",
                        round_number, mid,
                        result["ok"], result["total"],
                        result["unreachable"], result["elapsed"],
                    )
                else:
                    # API mode fallback: run each collector separately
                    for api_name in collector_names:
                        try:
                            result = await svc.collect(
                                api_name=api_name,
                                source="",
                                maintenance_id=mid,
                            )
                            logger.info(
                                "%s for %s: %d/%d successful",
                                api_name, mid,
                                result["success"], result["total"],
                            )
                        except Exception as e:
                            logger.error(
                                "%s failed for %s: %s",
                                api_name, mid, e,
                            )
            except Exception as e:
                logger.error(
                    "SNMP phase failed for %s: %s", mid, e,
                )
                try:
                    from app.services.system_log import write_log, format_error_detail
                    await write_log(
                        level="ERROR",
                        source="scheduler",
                        summary=f"SNMP 採集失敗 ({type(e).__name__}): {mid}",
                        detail=format_error_detail(
                            exc=e, context={"歲修": mid},
                        ),
                        module="collection_loop",
                        maintenance_id=mid,
                    )
                except Exception:
                    logger.error("Failed to write system log for SNMP phase %s", mid)

    async def _run_api_phase(
        self,
        api_configs: list[dict[str, str]],
        maintenance_ids: list[str],
    ) -> None:
        """Phase 2: API passthrough collection (ACL etc.)."""
        from app.services.data_collection import get_collection_service
        api_svc = get_collection_service()

        for mid in maintenance_ids:
            for cfg in api_configs:
                api_name = cfg["name"]
                source = cfg.get("source", "")
                try:
                    result = await api_svc.collect(
                        api_name=api_name,
                        source=source,
                        maintenance_id=mid,
                    )
                    logger.info(
                        "API %s for %s: %d/%d successful",
                        api_name, mid,
                        result["success"], result["total"],
                    )
                except Exception as e:
                    logger.error(
                        "API %s failed for %s: %s",
                        api_name, mid, e,
                    )

    # ── Legacy per-job collection (API mode fallback) ──────────────

    def add_collection_job(
        self,
        job_name: str,
        interval_seconds: int,
        source: str = "",
        initial_delay: float = 0,
    ) -> str:
        """
        Add a scheduled collection job (legacy per-api_name interface).

        Used when COLLECTION_MODE=api (non-SNMP).
        """
        job_id = f"collect_{job_name}"

        if job_name in self._jobs:
            self.remove_job(job_name)

        trigger_kwargs: dict[str, Any] = {"seconds": interval_seconds, "jitter": 15}
        if initial_delay > 0:
            trigger_kwargs["start_date"] = (
                datetime.now(timezone.utc) + timedelta(seconds=initial_delay)
            )

        job = self.scheduler.add_job(
            self._run_collection,
            trigger=IntervalTrigger(**trigger_kwargs),
            id=job_id,
            kwargs={
                "job_name": job_name,
                "source": source,
            },
            replace_existing=True,
        )

        self._jobs[job_name] = job.id
        logger.info(
            "Added collection job '%s' (source=%s) every %ds",
            job_name, source, interval_seconds,
        )
        return job.id

    def remove_job(self, job_name: str) -> bool:
        """Remove a scheduled job."""
        job_id = self._jobs.get(job_name)
        if job_id:
            self.scheduler.remove_job(job_id)
            del self._jobs[job_name]
            logger.info("Removed collection job '%s'", job_name)
            return True
        return False

    def get_jobs(self) -> list[dict[str, Any]]:
        """Get list of all scheduled jobs."""
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time),
                "trigger": str(job.trigger),
            }
            for job in self.scheduler.get_jobs()
        ]

    # ── Internal ─────────────────────────────────────────────────

    async def _get_active_maintenance_ids(self) -> list[str]:
        """
        取得所有活躍的歲修 ID。

        自動停用累計活躍時間超過 max_collection_days 的歲修。
        """
        from sqlalchemy import select

        from app.core.config import settings
        from app.db.base import get_session_context
        from app.db.models import MaintenanceConfig

        max_seconds = settings.max_collection_days * 86400

        async with get_session_context() as session:
            active_stmt = select(MaintenanceConfig).where(
                MaintenanceConfig.is_active == True,  # noqa: E712
            )
            active_result = await session.execute(active_stmt)
            active_configs = active_result.scalars().all()

            from app.services.maintenance_time import get_active_seconds

            expired: list[MaintenanceConfig] = []

            for config in active_configs:
                total = await get_active_seconds(
                    config.maintenance_id, session
                )

                if total >= max_seconds:
                    config.is_active = False
                    config.active_seconds_accumulated = int(total)
                    config.last_activated_at = None
                    expired.append(config)
                    logger.warning(
                        "Auto-stopping maintenance %s: accumulated %.1f hours "
                        "(limit: %d days)",
                        config.maintenance_id,
                        total / 3600,
                        settings.max_collection_days,
                    )

            if expired:
                await session.commit()
                try:
                    from app.services.system_log import write_log
                    for config in expired:
                        await write_log(
                            level="WARNING",
                            source="scheduler",
                            summary=(
                                f"歲修 {config.maintenance_id} 已自動停止採集"
                                f"（累計活躍時間超過 {settings.max_collection_days} 天上限）"
                            ),
                            module="scheduler",
                            maintenance_id=config.maintenance_id,
                        )
                except Exception:
                    logger.error("Failed to write system log for expired maintenances")

            expired_ids = {c.maintenance_id for c in expired}
            maintenance_ids = [
                c.maintenance_id for c in active_configs
                if c.maintenance_id not in expired_ids
            ]

        return maintenance_ids

    async def _run_collection(
        self,
        job_name: str,
        source: str = "",
    ) -> None:
        """
        Run a collection job for ALL active maintenances (legacy interface).
        """
        t0 = _time.monotonic()
        logger.info("Running scheduled collection for '%s'", job_name)

        maintenance_ids = await self._get_active_maintenance_ids()

        if not maintenance_ids:
            logger.debug("No active maintenances found, skipping collection")
            return

        try:
            svc = self.collection_service
            for mid in maintenance_ids:
                try:
                    result = await svc.collect(
                        api_name=job_name,
                        source=source,
                        maintenance_id=mid,
                    )
                    logger.info(
                        "%s for %s: %d/%d successful",
                        job_name, mid,
                        result["success"], result["total"],
                    )
                except Exception as e:
                    logger.error(
                        "%s failed for %s: %s",
                        job_name, mid, e,
                    )
                    try:
                        from app.services.system_log import write_log, format_error_detail
                        await write_log(
                            level="ERROR",
                            source="scheduler",
                            summary=f"排程任務失敗 ({type(e).__name__}): {job_name} ({mid})",
                            detail=format_error_detail(
                                exc=e,
                                context={"API": job_name, "歲修": mid},
                            ),
                            module=job_name,
                            maintenance_id=mid,
                        )
                    except Exception:
                        logger.error("Failed to write system log for %s/%s", job_name, mid)

        except Exception as e:
            logger.error(
                "Collection failed for '%s': %s",
                job_name, e,
            )
            try:
                from app.services.system_log import write_log, format_error_detail
                await write_log(
                    level="ERROR",
                    source="scheduler",
                    summary=f"排程任務整體失敗 ({type(e).__name__}): {job_name}",
                    detail=format_error_detail(
                        exc=e,
                        context={"任務": job_name},
                    ),
                    module=job_name,
                )
            except Exception:
                logger.error("Failed to write system log for %s", job_name)
        finally:
            elapsed = _time.monotonic() - t0
            logger.info(
                "'%s' cycle done: %d maintenances, %.2fs",
                job_name,
                len(maintenance_ids),
                elapsed,
            )

    # ── Client Collection ─────────────────────────────────────

    def add_client_collection_job(self, interval_seconds: int = 600) -> str:
        """
        Add a scheduled client collection job.

        This job runs periodically and for each active maintenance:
        1. Collects client data (MAC/InterfaceStatus/ACL/Ping)
        2. Syncs cases (creates missing Case rows for new MACs)
        3. Updates Case.last_ping_reachable from latest ClientRecord
        4. Auto-reopens resolved cases with ping failure
        """
        job_id = "client_collection"

        self.scheduler.add_job(
            self._run_client_collection,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            replace_existing=True,
        )
        logger.info(
            "Added client collection job every %ds", interval_seconds,
        )
        return job_id

    async def _run_client_collection(self) -> None:
        """Run client collection for ALL active maintenances."""
        t0 = _time.monotonic()
        logger.info("Running scheduled client collection")

        maintenance_ids = await self._get_active_maintenance_ids()

        if not maintenance_ids:
            logger.debug("No active maintenances, skipping client collection")
            return

        from app.services.client_collection_service import get_client_collection_service
        from app.services.case_service import CaseService
        from app.db.base import get_session_context

        client_svc = get_client_collection_service()

        for mid in maintenance_ids:
            try:
                result = await client_svc.collect_client_data(
                    maintenance_id=mid,
                )
                logger.info(
                    "Client collection for %s: %d/%d switches, %d records",
                    mid,
                    result["success"], result["total"],
                    result["client_records_count"],
                )

                # Sync cases + update ping + auto-resolve + change flags
                import asyncio as _asyncio
                from sqlalchemy.exc import OperationalError as _OpErr

                max_retries = 3
                for attempt in range(1, max_retries + 1):
                    try:
                        async with get_session_context() as session:
                            case_svc = CaseService()
                            await case_svc.sync_cases(mid, session)
                            await case_svc.update_ping_status(mid, session)
                            await case_svc.auto_reopen_unreachable(mid, session)
                            await case_svc.auto_resolve_reachable(mid, session)
                            await case_svc.update_change_flags(mid, session)
                        break
                    except _OpErr as oe:
                        if "1213" in str(oe) and attempt < max_retries:
                            logger.warning(
                                "client_collection %s: deadlock on attempt %d/%d, retrying...",
                                mid, attempt, max_retries,
                            )
                            await _asyncio.sleep(0.3 * attempt)
                        else:
                            raise

            except Exception as e:
                logger.error(
                    "Client collection failed for %s: %s", mid, e,
                )
                try:
                    from app.services.system_log import write_log, format_error_detail
                    await write_log(
                        level="ERROR",
                        source="scheduler",
                        summary=f"客戶端採集失敗 ({type(e).__name__}): {mid}",
                        detail=format_error_detail(
                            exc=e,
                            context={"歲修": mid},
                        ),
                        module="client_collection",
                        maintenance_id=mid,
                    )
                except Exception:
                    logger.error("Failed to write system log for client collection %s", mid)

        elapsed = _time.monotonic() - t0
        logger.info(
            "Client collection cycle done: %d maintenances, %.2fs",
            len(maintenance_ids), elapsed,
        )

    # ── Device Ping ─────────────────────────────────────────────

    def add_device_ping_job(self, interval_seconds: int = 30) -> str:
        """設備 IP Ping 獨立排程。"""
        job_id = "device_ping"
        self.scheduler.add_job(
            self._run_device_ping,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            replace_existing=True,
        )
        logger.info("Added device ping job every %ds", interval_seconds)
        return job_id

    async def _run_device_ping(self) -> None:
        """
        設備 Ping：按 tenant_group 分組 batch-ping，存入 PingRecordRepo。
        """
        t0 = _time.monotonic()
        logger.info("Running device ping")

        maintenance_ids = await self._get_active_maintenance_ids()
        if not maintenance_ids:
            return

        from app.core.config import settings
        from app.core.enums import TenantGroup
        from app.db.base import get_session_context
        from app.db.models import MaintenanceDeviceList
        from app.repositories.typed_records import get_typed_repo

        import httpx
        from sqlalchemy import select

        ping_cfg = settings.gnmsping
        if not ping_cfg.base_urls:
            logger.warning("No GNMSPING base_urls configured, skipping device ping")
            return

        async with httpx.AsyncClient(timeout=ping_cfg.timeout, verify=False) as http:
            for mid in maintenance_ids:
                try:
                    async with get_session_context() as session:
                        dev_stmt = select(MaintenanceDeviceList).where(
                            MaintenanceDeviceList.maintenance_id == mid,
                        )
                        dev_result = await session.execute(dev_stmt)
                        devices = dev_result.scalars().all()

                        # 新舊設備完全獨立：同 IP 不同 hostname 各自存一筆 ping_record
                        # ip_to_hostnames: 用於 ping API 呼叫（IP 不重複）
                        # hostname_map: IP → list[hostname]，用於存多筆 ping_record
                        groups: dict[TenantGroup, dict[str, str]] = {}
                        hostname_map: dict[str, set[tuple[str, str]]] = {}  # ip → {(hostname, tg)}
                        for d in devices:
                            tg = d.tenant_group or TenantGroup.F18
                            ip_map = groups.setdefault(tg, {})
                            if d.new_hostname and d.new_ip_address:
                                ip_map.setdefault(d.new_ip_address, d.new_hostname)
                                hostname_map.setdefault(d.new_ip_address, set()).add(
                                    (d.new_hostname, tg.value))
                            if d.old_hostname and d.old_ip_address:
                                ip_map.setdefault(d.old_ip_address, d.old_hostname)
                                hostname_map.setdefault(d.old_ip_address, set()).add(
                                    (d.old_hostname, tg.value))

                        if not groups:
                            continue

                        ip_to_dev_side: dict[str, list[tuple]] = {}
                        for d in devices:
                            if d.new_ip_address:
                                ip_to_dev_side.setdefault(d.new_ip_address, []).append((d, "new"))
                            if d.old_ip_address:
                                ip_to_dev_side.setdefault(d.old_ip_address, []).append((d, "old"))

                        CHUNK_SIZE = 500

                        for tg, device_ip_map in groups.items():
                            if not device_ip_map:
                                continue

                            base_url = (
                                ping_cfg.base_urls.get(tg.value)
                                or ping_cfg.base_urls.get(tg.value.lower())
                            )
                            if not base_url:
                                continue

                            url = base_url.rstrip("/") + ping_cfg.endpoint
                            all_ips = sorted(device_ip_map)
                            all_parsed_items = []

                            for chunk_start in range(0, len(all_ips), CHUNK_SIZE):
                                chunk_ips = all_ips[chunk_start:chunk_start + CHUNK_SIZE]
                                try:
                                    resp = await http.post(
                                        url,
                                        json={
                                            "app_name": "network-change-orchestrator",
                                            "token": ping_cfg.token,
                                            "addresses": chunk_ips,
                                            "count": 1,
                                            "interval": 0.1,
                                            "timeout": 1,
                                            "concurrent_tasks": 100,
                                            "family": 4,
                                            "privileged": True,
                                        },
                                    )
                                    resp.raise_for_status()
                                    all_parsed_items.extend(self._parse_ping_response(resp.text))
                                except Exception as fetch_err:
                                    logger.error(
                                        "device_ping fetch failed for %s/%s chunk %d: %s",
                                        mid, tg.value, chunk_start // CHUNK_SIZE, fetch_err,
                                    )

                            ip_to_result = {i.target: i for i in all_parsed_items}

                            ping_repo = get_typed_repo("ping_batch", session)
                            # 每個 hostname 都存一筆 ping_record（同 IP 不同 hostname 各自存）
                            saved_hostnames: set[str] = set()
                            for ip, result_item in ip_to_result.items():
                                for hn, _ in hostname_map.get(ip, set()):
                                    if hn in saved_hostnames:
                                        continue
                                    saved_hostnames.add(hn)
                                    await ping_repo.save_batch(
                                        switch_hostname=hn,
                                        raw_data=None,
                                        parsed_items=[result_item],
                                        maintenance_id=mid,
                                    )

                            from datetime import datetime, timezone
                            now = datetime.now(timezone.utc)
                            for ip, result_item in ip_to_result.items():
                                for dev, side in ip_to_dev_side.get(ip, []):
                                    if side == "old":
                                        dev.old_is_reachable = result_item.is_reachable
                                        dev.old_last_check_at = now
                                    else:
                                        dev.new_is_reachable = result_item.is_reachable
                                        dev.new_last_check_at = now

                            await session.flush()

                            logger.info(
                                "device_ping %s/%s: %d IPs (%d chunks)",
                                mid, tg.value, len(device_ip_map),
                                (len(all_ips) + CHUNK_SIZE - 1) // CHUNK_SIZE,
                            )

                except Exception as e:
                    logger.error("device_ping failed for %s: %s", mid, e)
                    try:
                        from app.services.system_log import write_log, format_error_detail
                        await write_log(
                            level="ERROR",
                            source="scheduler",
                            summary=f"設備 Ping 失敗 ({type(e).__name__}): {mid}",
                            detail=format_error_detail(exc=e, context={"歲修": mid}),
                            module="device_ping",
                            maintenance_id=mid,
                        )
                    except Exception:
                        logger.error("Failed to write system log for device_ping %s", mid)

        elapsed = _time.monotonic() - t0
        logger.info("device_ping cycle done: %d maintenances, %.2fs",
                     len(maintenance_ids), elapsed)

    # ── Client Ping ──────────────────────────────────────────────

    def add_client_ping_job(self, interval_seconds: int = 30) -> str:
        """Client IP Ping 獨立排程。"""
        job_id = "client_ping"
        self.scheduler.add_job(
            self._run_client_ping,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            replace_existing=True,
        )
        logger.info("Added client ping job every %ds", interval_seconds)
        return job_id

    async def _run_client_ping(self) -> None:
        """
        Client Ping：按 tenant_group 分組 batch-ping，存入 ping_records。

        純採集，不直接更新 Case。
        Case.last_ping_reachable 由 client_collection 統一透過
        ClientRecord → update_ping_status() 更新。
        """
        t0 = _time.monotonic()
        logger.info("Running client ping")

        maintenance_ids = await self._get_active_maintenance_ids()
        if not maintenance_ids:
            return

        from app.core.config import settings
        from app.core.enums import TenantGroup
        from app.db.base import get_session_context
        from app.db.models import MaintenanceMacList
        from app.repositories.typed_records import get_typed_repo

        import httpx
        from sqlalchemy import select

        ping_cfg = settings.gnmsping
        if not ping_cfg.base_urls:
            logger.warning("No GNMSPING base_urls configured, skipping client ping")
            return

        async with httpx.AsyncClient(timeout=ping_cfg.timeout, verify=False) as http:
            for mid in maintenance_ids:
                try:
                    async with get_session_context() as session:
                        mac_stmt = select(MaintenanceMacList).where(
                            MaintenanceMacList.maintenance_id == mid,
                            MaintenanceMacList.ip_address != None,  # noqa: E711
                        )
                        mac_result = await session.execute(mac_stmt)
                        mac_entries = mac_result.scalars().all()

                        groups: dict[TenantGroup, set[str]] = {}
                        for m in mac_entries:
                            if not (m.ip_address and m.ip_address.strip()):
                                continue
                            tg = m.tenant_group or TenantGroup.F18
                            groups.setdefault(tg, set()).add(m.ip_address)

                        if not groups:
                            continue

                        for tg, client_ips in groups.items():
                            if not client_ips:
                                continue

                            base_url = (
                                ping_cfg.base_urls.get(tg.value)
                                or ping_cfg.base_urls.get(tg.value.lower())
                            )
                            if not base_url:
                                logger.warning(
                                    "No GNMSPING base_url for tenant %s, "
                                    "skipping %d client IPs",
                                    tg.value, len(client_ips),
                                )
                                continue

                            url = base_url.rstrip("/") + ping_cfg.endpoint
                            sorted_ips = sorted(client_ips)

                            chunk_size = 500
                            all_results: list = []
                            all_raw: list[str] = []
                            for i in range(0, len(sorted_ips), chunk_size):
                                chunk = sorted_ips[i:i + chunk_size]
                                try:
                                    resp = await http.post(
                                        url,
                                        json={
                                            "app_name": "network-change-orchestrator",
                                            "token": ping_cfg.token,
                                            "addresses": chunk,
                                            "count": 1,
                                            "interval": 0.1,
                                            "timeout": 1,
                                            "concurrent_tasks": 100,
                                            "family": 4,
                                            "privileged": True,
                                        },
                                    )
                                    resp.raise_for_status()
                                except Exception as fetch_err:
                                    logger.error(
                                        "client_ping fetch failed for "
                                        "%s/%s chunk %d-%d: %s",
                                        mid, tg.value,
                                        i, i + len(chunk), fetch_err,
                                    )
                                    continue

                                parsed_items = self._parse_ping_response(
                                    resp.text,
                                )
                                ip_to_result = {
                                    it.target: it for it in parsed_items
                                }
                                all_results.extend(
                                    ip_to_result[ip]
                                    for ip in chunk
                                    if ip in ip_to_result
                                )
                                all_raw.append(resp.text)

                            if all_results:
                                client_repo = get_typed_repo("gnms_ping", session)
                                await client_repo.save_batch(
                                    switch_hostname=f"__CLIENT_PING_{tg.value}__",
                                    raw_data="\n".join(all_raw),
                                    parsed_items=all_results,
                                    maintenance_id=mid,
                                )

                            logger.info(
                                "client_ping %s/%s: %d IPs (%d chunks)",
                                mid, tg.value, len(all_results),
                                (len(sorted_ips) + chunk_size - 1) // chunk_size,
                            )

                except Exception as e:
                    logger.error("client_ping failed for %s: %s", mid, e)
                    try:
                        from app.services.system_log import write_log, format_error_detail
                        await write_log(
                            level="ERROR",
                            source="scheduler",
                            summary=f"Client Ping 失敗 ({type(e).__name__}): {mid}",
                            detail=format_error_detail(exc=e, context={"歲修": mid}),
                            module="client_ping",
                            maintenance_id=mid,
                        )
                    except Exception:
                        logger.error("Failed to write system log for client_ping %s", mid)

        elapsed = _time.monotonic() - t0
        logger.info("client_ping cycle done: %d maintenances, %.2fs",
                     len(maintenance_ids), elapsed)

    @staticmethod
    def _parse_ping_response(raw_output: str) -> list:
        """Parse ping response into PingResultData list.

        Supports two formats:
        1. JSON (real GNMS Ping API)::

            {"result": {"10.1.1.1": {"is_alive": true, ...}, ...}}

        2. CSV (mock server fallback)::

            IP,Reachable,Latency_ms
            10.1.1.1,True,1.2
        """
        import json

        from app.parsers.protocols import PingResultData

        stripped = raw_output.strip()
        if not stripped:
            return []

        try:
            data = json.loads(stripped)
            if isinstance(data, dict) and "result" in data:
                results = []
                for ip, stats in data["result"].items():
                    if isinstance(stats, dict):
                        is_alive = bool(stats.get("is_alive", False))
                    else:
                        is_alive = False
                    results.append(PingResultData(
                        target=str(ip),
                        is_reachable=is_alive,
                    ))
                return results
        except (json.JSONDecodeError, ValueError):
            pass

        results = []
        for line in stripped.splitlines():
            line = line.strip()
            if not line or line.startswith("IP,"):
                continue
            parts = line.split(",")
            if len(parts) < 2:
                continue
            try:
                ip = parts[0].strip()
                reachable = parts[1].strip().lower() == "true"
                results.append(PingResultData(
                    target=ip,
                    is_reachable=reachable,
                ))
            except (ValueError, IndexError):
                continue
        return results

    # ── Retention ──────────────────────────────────────────────

    def add_retention_job(self, interval_minutes: int = 30) -> str:
        """Add a retention cleanup job."""
        job_id = "retention_cleanup"

        self.scheduler.add_job(
            self._run_retention,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=job_id,
            replace_existing=True,
        )
        logger.info("Added retention cleanup job every %d minutes", interval_minutes)
        return job_id

    async def _run_retention(self) -> None:
        """Run retention cleanup (deactivated maintenances + old batches)."""
        from app.services.retention import RetentionService

        try:
            svc = RetentionService()
            stats = await svc.cleanup_deactivated()
            if stats["maintenances_cleaned"] > 0:
                logger.info("Retention cleanup: %s", stats)

            from app.core.config import settings
            old_stats = await svc.cleanup_old_batches(
                retention_days=settings.max_collection_days,
            )
            if old_stats["batches_deleted"] > 0:
                logger.info("Old batch cleanup: %s", old_stats)

            log_deleted = await svc.cleanup_system_logs(retention_days=3)
            if log_deleted > 0:
                logger.info("System log cleanup: %d logs deleted", log_deleted)
        except Exception as e:
            logger.error("Retention cleanup failed: %s", e)

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")

    def stop(self) -> None:
        """Stop the scheduler and collection loop."""
        # Signal the continuous loop to stop
        self._loop_stop.set()
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            logger.info("Collection loop cancel requested")

        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
            logger.info("Scheduler stopped")

    def is_running(self) -> bool:
        """Check if scheduler is running."""
        return self.scheduler.running


# ── Singleton ────────────────────────────────────────────────────

_scheduler_service: SchedulerService | None = None


def get_scheduler_service() -> SchedulerService:
    """Get or create SchedulerService instance."""
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service


async def setup_scheduled_jobs(job_configs: list[dict[str, Any]]) -> None:
    """
    Setup scheduled jobs from configuration.

    採集使用連續迴圈（完成即開始下一輪），Ping / Retention 使用 APScheduler 定時。
    """
    from app.core.config import settings
    from app.snmp.collection_service import (
        API_PASSTHROUGH_COLLECTORS,
        FAST_ROUND_COLLECTORS,
        FULL_ROUND_COLLECTORS,
    )

    scheduler = get_scheduler_service()

    # gnms_ping / ping_batch handled by independent ping jobs
    _CUSTOM_JOBS = {"gnms_ping", "ping_batch"}
    ping_interval = 15
    for config in job_configs:
        if config["name"] in _CUSTOM_JOBS:
            ping_interval = config.get("interval", 15)

    config_by_name = {c["name"]: c for c in job_configs}

    if settings.collection_mode == "snmp":
        # ── Continuous collection loop (SNMP mode) ──
        # 所有 SNMP collectors 合為一輪，ACL 走 API passthrough
        all_snmp = FAST_ROUND_COLLECTORS + FULL_ROUND_COLLECTORS
        api_cfgs = [
            {"name": n, "source": config_by_name.get(n, {}).get("source", "")}
            for n in API_PASSTHROUGH_COLLECTORS
        ]
        scheduler.start_collection_loop(
            snmp_collectors=all_snmp,
            api_collectors=api_cfgs,
            min_round_gap=settings.min_round_gap,
        )

        logger.info(
            "Continuous loop: %d SNMP + %d API collectors, min_gap=%ds",
            len(all_snmp), len(api_cfgs),
            settings.min_round_gap,
        )
    else:
        # ── Continuous collection loop (API mode) ──
        # API 模式下所有 collector 都走 API passthrough
        api_cfgs = [
            {"name": c["name"], "source": c.get("source", "")}
            for c in job_configs if c["name"] not in _CUSTOM_JOBS
        ]
        scheduler.start_collection_loop(
            snmp_collectors=[],
            api_collectors=api_cfgs,
            min_round_gap=settings.min_round_gap,
        )

    # Independent ping jobs (same for both modes)
    scheduler.add_device_ping_job(interval_seconds=ping_interval)
    scheduler.add_client_ping_job(interval_seconds=ping_interval)

    # Retention cleanup
    scheduler.add_retention_job(interval_minutes=30)

    scheduler.start()
