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
        # Switch collection service based on COLLECTION_MODE
        from app.core.config import settings
        if settings.collection_mode == "snmp":
            from app.snmp.collection_service import SnmpCollectionService
            self.collection_service = SnmpCollectionService()  # type: ignore[assignment]
            logger.info("Using SNMP collection mode")
        else:
            self.collection_service = ApiCollectionService()
            logger.info("Using API collection mode")
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
                #    含 deadlock 重試（與 client_ping 並行更新 cases 表時可能衝突）
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
                        break  # 成功，跳出重試
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

                        # 按 tenant_group 分組 device IP
                        groups: dict[TenantGroup, dict[str, str]] = {}
                        for d in devices:
                            if not (d.new_hostname and d.new_ip_address):
                                continue
                            tg = d.tenant_group or TenantGroup.F18
                            ip_map = groups.setdefault(tg, {})
                            ip_map[d.new_ip_address] = d.new_hostname
                            if (d.old_hostname and d.old_ip_address
                                    and d.old_ip_address != d.new_ip_address):
                                ip_map[d.old_ip_address] = d.old_hostname

                        if not groups:
                            continue

                        # 建立 IP → (device, "old"|"new") 映射，用於回寫 ping 結果
                        ip_to_dev_side: dict[str, list[tuple]] = {}
                        for d in devices:
                            if d.new_ip_address:
                                ip_to_dev_side.setdefault(d.new_ip_address, []).append((d, "new"))
                            if d.old_ip_address:
                                ip_to_dev_side.setdefault(d.old_ip_address, []).append((d, "old"))

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
                            try:
                                resp = await http.post(
                                    url,
                                    json={
                                        "app_name": "network_change_orchestrator",
                                        "token": ping_cfg.token,
                                        "addresses": sorted(device_ip_map),
                                    },
                                )
                                resp.raise_for_status()
                            except Exception as fetch_err:
                                logger.error(
                                    "device_ping fetch failed for %s/%s: %s",
                                    mid, tg.value, fetch_err,
                                )
                                continue

                            parsed_items = self._parse_ping_csv(resp.text)
                            ip_to_result = {i.target: i for i in parsed_items}

                            ping_repo = get_typed_repo("ping_batch", session)
                            for ip, hostname in device_ip_map.items():
                                result_item = ip_to_result.get(ip)
                                if result_item is None:
                                    continue
                                await ping_repo.save_batch(
                                    switch_hostname=hostname,
                                    raw_data=resp.text,
                                    parsed_items=[result_item],
                                    maintenance_id=mid,
                                )

                            # 回寫 is_reachable 到設備清單（區分 old/new）
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
                                "device_ping %s/%s: %d IPs",
                                mid, tg.value, len(device_ip_map),
                            )

                except Exception as e:
                    logger.error("device_ping failed for %s: %s", mid, e)
                    from app.services.system_log import write_log, format_error_detail
                    await write_log(
                        level="ERROR",
                        source="scheduler",
                        summary=f"設備 Ping 失敗 ({type(e).__name__}): {mid}",
                        detail=format_error_detail(exc=e, context={"歲修": mid}),
                        module="device_ping",
                        maintenance_id=mid,
                    )

        elapsed = _time.monotonic() - t0
        logger.info("device_ping cycle done: %d maintenances, %.2fs",
                     len(maintenance_ids), elapsed)

    # ── Client Ping ──────────────────────────────────────────────

    def add_client_ping_job(self, interval_seconds: int = 30) -> str:
        """Client IP Ping 獨立排程，完成後立即更新 Case 燈號。"""
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

                        # 按 tenant_group 分組
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
                            try:
                                resp = await http.post(
                                    url,
                                    json={
                                        "app_name": "network_change_orchestrator",
                                        "token": ping_cfg.token,
                                        "addresses": sorted(client_ips),
                                    },
                                )
                                resp.raise_for_status()
                            except Exception as fetch_err:
                                logger.error(
                                    "client_ping fetch failed for %s/%s: %s",
                                    mid, tg.value, fetch_err,
                                )
                                continue

                            parsed_items = self._parse_ping_csv(resp.text)
                            ip_to_result = {i.target: i for i in parsed_items}

                            # 存入 ping_records（純採集）
                            client_results = [
                                ip_to_result[ip]
                                for ip in client_ips
                                if ip in ip_to_result
                            ]
                            if client_results:
                                client_repo = get_typed_repo("gnms_ping", session)
                                await client_repo.save_batch(
                                    switch_hostname=f"__CLIENT_PING_{tg.value}__",
                                    raw_data=resp.text,
                                    parsed_items=client_results,
                                    maintenance_id=mid,
                                )

                            logger.info(
                                "client_ping %s/%s: %d IPs",
                                mid, tg.value, len(client_results),
                            )

                except Exception as e:
                    logger.error("client_ping failed for %s: %s", mid, e)
                    from app.services.system_log import write_log, format_error_detail
                    await write_log(
                        level="ERROR",
                        source="scheduler",
                        summary=f"Client Ping 失敗 ({type(e).__name__}): {mid}",
                        detail=format_error_detail(exc=e, context={"歲修": mid}),
                        module="client_ping",
                        maintenance_id=mid,
                    )

        elapsed = _time.monotonic() - t0
        logger.info("client_ping cycle done: %d maintenances, %.2fs",
                     len(maintenance_ids), elapsed)

    @staticmethod
    def _parse_ping_csv(raw_output: str) -> list:
        """Parse ping CSV response into PingResultData list."""
        from app.parsers.protocols import PingResultData

        results = []
        for line in raw_output.strip().splitlines():
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

    # gnms_ping / ping_batch 由獨立的 device_ping + client_ping 處理
    _CUSTOM_JOBS = {"gnms_ping", "ping_batch"}
    ping_interval = 30
    for config in job_configs:
        if config["name"] in _CUSTOM_JOBS:
            ping_interval = config.get("interval", 30)

    # 收集需要標準 per-device 採集的 job（排除自訂 job）
    standard_jobs = [
        c for c in job_configs if c["name"] not in _CUSTOM_JOBS
    ]

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

    # 加入獨立的設備 Ping + Client Ping 任務
    scheduler.add_device_ping_job(interval_seconds=ping_interval)
    scheduler.add_client_ping_job(interval_seconds=ping_interval)

    # 加入 client collection 任務（每 120 秒）
    scheduler.add_client_collection_job(interval_seconds=120)

    # 加入 retention cleanup 任務（每 30 分鐘）
    scheduler.add_retention_job(interval_minutes=30)

    scheduler.start()
