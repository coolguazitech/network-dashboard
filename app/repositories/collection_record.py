"""
Collection Record Repository.

Data access layer for CollectionRecord model (raw data storage).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, select

from app.core.enums import MaintenancePhase
from app.db.models import CollectionRecord
from app.repositories.base import BaseRepository


class CollectionRecordRepository(BaseRepository[CollectionRecord]):
    """Repository for CollectionRecord operations."""

    model = CollectionRecord

    async def save_collection(
        self,
        indicator_type: str,
        switch_hostname: str,
        raw_data: str,
        parsed_data: dict[str, Any],
        phase: MaintenancePhase = MaintenancePhase.POST,
        maintenance_id: str | None = None,
    ) -> CollectionRecord:
        """
        Save a new collection record.

        Args:
            indicator_type: Type of indicator (e.g., "transceiver")
            switch_hostname: Switch hostname
            raw_data: Raw CLI output
            parsed_data: Parsed data as dict
            phase: Maintenance phase (PRE/POST)
            maintenance_id: Maintenance job ID (optional)

        Returns:
            Created CollectionRecord
        """
        return await self.create(
            indicator_type=indicator_type,
            switch_hostname=switch_hostname,
            raw_data=raw_data,
            parsed_data=parsed_data,
            phase=phase,
            maintenance_id=maintenance_id,
        )

    async def get_latest_by_indicator(
        self,
        indicator_type: str,
        phase: MaintenancePhase | None = None,
        maintenance_id: str | None = None,
    ) -> list[CollectionRecord]:
        """
        Get latest collection records for an indicator.

        Returns the most recent record per switch.

        Args:
            indicator_type: Type of indicator
            phase: Filter by phase (optional)
            maintenance_id: Filter by maintenance ID (optional)

        Returns:
            List of latest CollectionRecords (one per switch)
        """
        # Subquery to get max collected_at per switch
        from sqlalchemy import func

        subq = (
            select(
                CollectionRecord.switch_hostname,
                func.max(CollectionRecord.collected_at).label("max_time"),
            )
            .where(CollectionRecord.indicator_type == indicator_type)
        )

        if phase:
            subq = subq.where(CollectionRecord.phase == phase)
        if maintenance_id:
            subq = subq.where(
                CollectionRecord.maintenance_id == maintenance_id
            )

        subq = subq.group_by(CollectionRecord.switch_hostname).subquery()

        # Main query
        stmt = (
            select(CollectionRecord)
            .join(
                subq,
                and_(
                    CollectionRecord.switch_hostname == subq.c.switch_hostname,
                    CollectionRecord.collected_at == subq.c.max_time,
                ),
            )
            .where(CollectionRecord.indicator_type == indicator_type)
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_timeseries(
        self,
        indicator_type: str,
        switch_hostname: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[CollectionRecord]:
        """
        Get collection records as time series.

        Args:
            indicator_type: Type of indicator
            switch_hostname: Filter by switch (optional, None = all)
            start_time: Start of time range (optional)
            end_time: End of time range (optional)
            limit: Maximum records to return

        Returns:
            List of CollectionRecords ordered by time
        """
        stmt = (
            select(CollectionRecord)
            .where(CollectionRecord.indicator_type == indicator_type)
            .order_by(CollectionRecord.collected_at.desc())
            .limit(limit)
        )

        if switch_hostname:
            stmt = stmt.where(
                CollectionRecord.switch_hostname == switch_hostname
            )
        if start_time:
            stmt = stmt.where(CollectionRecord.collected_at >= start_time)
        if end_time:
            stmt = stmt.where(CollectionRecord.collected_at <= end_time)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_switch_and_indicator(
        self,
        switch_hostname: str,
        indicator_type: str,
        phase: MaintenancePhase | None = None,
    ) -> list[CollectionRecord]:
        """
        Get all records for a specific switch and indicator.

        Args:
            switch_hostname: Switch hostname
            indicator_type: Type of indicator
            phase: Filter by phase (optional)

        Returns:
            List of CollectionRecords
        """
        stmt = (
            select(CollectionRecord)
            .where(CollectionRecord.switch_hostname == switch_hostname)
            .where(CollectionRecord.indicator_type == indicator_type)
            .order_by(CollectionRecord.collected_at.desc())
        )

        if phase:
            stmt = stmt.where(CollectionRecord.phase == phase)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_old_records(
        self,
        indicator_type: str,
        before: datetime,
    ) -> int:
        """
        Delete old collection records.

        Args:
            indicator_type: Type of indicator
            before: Delete records older than this time

        Returns:
            Number of deleted records
        """
        from sqlalchemy import delete

        stmt = (
            delete(CollectionRecord)
            .where(CollectionRecord.indicator_type == indicator_type)
            .where(CollectionRecord.collected_at < before)
        )
        result = await self.session.execute(stmt)
        return result.rowcount  # type: ignore
