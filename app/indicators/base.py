"""
Indicator base classes and interfaces.

All indicator evaluators inherit from BaseIndicator.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MaintenancePhase


class ObservedField(BaseModel):
    """Observed field in an indicator."""
    name: str
    display_name: str
    metric_name: str | None = None
    unit: str | None = None


class DisplayConfig(BaseModel):
    """Display configuration for indicator charts."""
    chart_type: str
    x_axis_label: str | None = None
    y_axis_label: str | None = None
    y_axis_min: float | None = None
    y_axis_max: float | None = None
    line_colors: list[str] | None = None
    show_raw_data_table: bool = True
    refresh_interval_seconds: int = 60


class IndicatorMetadata(BaseModel):
    """Metadata describing an indicator."""
    name: str
    title: str
    description: str
    object_type: str
    data_type: str
    observed_fields: list[ObservedField]
    display_config: DisplayConfig


class TimeSeriesPoint(BaseModel):
    """A single point in a time series."""
    timestamp: datetime
    values: dict[str, float]


class RawDataRow(BaseModel):
    """Base class for raw data rows (subclasses define specific fields)."""
    model_config = {"extra": "allow"}


class IndicatorEvaluationResult(BaseModel):
    """Result of indicator evaluation."""

    indicator_type: str
    phase: MaintenancePhase
    maintenance_id: str

    # Statistics
    total_count: int
    pass_count: int
    fail_count: int

    # Pass rates for each metric
    pass_rates: dict[str, float]

    # Detailed failure information
    failures: list[dict[str, Any]] | None = None

    # Summary message
    summary: str | None = None

    @property
    def pass_rate_percent(self) -> float:
        """Overall pass rate percentage."""
        if self.total_count == 0:
            return 0.0
        return (self.pass_count / self.total_count) * 100


class BaseIndicator(ABC):
    """
    Abstract base class for all indicator evaluators.

    Each evaluator handles one type of indicator (transceiver, version, uplink).
    """

    indicator_type: str

    @abstractmethod
    async def evaluate(
        self,
        maintenance_id: str,
        session: Any,
        phase: MaintenancePhase = MaintenancePhase.NEW,
    ) -> IndicatorEvaluationResult:
        """
        Evaluate indicator for a maintenance operation.

        Args:
            maintenance_id: The maintenance operation ID
            session: Database session
            phase: Maintenance phase (OLD or NEW)

        Returns:
            IndicatorEvaluationResult: Evaluation result with statistics
        """
        ...

    @abstractmethod
    def get_metadata(self) -> IndicatorMetadata:
        """
        Get indicator metadata.

        Returns:
            IndicatorMetadata: Indicator configuration and display info
        """
        ...

    @abstractmethod
    async def get_time_series(
        self,
        limit: int,
        session: AsyncSession,
        maintenance_id: str,
        phase: MaintenancePhase = MaintenancePhase.NEW,
    ) -> list[TimeSeriesPoint]:
        """
        Get time series data for this indicator.

        Args:
            limit: Maximum number of data points to return
            session: Database session
            maintenance_id: Maintenance ID to query
            phase: Maintenance phase

        Returns:
            List of time series points
        """
        ...

    @abstractmethod
    async def get_latest_raw_data(
        self,
        limit: int,
        session: AsyncSession,
        maintenance_id: str,
        phase: MaintenancePhase = MaintenancePhase.NEW,
    ) -> list[RawDataRow]:
        """
        Get latest raw data records for this indicator.

        Args:
            limit: Maximum number of records to return
            session: Database session
            maintenance_id: Maintenance ID to query
            phase: Maintenance phase

        Returns:
            List of raw data rows
        """
        ...
