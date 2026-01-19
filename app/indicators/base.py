"""
Indicator base classes and interfaces.

All indicator evaluators inherit from BaseIndicator.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel

from app.core.enums import MaintenancePhase


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
    ) -> IndicatorEvaluationResult:
        """
        Evaluate indicator for a maintenance operation.

        Args:
            maintenance_id: The maintenance operation ID
            session: Database session

        Returns:
            IndicatorEvaluationResult: Evaluation result with statistics
        """
        ...
