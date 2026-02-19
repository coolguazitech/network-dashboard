"""
Scheduler Service.

Handles scheduled jobs for API data collection using APScheduler.
每個 job 自動對所有 is_active=True 的歲修執行 fetch → parse → save。
"""
from __future__ import annotations

import logging
import time as _time
from datetime import datetime, timedelta, timezone
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.services.data_collection import ApiCollectionService

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Scheduler for API collection jobs.

    Uses APScheduler to run collection jobs at configured intervals.
    所有採集任務會自動遍歷所有活躍的歲修 ID。
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
        self.collection_service = ApiCollectionService()
        self._jobs: dict[str, str] = {}  # job_name -> job_id

    def add_collection_job(
        self,
        job_name: str,
        interval_seconds: int,
        source: str = "",
        initial_delay: float = 0,
    ) -> str:
        """
        Add a scheduled collection job.

        Args:
            job_name: API name from scheduler.yaml (e.g., "get_fan")
            interval_seconds: Collection interval in seconds
            source: API source (e.g., "FNA", "DNA")
            initial_delay: Seconds to delay the first trigger (for staggering)

        Returns:
            str: Job ID
        """
        job_id = f"collect_{job_name}"

        # Remove existing job if any
        if job_name in self._jobs:
            self.remove_job(job_name)

        # 錯開首次觸發時間 + 加 jitter 避免長期同步
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
        計時器在暫停歲修時凍結，恢復時繼續累計。
        """
        from datetime import datetime, timezone

        from sqlalchemy import select

        from app.core.config import settings
        from app.db.base import get_session_context
        from app.db.models import MaintenanceConfig

        max_seconds = settings.max_collection_days * 86400

        async with get_session_context() as session:
            # 查出所有活躍歲修
            active_stmt = select(MaintenanceConfig).where(
                MaintenanceConfig.is_active == True,  # noqa: E712
            )
            active_result = await session.execute(active_stmt)
            active_configs = active_result.scalars().all()

            # 檢查累計活躍時間是否超過上限
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

            # 查詢仍活躍的歲修（排除剛停用的）
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
        Run a collection job for ALL active maintenances.

        Args:
            job_name: API name (e.g., "get_fan")
            source: API source (e.g., "FNA", "DNA")
        """
        t0 = _time.monotonic()
        logger.info("Running scheduled collection for '%s'", job_name)

        maintenance_ids = await self._get_active_maintenance_ids()

        if not maintenance_ids:
            logger.debug("No active maintenances found, skipping collection")
            return

        logger.debug(
            "Found %d active maintenances: %s",
            len(maintenance_ids),
            maintenance_ids,
        )

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

        except Exception as e:
            logger.error(
                "Collection failed for '%s': %s",
                job_name, e,
            )
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
        finally:
            elapsed = _time.monotonic() - t0
            logger.info(
                "'%s' cycle done: %d maintenances, %.2fs",
                job_name,
                len(maintenance_ids),
                elapsed,
            )

    # ── Client Collection ─────────────────────────────────────

    def add_client_collection_job(self, interval_seconds: int = 120) -> str:
        """
        Add a scheduled client collection job.

        This job runs periodically and for each active maintenance:
        1. Collects client data (MAC/InterfaceStatus/ACL/Ping)
        2. Syncs cases (creates missing Case rows for new MACs)
        3. Updates Case.last_ping_reachable from latest ClientRecord
        4. Auto-reopens resolved cases with ping failure

        Args:
            interval_seconds: Collection interval in seconds (default: 120)

        Returns:
            str: Job ID
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
        """
        Run client collection for ALL active maintenances.

        After collection, sync cases and update ping status.
        """
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
                # 1. Collect client data
                result = await client_svc.collect_client_data(
                    maintenance_id=mid,
                )
                logger.info(
                    "Client collection for %s: %d/%d switches, %d records",
                    mid,
                    result["success"], result["total"],
                    result["client_records_count"],
                )

                # 2. Sync cases + update ping + auto-resolve + change flags
                async with get_session_context() as session:
                    case_svc = CaseService()
                    await case_svc.sync_cases(mid, session)
                    await case_svc.update_ping_status(mid, session)
                    await case_svc.auto_reopen_unreachable(mid, session)
                    await case_svc.auto_resolve_reachable(mid, session)
                    await case_svc.update_change_flags(mid, session)

            except Exception as e:
                logger.error(
                    "Client collection failed for %s: %s", mid, e,
                )
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

        elapsed = _time.monotonic() - t0
        logger.info(
            "Client collection cycle done: %d maintenances, %.2fs",
            len(maintenance_ids), elapsed,
        )

    # ── GNMS Ping (Client IP Ping) ───────────────────────────

    def add_gnms_ping_job(self, interval_seconds: int = 60) -> str:
        """
        Add a scheduled gnms_ping job for client IP pinging.

        Unlike standard collection jobs, gnms_ping:
        - Reads client IPs from MaintenanceMacList
        - Sends all IPs in one batch request
        - Stores results as PingRecord with collection_type="gnms_ping"
        """
        job_id = "gnms_ping"

        self.scheduler.add_job(
            self._run_gnms_ping_collection,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            replace_existing=True,
        )
        logger.info(
            "Added gnms_ping job every %ds", interval_seconds,
        )
        return job_id

    async def _run_gnms_ping_collection(self) -> None:
        """
        Ping all client IPs for active maintenances.

        Flow:
        1. Get all client IPs from MaintenanceMacList
        2. Call gnms_ping fetcher with switch_ips param
        3. Parse CSV response into PingResultData
        4. Save via ClientPingRecordRepo
        """
        t0 = _time.monotonic()
        logger.info("Running gnms_ping client collection")

        maintenance_ids = await self._get_active_maintenance_ids()
        if not maintenance_ids:
            logger.debug("No active maintenances, skipping gnms_ping")
            return

        from app.core.enums import DeviceType
        from app.db.base import get_session_context
        from app.db.models import MaintenanceMacList
        from app.fetchers.base import FetchContext
        from app.fetchers.registry import fetcher_registry
        from app.repositories.typed_records import get_typed_repo

        import httpx
        from sqlalchemy import select

        fetcher = fetcher_registry.get("gnms_ping")
        if fetcher is None:
            logger.warning("gnms_ping fetcher not registered, skipping")
            return

        async with httpx.AsyncClient() as http:
            for mid in maintenance_ids:
                try:
                    async with get_session_context() as session:
                        # 1. Get all client IPs
                        stmt = select(MaintenanceMacList).where(
                            MaintenanceMacList.maintenance_id == mid,
                            MaintenanceMacList.ip_address != None,  # noqa: E711
                        )
                        result = await session.execute(stmt)
                        mac_entries = result.scalars().all()

                        client_ips = [
                            m.ip_address for m in mac_entries
                            if m.ip_address and m.ip_address.strip()
                        ]

                        if not client_ips:
                            logger.debug(
                                "gnms_ping: no client IPs for %s", mid,
                            )
                            continue

                        # Use tenant_group from first MAC entry
                        tenant_group = mac_entries[0].tenant_group

                        # 2. Fetch — pass all IPs as comma-separated string
                        ctx = FetchContext(
                            switch_ip="0.0.0.0",
                            switch_hostname="__CLIENT_PING__",
                            device_type=DeviceType.HPE,
                            tenant_group=tenant_group,
                            maintenance_id=mid,
                            params={"switch_ips": ",".join(client_ips)},
                            http=http,
                        )
                        fetch_result = await fetcher.fetch(ctx)

                        if not fetch_result.success:
                            logger.error(
                                "gnms_ping fetch failed for %s: %s",
                                mid, fetch_result.error,
                            )
                            continue

                        # 3. Parse CSV response
                        parsed_items = self._parse_gnms_ping_csv(
                            fetch_result.raw_output,
                        )

                        # 4. Save via typed repo
                        typed_repo = get_typed_repo("gnms_ping", session)
                        batch = await typed_repo.save_batch(
                            switch_hostname="__CLIENT_PING__",
                            raw_data=fetch_result.raw_output,
                            parsed_items=parsed_items,
                            maintenance_id=mid,
                        )

                        if batch:
                            logger.info(
                                "gnms_ping for %s: %d IPs (new batch)",
                                mid, len(parsed_items),
                            )
                        else:
                            logger.debug(
                                "gnms_ping for %s: unchanged", mid,
                            )

                except Exception as e:
                    logger.error(
                        "gnms_ping failed for %s: %s", mid, e,
                    )
                    from app.services.system_log import (
                        write_log,
                        format_error_detail,
                    )
                    await write_log(
                        level="ERROR",
                        source="scheduler",
                        summary=f"Client Ping 失敗 ({type(e).__name__}): {mid}",
                        detail=format_error_detail(
                            exc=e,
                            context={"歲修": mid},
                        ),
                        module="gnms_ping",
                        maintenance_id=mid,
                    )

        elapsed = _time.monotonic() - t0
        logger.info(
            "gnms_ping cycle done: %d maintenances, %.2fs",
            len(maintenance_ids), elapsed,
        )

    @staticmethod
    def _parse_gnms_ping_csv(raw_output: str) -> list:
        """Parse gnms_ping CSV response into PingResultData list."""
        from app.parsers.protocols import PingResultData

        results = []
        for line in raw_output.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("IP,"):
                continue
            parts = line.split(",")
            if len(parts) < 3:
                continue
            try:
                ip = parts[0].strip()
                reachable = parts[1].strip().lower() == "true"
                latency = float(parts[2].strip()) if parts[2].strip() else 0.0
                results.append(PingResultData(
                    target=ip,
                    is_reachable=reachable,
                    success_rate=100.0 if reachable else 0.0,
                    avg_rtt_ms=latency if reachable else None,
                ))
            except (ValueError, IndexError):
                continue
        return results

    # ── Retention ──────────────────────────────────────────────

    def add_retention_job(self, interval_minutes: int = 30) -> str:
        """
        Add a retention cleanup job.

        Args:
            interval_minutes: Cleanup interval in minutes (default: 30)

        Returns:
            str: Job ID
        """
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
        """Run retention cleanup."""
        from app.services.retention import RetentionService

        try:
            svc = RetentionService()
            stats = await svc.cleanup_deactivated()
            if stats["maintenances_cleaned"] > 0:
                logger.info("Retention cleanup: %s", stats)
        except Exception as e:
            logger.error("Retention cleanup failed: %s", e)

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self) -> None:
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")

    def stop(self) -> None:
        """Stop the scheduler, waiting for running jobs to finish."""
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

    Args:
        job_configs: List of job configurations.
            Each config should have:
            - name: str (API name, e.g., "get_fan", "get_gbic_details")
            - interval: int (seconds)
            - source: str (e.g., "FNA", "DNA")
    """
    scheduler = get_scheduler_service()

    # gnms_ping 使用自訂 job（非標準 per-device 採集）
    _CUSTOM_JOBS = {"gnms_ping"}
    gnms_ping_interval = 60

    # 收集需要標準 per-device 採集的 job（排除自訂 job）
    standard_jobs = [
        c for c in job_configs if c["name"] not in _CUSTOM_JOBS
    ]
    for config in job_configs:
        if config["name"] in _CUSTOM_JOBS:
            gnms_ping_interval = config.get("interval", 60)

    # 計算錯開間距：interval ÷ job 數（至少 1s），避免全部同時觸發
    if standard_jobs:
        base_interval = standard_jobs[0].get("interval", 300)
        stagger_step = max(base_interval / len(standard_jobs), 1)
    else:
        stagger_step = 0

    for idx, config in enumerate(standard_jobs):
        scheduler.add_collection_job(
            job_name=config["name"],
            interval_seconds=config.get("interval", 30),
            source=config.get("source", ""),
            initial_delay=idx * stagger_step,
        )

    # 加入 gnms_ping 任務（client IP ping）
    scheduler.add_gnms_ping_job(interval_seconds=gnms_ping_interval)

    # 加入 client collection 任務（每 120 秒）
    scheduler.add_client_collection_job(interval_seconds=120)

    # 加入 retention cleanup 任務（每 30 分鐘）
    scheduler.add_retention_job(interval_minutes=30)

    scheduler.start()
