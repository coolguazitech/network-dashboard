"""
Scheduler Service.

Handles scheduled jobs for data collection using APScheduler.
"""
from __future__ import annotations

import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.services.client_collection_service import ClientCollectionService
from app.services.data_collection import DataCollectionService

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Service for managing scheduled data collection jobs.

    Uses APScheduler to run collection jobs at configured intervals.
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
        maintenance_id: str | None = None,
        url: str | None = None,
        source: str | None = None,
        brand: str | None = None,
    ) -> str:
        """
        Add a scheduled collection job.

        Args:
            job_name: Data type name (e.g., "transceiver", "mac-table")
            interval_seconds: Collection interval in seconds
            maintenance_id: APM maintenance ID
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
                "maintenance_id": maintenance_id,
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

    async def _run_collection(
        self,
        job_name: str,
        maintenance_id: str | None,
        url: str | None = None,
        source: str | None = None,
        brand: str | None = None,
    ) -> None:
        """
        Run a collection job.

        Args:
            job_name: Data type name (e.g., "transceiver", "client-collection")
            maintenance_id: APM maintenance ID
            url: External API endpoint URL
            source: Data source (FNA/DNA)
            brand: Device brand (HPE/Cisco-IOS/Cisco-NXOS)
        """
        logger.info("Running scheduled collection for '%s'", job_name)
        try:
            if job_name == "client-collection":
                svc = self.client_collection_service
                result = await svc.collect_client_data(
                    maintenance_id=maintenance_id or "",
                    source=source,
                    brand=brand,
                )
                logger.info(
                    "Client collection complete: "
                    "%d/%d switches, %d records",
                    result["success"],
                    result["total"],
                    result["client_records_count"],
                )
            else:
                svc = self.collection_service
                result = await svc.collect_indicator_data(
                    collection_type=job_name,
                    maintenance_id=maintenance_id,
                    url=url,
                    source=source,
                    brand=brand,
                )
                logger.info(
                    "Collection complete for '%s': "
                    "%d/%d successful",
                    job_name,
                    result["success"],
                    result["total"],
                )
        except Exception as e:
            logger.error(
                "Collection failed for '%s': %s",
                job_name, e,
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

    Args:
        job_configs: List of job configurations.
            Each config should have:
            - name: str (data type, e.g., "transceiver", "mac-table")
            - interval: int (seconds)
            - maintenance_id: str (APM ID)
            - url: str (external API endpoint, optional)
            - source: str (FNA/DNA, optional)
            - brand: str (HPE/Cisco-IOS/Cisco-NXOS, optional)
    """
    scheduler = get_scheduler_service()

    for config in job_configs:
        scheduler.add_collection_job(
            job_name=config["name"],
            interval_seconds=config.get("interval", 30),
            maintenance_id=config.get("maintenance_id"),
            url=config.get("url"),
            source=config.get("source"),
            brand=config.get("brand"),
        )

    scheduler.start()
