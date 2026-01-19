"""
Indicator Result Repository.

Data access layer for IndicatorResult model (calculated results).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select

from app.core.enums import MaintenancePhase
from app.db.models import IndicatorResult
from app.repositories.base import BaseRepository


class IndicatorResultRepository(BaseRepository[IndicatorResult]):
    """Repository for IndicatorResult operations."""

    model = IndicatorResult

    async def save_result(
        self,
        indicator_type: str,
        pass_rates: dict[str, float],
        total_count: int,
        pass_count: int,
        fail_count: int,
        phase: MaintenancePhase = MaintenancePhase.POST,
        maintenance_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> IndicatorResult:
        """
        Save an indicator evaluation result.

        Args:
            indicator_type: Type of indicator
            pass_rates: Pass rates for each metric
            total_count: Total items evaluated
            pass_count: Items that passed
            fail_count: Items that failed
            phase: Maintenance phase
            maintenance_id: Maintenance job ID (optional)
            details: Additional details (optional)

        Returns:
            Created IndicatorResult
        """
        return await self.create(
            indicator_type=indicator_type,
            pass_rates=pass_rates,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=fail_count,
            phase=phase,
            maintenance_id=maintenance_id,
            details=details,
        )

    async def get_latest_result(
        self,
        indicator_type: str,
        phase: MaintenancePhase | None = None,
        maintenance_id: str | None = None,
    ) -> IndicatorResult | None:
        """
        Get the latest result for an indicator.

        Args:
            indicator_type: Type of indicator
            phase: Filter by phase (optional)
            maintenance_id: Filter by maintenance ID (optional)

        Returns:
            Latest IndicatorResult or None
        """
        stmt = (
            select(IndicatorResult)
            .where(IndicatorResult.indicator_type == indicator_type)
            .order_by(IndicatorResult.evaluated_at.desc())
            .limit(1)
        )

        if phase:
            stmt = stmt.where(IndicatorResult.phase == phase)
        if maintenance_id:
            stmt = stmt.where(
                IndicatorResult.maintenance_id == maintenance_id
            )

        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_timeseries(
        self,
        indicator_type: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[IndicatorResult]:
        """
        Get indicator results as time series.

        Args:
            indicator_type: Type of indicator
            start_time: Start of time range (optional)
            end_time: End of time range (optional)
            limit: Maximum records to return

        Returns:
            List of IndicatorResults ordered by time
        """
        stmt = (
            select(IndicatorResult)
            .where(IndicatorResult.indicator_type == indicator_type)
            .order_by(IndicatorResult.evaluated_at.asc())
            .limit(limit)
        )

        if start_time:
            stmt = stmt.where(IndicatorResult.evaluated_at >= start_time)
        if end_time:
            stmt = stmt.where(IndicatorResult.evaluated_at <= end_time)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_latest(
        self,
        maintenance_id: str | None = None,
    ) -> list[IndicatorResult]:
        """
        Get latest result for each indicator type.

        Args:
            maintenance_id: Filter by maintenance ID (optional)

        Returns:
            List of latest IndicatorResults (one per type)
        """
        from sqlalchemy import func

        # Subquery to get max evaluated_at per indicator_type
        subq = (
            select(
                IndicatorResult.indicator_type,
                func.max(IndicatorResult.evaluated_at).label("max_time"),
            )
            .group_by(IndicatorResult.indicator_type)
        )

        if maintenance_id:
            subq = subq.where(
                IndicatorResult.maintenance_id == maintenance_id
            )

        subq = subq.subquery()

        # Main query
        from sqlalchemy import and_

        stmt = select(IndicatorResult).join(
            subq,
            and_(
                IndicatorResult.indicator_type == subq.c.indicator_type,
                IndicatorResult.evaluated_at == subq.c.max_time,
            ),
        )

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def compare_phases(
        self,
        indicator_type: str,
        maintenance_id: str,
    ) -> dict[str, IndicatorResult | None]:
        """
        Get results for both PRE and POST phases.

        Args:
            indicator_type: Type of indicator
            maintenance_id: Maintenance job ID

        Returns:
            Dict with 'pre' and 'post' keys
        """
        pre_result = await self.get_latest_result(
            indicator_type=indicator_type,
            phase=MaintenancePhase.PRE,
            maintenance_id=maintenance_id,
        )
        post_result = await self.get_latest_result(
            indicator_type=indicator_type,
            phase=MaintenancePhase.POST,
            maintenance_id=maintenance_id,
        )

        return {
            "pre": pre_result,
            "post": post_result,
        }
