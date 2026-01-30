"""
Scheduler Service.

Handles scheduled jobs for data collection using APScheduler.

此服務會自動對「所有活躍歲修」執行採集任務，不需要指定特定的 maintenance_id。
"""
from __future__ import annotations

import logging
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

    def add_collection_job(
        self,
        job_name: str,
        interval_seconds: int,
        url: str | None = None,
        source: str | None = None,
        brand: str | None = None,
    ) -> str:
        """
        Add a scheduled collection job.

        此 job 會自動對所有活躍歲修執行採集。

        Args:
            job_name: Data type name (e.g., "transceiver", "mac-table")
            interval_seconds: Collection interval in seconds
            url: External API endpoint URL
            source: Data source (FNA/DNA)
            brand: Device brand (HPE/Cisco-IOS/Cisco-NXOS)

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
                "url": url,
                "source": source,
                "brand": brand,
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

        Returns:
            list: 活躍歲修 ID 列表
        """
        from sqlalchemy import select

        from app.db.base import get_session_context
        from app.db.models import MaintenanceConfig

        async with get_session_context() as session:
            stmt = select(MaintenanceConfig.maintenance_id).where(
                MaintenanceConfig.is_active == True  # noqa: E712
            )
            result = await session.execute(stmt)
            maintenance_ids = [row[0] for row in result.fetchall()]

        return maintenance_ids

    async def _run_collection(
        self,
        job_name: str,
        url: str | None = None,
        source: str | None = None,
        brand: str | None = None,
    ) -> None:
        """
        Run a collection job for ALL active maintenances.

        Args:
            job_name: Data type name (e.g., "transceiver", "client-collection")
            url: External API endpoint URL
            source: Data source (FNA/DNA)
            brand: Device brand (HPE/Cisco-IOS/Cisco-NXOS)
        """
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

        try:
            if job_name == "cleanup-old-records":
                # 清理任務對每個歲修執行
                for mid in maintenance_ids:
                    await self._run_cleanup_old_records(mid)

            elif job_name == "mock-client-generation":
                # Mock 資料生成對每個歲修執行
                for mid in maintenance_ids:
                    await self._run_mock_client_generation(mid)

            elif job_name == "client-collection":
                # 客戶端採集對每個歲修執行
                svc = self.client_collection_service
                for mid in maintenance_ids:
                    try:
                        result = await svc.collect_client_data(
                            maintenance_id=mid,
                            source=source,
                            brand=brand,
                        )
                        logger.info(
                            "Client collection for %s: %d/%d switches, %d records",
                            mid,
                            result["success"],
                            result["total"],
                            result["client_records_count"],
                        )
                    except Exception as e:
                        logger.error(
                            "Client collection failed for %s: %s",
                            mid, e,
                        )

            else:
                # 一般指標採集（從 switches 表採集，與特定歲修無關）
                svc = self.collection_service
                result = await svc.collect_indicator_data(
                    collection_type=job_name,
                    url=url,
                    source=source,
                    brand=brand,
                )
                logger.info(
                    "Collection complete for '%s': %d/%d successful",
                    job_name,
                    result["success"],
                    result["total"],
                )

        except Exception as e:
            logger.error(
                "Collection failed for '%s': %s",
                job_name, e,
            )

    async def _run_mock_client_generation(
        self,
        maintenance_id: str,
    ) -> None:
        """
        Run mock client data generation for a specific maintenance.

        Generates random ClientRecord data based on latest records or MAC list.
        """
        from sqlalchemy import select, func

        from app.db.base import get_session_context
        from app.db.models import ClientRecord
        from app.core.enums import MaintenancePhase

        generator = get_mock_data_generator()

        async with get_session_context() as session:
            # 取得最新的 NEW 階段記錄作為基準
            subquery = (
                select(func.max(ClientRecord.collected_at))
                .where(
                    ClientRecord.maintenance_id == maintenance_id,
                    ClientRecord.phase == MaintenancePhase.NEW,
                )
                .scalar_subquery()
            )

            stmt = select(ClientRecord).where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.phase == MaintenancePhase.NEW,
                ClientRecord.collected_at == subquery,
            )
            result = await session.execute(stmt)
            latest_records = list(result.scalars().all())

            # 生成新一批記錄
            new_records = await generator.generate_client_records(
                maintenance_id=maintenance_id,
                phase=MaintenancePhase.NEW,
                session=session,
                base_records=latest_records if latest_records else None,
            )

            # 儲存到資料庫
            for record in new_records:
                session.add(record)
            await session.commit()

            if new_records:
                logger.info(
                    "Mock client generation: %d records for %s",
                    len(new_records),
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
            - url: str (external API endpoint, optional)
            - source: str (FNA/DNA, optional)
            - brand: str (HPE/Cisco-IOS/Cisco-NXOS, optional)
    """
    scheduler = get_scheduler_service()

    for config in job_configs:
        scheduler.add_collection_job(
            job_name=config["name"],
            interval_seconds=config.get("interval", 30),
            url=config.get("url"),
            source=config.get("source"),
            brand=config.get("brand"),
        )

    scheduler.start()
