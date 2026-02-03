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
                    except Exception as e:
                        logger.error(
                            "Client collection failed for %s: %s",
                            mid, e,
                        )

            elif job_name == "ping":
                # Ping 採集需要針對每個歲修的 maintenance_device_list 設備
                svc = self.collection_service
                for mid in maintenance_ids:
                    try:
                        result = await svc.collect_indicator_data(
                            collection_type=job_name,
                            maintenance_id=mid,
                            url=url,
                            source=source,
                            brand=brand,
                        )
                        logger.info(
                            "Ping collection for %s: %d/%d successful",
                            mid,
                            result["success"],
                            result["total"],
                        )
                    except Exception as e:
                        logger.error(
                            "Ping collection failed for %s: %s",
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

        注意：必須先設定 ArpSource 才會生成資料，
        這與真實資料採集邏輯一致。
        """
        from sqlalchemy import select, func

        from app.db.base import get_session_context
        from app.db.models import ClientRecord, ArpSource
        from app.core.enums import MaintenancePhase

        generator = get_mock_data_generator()

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

            # 生成變化版本的記錄
            new_records = await generator.generate_client_records(
                maintenance_id=maintenance_id,
                phase=MaintenancePhase.NEW,
                session=session,
                base_records=latest_records if latest_records else None,
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

                # 獲取有效的交換機 hostname 列表
                valid_hostnames = await generator._get_valid_switch_hostnames(
                    maintenance_id, MaintenancePhase.NEW, session
                )

                # 為新加入的 MAC 創建記錄
                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                for mac_entry in mac_list:
                    mac_upper = mac_entry.mac_address.upper() if mac_entry.mac_address else ""
                    if mac_upper and mac_upper not in existing_macs:
                        new_record = generator._create_new_record(
                            mac_entry, maintenance_id, MaintenancePhase.NEW, now,
                            valid_hostnames,
                        )
                        new_records.append(new_record)
                        logger.info("Added new MAC to mock data: %s", mac_upper)

            # 儲存 ClientRecord 到資料庫
            for record in new_records:
                session.add(record)
            await session.commit()

            if new_records:
                logger.info(
                    "Mock client generation: %d records for %s",
                    len(new_records),
                    maintenance_id,
                )

            # 更新 MaintenanceMacList.detection_status（根據生成的 mock 資料）
            from sqlalchemy import update
            from app.core.enums import ClientDetectionStatus

            for record in new_records:
                if not record.mac_address:
                    continue

                # 如果 ClientRecord 存在，表示該 MAC 已被偵測到
                # detection_status 代表「是否被偵測到」，與 ping 是否成功無關
                # ping_reachable 是另一個獨立的指標（Ping 連通性驗收）
                status = ClientDetectionStatus.DETECTED

                update_stmt = (
                    update(MaintenanceMacList)
                    .where(
                        MaintenanceMacList.maintenance_id == maintenance_id,
                        MaintenanceMacList.mac_address == record.mac_address,
                    )
                    .values(detection_status=status)
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
                phase=MaintenancePhase.NEW,
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
