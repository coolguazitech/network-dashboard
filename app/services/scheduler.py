"""
Scheduler Service.

Handles scheduled jobs for data collection using APScheduler.

此服務會自動對「所有活躍歲修」執行採集任務，不需要指定特定的 maintenance_id。
"""
from __future__ import annotations

import logging
import traceback as tb_module
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.services.client_collection_service import ClientCollectionService
from app.services.data_collection import DataCollectionService
from app.services.mock_data_generator import get_mock_data_generator

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Service for managing scheduled data collection jobs.

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
        self.collection_service = DataCollectionService()
        self.client_collection_service = ClientCollectionService()
        self._jobs: dict[str, str] = {}  # job_name -> job_id
        # 追蹤每個歲修的初始 checkpoint 寫入次數
        # 新歲修需要至少 2 次寫入才能讓比較頁面有 Before ≠ Current
        self._initial_checkpoint_counts: dict[str, int] = {}

    def add_collection_job(
        self,
        job_name: str,
        interval_seconds: int,
    ) -> str:
        """
        Add a scheduled collection job.

        此 job 會自動對所有活躍歲修執行採集。

        Args:
            job_name: Data type name (e.g., "transceiver", "mac-table")
            interval_seconds: Collection interval in seconds

        Returns:
            str: Job ID
        """
        job_id = f"collect_{job_name}"

        # Remove existing job if any
        if job_name in self._jobs:
            self.remove_job(job_name)

        # Add new job
        job = self.scheduler.add_job(
            self._run_collection,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            kwargs={
                "job_name": job_name,
            },
            replace_existing=True,
        )

        self._jobs[job_name] = job.id
        logger.info(
            f"Added collection job '{job_name}' every {interval_seconds}s"
        )

        return job.id

    def remove_job(self, job_name: str) -> bool:
        """
        Remove a scheduled job.

        Args:
            job_name: Job name

        Returns:
            bool: True if job was removed
        """
        job_id = self._jobs.get(job_name)
        if job_id:
            self.scheduler.remove_job(job_id)
            del self._jobs[job_name]
            logger.info(f"Removed collection job '{job_name}'")
            return True
        return False

    def get_jobs(self) -> list[dict[str, Any]]:
        """
        Get list of all scheduled jobs.

        Returns:
            list: Job information
        """
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time),
                "trigger": str(job.trigger),
            })
        return jobs

    async def _get_active_maintenance_ids(self) -> list[str]:
        """
        取得所有活躍的歲修 ID。

        自動停用超過 max_collection_days 的歲修。

        Returns:
            list: 活躍歲修 ID 列表
        """
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import select

        from app.core.config import settings
        from app.db.base import get_session_context
        from app.db.models import MaintenanceConfig

        async with get_session_context() as session:
            # 自動停用超時歲修
            cutoff = datetime.now(timezone.utc) - timedelta(
                days=settings.max_collection_days
            )
            expired_stmt = select(MaintenanceConfig).where(
                MaintenanceConfig.is_active == True,  # noqa: E712
                MaintenanceConfig.created_at <= cutoff,
            )
            expired_result = await session.execute(expired_stmt)
            expired = expired_result.scalars().all()

            for config in expired:
                config.is_active = False
                logger.warning(
                    "Auto-stopping maintenance %s: exceeded %d-day limit",
                    config.maintenance_id,
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
                            f"（超過 {settings.max_collection_days} 天上限）"
                        ),
                        module="scheduler",
                        maintenance_id=config.maintenance_id,
                    )

            # 查詢仍活躍的歲修
            stmt = select(MaintenanceConfig.maintenance_id).where(
                MaintenanceConfig.is_active == True  # noqa: E712
            )
            result = await session.execute(stmt)
            maintenance_ids = [row[0] for row in result.fetchall()]

        return maintenance_ids

    def _is_checkpoint_time(self) -> bool:
        """判斷當前是否為 checkpoint 整點。

        根據 settings.checkpoint_interval_minutes 和
        settings.collection_interval_seconds 判斷。
        例如 interval=60 時，minute=0 且在一個採集週期內為 True。
        """
        from datetime import datetime, timezone
        from app.core.config import settings

        now = datetime.now(timezone.utc)
        interval = settings.checkpoint_interval_minutes
        # 當前分鐘在 checkpoint 間隔內的偏移量
        offset_minutes = now.minute % interval
        # 如果偏移量在一個採集週期以內，視為 checkpoint 時間
        cycle_minutes = settings.collection_interval_seconds / 60
        return offset_minutes < cycle_minutes

    async def _run_collection(
        self,
        job_name: str,
    ) -> None:
        """
        Run a collection job for ALL active maintenances.

        Args:
            job_name: Data type name (e.g., "transceiver", "client-collection")
        """
        import time as _time

        t0 = _time.monotonic()
        logger.info("Running scheduled collection for '%s'", job_name)

        # 取得所有活躍歲修
        maintenance_ids = await self._get_active_maintenance_ids()

        if not maintenance_ids:
            logger.debug("No active maintenances found, skipping collection")
            return

        logger.debug(
            "Found %d active maintenances: %s",
            len(maintenance_ids),
            maintenance_ids,
        )

        # 判斷是否為 checkpoint 整點（強制寫入 DB）
        force_cp = self._is_checkpoint_time()
        if force_cp:
            logger.info("Checkpoint time — forcing DB write for '%s'", job_name)

        try:
            if job_name == "cleanup-old-records":
                # 清理任務對每個歲修執行
                for mid in maintenance_ids:
                    await self._run_cleanup_old_records(mid)

            elif job_name == "mock-client-generation":
                # Mock 資料生成對每個歲修執行
                for mid in maintenance_ids:
                    # 新歲修前 2 次採集強制寫入，確保比較頁面 Before ≠ Current
                    init_count = self._initial_checkpoint_counts.get(mid, 0)
                    force_initial = init_count < 2
                    force_cp_for_maint = force_cp or force_initial

                    await self._run_mock_client_generation(
                        mid, force_checkpoint=force_cp_for_maint,
                    )

                    if init_count < 2:
                        self._initial_checkpoint_counts[mid] = init_count + 1

            elif job_name == "client-collection":
                # 客戶端採集對每個歲修執行
                svc = self.client_collection_service
                for mid in maintenance_ids:
                    try:
                        # 新歲修前 2 次採集強制寫入
                        init_count = self._initial_checkpoint_counts.get(mid, 0)
                        force_initial = init_count < 2
                        force_cp_for_maint = force_cp or force_initial

                        result = await svc.collect_client_data(
                            maintenance_id=mid,
                            force_checkpoint=force_cp_for_maint,
                        )
                        logger.info(
                            "Client collection for %s: %d/%d switches, %d records",
                            mid,
                            result["success"],
                            result["total"],
                            result["client_records_count"],
                        )

                        # 採集後自動偵測客戶端狀態（更新 MaintenanceMacList.detection_status）
                        detect_result = await svc.detect_clients(
                            maintenance_id=mid,
                        )
                        logger.info(
                            "Client detection for %s: %d detected, %d mismatch, %d not_detected",
                            mid,
                            detect_result.get("detected", 0),
                            detect_result.get("mismatch", 0),
                            detect_result.get("not_detected", 0),
                        )

                        if init_count < 2:
                            self._initial_checkpoint_counts[mid] = init_count + 1
                    except Exception as e:
                        logger.error(
                            "Client collection failed for %s: %s",
                            mid, e,
                        )
                        from app.services.system_log import write_log, format_error_detail
                        await write_log(
                            level="ERROR",
                            source="scheduler",
                            summary=f"排程任務失敗 ({type(e).__name__}): 客戶端採集 ({mid})",
                            detail=format_error_detail(
                                exc=e,
                                context={"任務": "client-collection", "歲修": mid},
                            ),
                            module="client-collection",
                            maintenance_id=mid,
                        )

            else:
                # 指標採集（含 ping）— 對每個歲修執行
                svc = self.collection_service
                for mid in maintenance_ids:
                    try:
                        result = await svc.collect_indicator_data(
                            collection_type=job_name,
                            maintenance_id=mid,
                            force_checkpoint=force_cp,
                        )
                        logger.info(
                            "%s collection for %s: %d/%d successful",
                            job_name,
                            mid,
                            result["success"],
                            result["total"],
                        )
                    except Exception as e:
                        logger.error(
                            "%s collection failed for %s: %s",
                            job_name, mid, e,
                        )
                        from app.services.system_log import write_log, format_error_detail
                        await write_log(
                            level="ERROR",
                            source="scheduler",
                            summary=f"排程任務失敗 ({type(e).__name__}): {job_name} 採集 ({mid})",
                            detail=format_error_detail(
                                exc=e,
                                context={"任務": job_name, "歲修": mid},
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

    async def _run_mock_client_generation(
        self,
        maintenance_id: str,
        force_checkpoint: bool = False,
    ) -> None:
        """
        Run mock client data generation for a specific maintenance.

        模擬真實情境：
        - 系統不知道現在是哪個「階段」
        - 系統查詢所有可達的 ARP 來源來找 MAC
        - MAC 物理位置由收斂時間決定（模擬設備切換）

        收斂邏輯模擬：
        - 收斂前 (t < T/2)：MAC 物理上在 OLD 設備
        - 收斂後 (t >= T/2)：MAC 物理上在 NEW 設備
        - 無論哪個階段，只要 MAC 所在的設備可達，就能採集到

        注意：必須先設定 ArpSource 才會生成資料。
        """
        from sqlalchemy import select, func

        from app.db.base import get_session_context
        from app.db.models import ClientRecord, ArpSource
        from app.fetchers.convergence import MockTimeTracker
        from app.core.config import settings

        generator = get_mock_data_generator()
        tracker = MockTimeTracker()

        # 判斷 MAC 目前物理上在哪裡（收斂前在 OLD，收斂後在 NEW）
        elapsed = tracker.get_elapsed_seconds(maintenance_id)
        converge_time = settings.mock_ping_converge_time
        switch_time = converge_time / 2
        has_converged = elapsed >= switch_time

        # ARP 來源（NEW CORE 設備）是否可達？
        # 收斂前 NEW 設備不可達 → 無法透過 ARP 確認 MAC → ping 未執行 → ping_reachable=None
        # 收斂後 NEW 設備可達 → ARP 找到 MAC → ping 可執行 → ping_reachable=True/False
        can_ping = has_converged

        logger.debug(
            "Mock client generation for %s: elapsed=%.1fs, converged=%s, can_ping=%s",
            maintenance_id, elapsed, has_converged, can_ping,
        )

        async with get_session_context() as session:
            from app.db.models import MaintenanceMacList

            # 先檢查是否有設定 ArpSource
            # 如果沒有設定，就不應該生成 ClientRecord 資料
            arp_stmt = select(func.count()).select_from(ArpSource).where(
                ArpSource.maintenance_id == maintenance_id
            )
            arp_count_result = await session.execute(arp_stmt)
            arp_count = arp_count_result.scalar()

            if arp_count == 0:
                logger.warning(
                    "No ArpSource configured for %s - skipping mock client generation. "
                    "Please configure ARP sources first.",
                    maintenance_id,
                )
                return

            # 取得最新記錄作為基準
            subquery = (
                select(func.max(ClientRecord.collected_at))
                .where(
                    ClientRecord.maintenance_id == maintenance_id,
                )
                .scalar_subquery()
            )

            stmt = select(ClientRecord).where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.collected_at == subquery,
            )
            result = await session.execute(stmt)
            latest_records = list(result.scalars().all())

            # 獲取設備對應清單
            device_mapping = await generator._get_device_mapping(
                maintenance_id, session
            )

            # 獲取所有可達設備（包含 OLD 和 NEW，模擬查詢所有 ARP 來源）
            old_reachable = generator._get_reachable_devices(
                device_mapping, is_old=True
            )
            new_reachable = generator._get_reachable_devices(
                device_mapping, is_old=False
            )
            all_reachable = old_reachable | new_reachable

            logger.debug(
                "Reachable devices for %s: OLD=%d, NEW=%d, total=%d",
                maintenance_id, len(old_reachable), len(new_reachable), len(all_reachable),
            )

            # 生成記錄
            # - has_converged 決定 MAC 物理上在 OLD 還是 NEW 設備
            # - all_reachable 決定哪些設備可以被查詢到
            new_records = await generator.generate_client_records_realistic(
                maintenance_id=maintenance_id,
                has_converged=has_converged,
                reachable_devices=all_reachable,
                session=session,
                base_records=latest_records if latest_records else None,
                can_ping=can_ping,
            )

            # 檢查是否有新加入 MaintenanceMacList 但尚未有記錄的 MAC
            if latest_records:
                existing_macs = {r.mac_address.upper() for r in new_records if r.mac_address}

                # 查詢所有 MAC 清單
                mac_list_stmt = select(MaintenanceMacList).where(
                    MaintenanceMacList.maintenance_id == maintenance_id
                )
                mac_list_result = await session.execute(mac_list_stmt)
                mac_list = mac_list_result.scalars().all()

                # 為新加入的 MAC 創建記錄
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                for mac_entry in mac_list:
                    mac_upper = mac_entry.mac_address.upper() if mac_entry.mac_address else ""
                    if mac_upper and mac_upper not in existing_macs:
                        new_record = generator._create_new_record_realistic(
                            mac_entry, maintenance_id,
                            has_converged,
                            now, device_mapping, all_reachable,
                            can_ping=can_ping,
                        )
                        if new_record:  # None 表示 MAC「消失」或設備不可達
                            new_records.append(new_record)
                            logger.info("Added new MAC to mock data: %s", mac_upper)

            # 變更偵測：hash 比對
            from app.services.change_cache import ClientChangeCache
            cache = self.client_collection_service.change_cache
            data_changed = cache.has_changed(maintenance_id, new_records)

            if data_changed or force_checkpoint:
                # 儲存 ClientRecord 到資料庫
                for record in new_records:
                    session.add(record)
                await session.commit()

                if new_records:
                    logger.info(
                        "Mock client generation: %d records for %s%s",
                        len(new_records),
                        maintenance_id,
                        " (checkpoint)" if force_checkpoint and not data_changed else "",
                    )
            else:
                logger.debug(
                    "No mock client data change for %s, skipping DB write",
                    maintenance_id,
                )

            # 更新 MaintenanceMacList.detection_status（不受快取影響）
            # can_ping=True → ARP 來源可達，已確認 MAC → DETECTED
            # can_ping=False → ARP 來源不可達，無法確認 → NOT_DETECTED
            from sqlalchemy import update
            from app.core.enums import ClientDetectionStatus

            detection_status = (
                ClientDetectionStatus.DETECTED if can_ping
                else ClientDetectionStatus.NOT_DETECTED
            )

            for record in new_records:
                if not record.mac_address:
                    continue

                update_stmt = (
                    update(MaintenanceMacList)
                    .where(
                        MaintenanceMacList.maintenance_id == maintenance_id,
                        MaintenanceMacList.mac_address == record.mac_address,
                    )
                    .values(detection_status=detection_status)
                )
                await session.execute(update_stmt)

            await session.commit()
            logger.info(
                "Updated detection_status for %d MACs in %s",
                len(new_records),
                maintenance_id,
            )

            # 也生成 VersionRecord（設備版本資料）
            version_records = await generator.generate_version_records(
                maintenance_id=maintenance_id,
                session=session,
            )

            for record in version_records:
                session.add(record)
            await session.commit()

            if version_records:
                logger.info(
                    "Mock version generation: %d records for %s",
                    len(version_records),
                    maintenance_id,
                )

    async def _run_cleanup_old_records(
        self,
        maintenance_id: str,
        retention_days: int = 7,
    ) -> None:
        """
        Run cleanup of old ClientRecord data for a specific maintenance.

        Removes records older than retention_days.
        """
        from app.db.base import get_session_context
        from app.services.client_comparison_service import cleanup_old_client_records

        async with get_session_context() as session:
            deleted_count = await cleanup_old_client_records(
                maintenance_id=maintenance_id,
                retention_days=retention_days,
                session=session,
            )

            if deleted_count > 0:
                logger.info(
                    "Cleanup: deleted %d old records for %s",
                    deleted_count,
                    maintenance_id,
                )

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


# Singleton instance
_scheduler_service: SchedulerService | None = None


def get_scheduler_service() -> SchedulerService:
    """
    Get or create SchedulerService instance.

    Returns:
        SchedulerService instance
    """
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service


async def setup_scheduled_jobs(job_configs: list[dict[str, Any]]) -> None:
    """
    Setup scheduled jobs from configuration.

    所有採集任務會自動遍歷所有活躍的歲修 ID，不需要指定特定的 maintenance_id。

    Args:
        job_configs: List of job configurations.
            Each config should have:
            - name: str (data type, e.g., "transceiver", "mac-table")
            - interval: int (seconds)
    """
    scheduler = get_scheduler_service()

    for config in job_configs:
        scheduler.add_collection_job(
            job_name=config["name"],
            interval_seconds=config.get("interval", 30),
        )

    scheduler.start()
