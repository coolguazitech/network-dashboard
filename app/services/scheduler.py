"""
Scheduler Service.

Handles scheduled jobs for data collection using APScheduler.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.core.enums import MaintenancePhase
from app.services.data_collection import DataCollectionService

logger = logging.getLogger(__name__)


class SchedulerService:
    """
    Service for managing scheduled data collection jobs.

    Uses APScheduler to run collection jobs at configured intervals.
    """

    def __init__(self) -> None:
        """Initialize scheduler."""
        self.scheduler = AsyncIOScheduler()
        self.collection_service = DataCollectionService()
        self._jobs: dict[str, str] = {}  # indicator_type -> job_id

    def add_collection_job(
        self,
        indicator_type: str,
        interval_seconds: int,
        phase: MaintenancePhase = MaintenancePhase.POST,
        maintenance_id: str | None = None,
    ) -> str:
        """
        Add a scheduled collection job.

        Args:
            indicator_type: Type of indicator to collect
            interval_seconds: Collection interval in seconds
            phase: Maintenance phase
            maintenance_id: Maintenance job ID (optional)

        Returns:
            str: Job ID
        """
        job_id = f"collect_{indicator_type}"

        # Remove existing job if any
        if job_id in self._jobs:
            self.remove_job(indicator_type)

        # Add new job
        job = self.scheduler.add_job(
            self._run_collection,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            kwargs={
                "indicator_type": indicator_type,
                "phase": phase,
                "maintenance_id": maintenance_id,
            },
            replace_existing=True,
        )

        self._jobs[indicator_type] = job.id
        logger.info(
            f"Added collection job for {indicator_type} "
            f"every {interval_seconds}s"
        )

        return job.id

    def remove_job(self, indicator_type: str) -> bool:
        """
        Remove a scheduled job.

        Args:
            indicator_type: Type of indicator

        Returns:
            bool: True if job was removed
        """
        job_id = self._jobs.get(indicator_type)
        if job_id:
            self.scheduler.remove_job(job_id)
            del self._jobs[indicator_type]
            logger.info(f"Removed collection job for {indicator_type}")
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
        indicator_type: str,
        phase: MaintenancePhase,
        maintenance_id: str | None,
    ) -> None:
        """
        Run a collection job.

        Args:
            indicator_type: Type of indicator
            phase: Maintenance phase
            maintenance_id: Maintenance job ID
        """
        logger.info(f"Running scheduled collection for {indicator_type}")
        try:
            result = await self.collection_service.collect_indicator_data(
                indicator_type=indicator_type,
                phase=phase,
                maintenance_id=maintenance_id,
            )
            logger.info(
                f"Collection complete: {result['success']}/{result['total']} "
                f"successful"
            )
        except Exception as e:
            logger.error(f"Collection failed for {indicator_type}: {e}")

    def start(self) -> None:
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("Scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
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
        job_configs: List of job configurations
            Each config should have:
            - indicator: str (indicator type)
            - interval: int (seconds)
            - enabled: bool (optional)
            - phase: str (optional, "pre" or "post")
            - maintenance_id: str (optional)

    Example:
        job_configs = [
            {"indicator": "transceiver", "interval": 300, "enabled": True},
            {"indicator": "version", "interval": 3600},
        ]
    """
    scheduler = get_scheduler_service()

    for config in job_configs:
        if not config.get("enabled", True):
            continue

        indicator = config["indicator"]
        interval = config["interval"]
        phase_str = config.get("phase", "post")
        phase = (
            MaintenancePhase.PRE
            if phase_str == "pre"
            else MaintenancePhase.POST
        )
        maintenance_id = config.get("maintenance_id")

        scheduler.add_collection_job(
            indicator_type=indicator,
            interval_seconds=interval,
            phase=phase,
            maintenance_id=maintenance_id,
        )

    scheduler.start()
