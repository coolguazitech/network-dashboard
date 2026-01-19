"""
Metric system for evaluating indicator values.

Metrics convert raw values to scores (0.0 to 1.0) and determine pass/fail.
Follows Open-Closed Principle: add new metrics without modifying existing ones.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, Type, TypeVar, Union

from pydantic import BaseModel, Field

from app.core.enums import MetricType

T = TypeVar("T")


class MetricConfig(BaseModel):
    """Base configuration for all metrics."""

    metric_type: MetricType
    pass_threshold: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Score threshold to pass (0.0-1.0)",
    )
    description: str = ""


class RangeMetricConfig(MetricConfig):
    """Configuration for range-based metric."""

    metric_type: MetricType = MetricType.RANGE
    min_value: float = Field(description="Minimum acceptable value")
    max_value: float = Field(description="Maximum acceptable value")
    optimal_min: float | None = Field(
        default=None,
        description="Optimal range minimum (for scoring)",
    )
    optimal_max: float | None = Field(
        default=None,
        description="Optimal range maximum (for scoring)",
    )


class ThresholdMetricConfig(MetricConfig):
    """Configuration for threshold-based metric."""

    metric_type: MetricType = MetricType.THRESHOLD
    threshold: float = Field(description="Threshold value")
    is_upper_limit: bool = Field(
        default=True,
        description="True if value should be below threshold",
    )


class EqualsMetricConfig(MetricConfig):
    """Configuration for string equality metric."""

    metric_type: MetricType = MetricType.EQUALS
    expected_value: str = Field(description="Expected value to match")
    case_sensitive: bool = Field(default=False)


class BooleanMetricConfig(MetricConfig):
    """Configuration for boolean metric."""

    metric_type: MetricType = MetricType.BOOLEAN
    true_values: list[str] = Field(
        default=["ok", "normal", "up", "true", "yes", "1"],
        description="Values considered as True",
    )


class MappingMetricConfig(MetricConfig):
    """Configuration for mapping-based comparison metric."""

    metric_type: MetricType = MetricType.MAPPING
    mapping_field: str = Field(
        description="Field name in device mapping config",
    )


class MetricResult(BaseModel):
    """Result of metric evaluation."""

    score: float = Field(ge=0.0, le=1.0, description="Score 0.0-1.0")
    passed: bool = Field(description="Whether the value passed")
    raw_value: Any = Field(description="Original raw value")
    message: str = Field(default="", description="Optional message")


class BaseMetric(ABC, Generic[T]):
    """
    Abstract base class for all metrics.

    Implements Strategy Pattern: each metric type is a different strategy.
    """

    def __init__(self, config: MetricConfig) -> None:
        self.config = config

    @abstractmethod
    def calculate_score(self, value: T) -> float:
        """
        Calculate score from raw value.

        Args:
            value: Raw value to evaluate

        Returns:
            float: Score between 0.0 and 1.0
        """
        ...

    def evaluate(self, value: T) -> MetricResult:
        """
        Evaluate a value and return result.

        Args:
            value: Raw value to evaluate

        Returns:
            MetricResult: Evaluation result with score and pass status
        """
        score = self.calculate_score(value)
        passed = score >= self.config.pass_threshold
        return MetricResult(
            score=score,
            passed=passed,
            raw_value=value,
        )


class RangeMetric(BaseMetric[float]):
    """
    Metric for evaluating numeric values within a range.

    Score calculation:
    - 1.0 if value is in optimal range
    - Decreases linearly as value approaches min/max boundaries
    - 0.0 if value is outside min/max
    """

    def __init__(self, config: RangeMetricConfig) -> None:
        super().__init__(config)
        self.config: RangeMetricConfig = config

    def calculate_score(self, value: float) -> float:
        """Calculate score based on position within range."""
        if value < self.config.min_value or value > self.config.max_value:
            return 0.0

        # If optimal range is defined
        opt_min = self.config.optimal_min or self.config.min_value
        opt_max = self.config.optimal_max or self.config.max_value

        if opt_min <= value <= opt_max:
            return 1.0

        # Linear interpolation for values outside optimal but inside range
        if value < opt_min:
            range_size = opt_min - self.config.min_value
            if range_size == 0:
                return 1.0
            return (value - self.config.min_value) / range_size

        # value > opt_max
        range_size = self.config.max_value - opt_max
        if range_size == 0:
            return 1.0
        return (self.config.max_value - value) / range_size


class ThresholdMetric(BaseMetric[float]):
    """
    Metric for evaluating numeric values against a threshold.

    Score calculation:
    - 1.0 if value is on the correct side of threshold
    - Decreases as value exceeds threshold
    """

    def __init__(self, config: ThresholdMetricConfig) -> None:
        super().__init__(config)
        self.config: ThresholdMetricConfig = config

    def calculate_score(self, value: float) -> float:
        """Calculate score based on threshold comparison."""
        threshold = self.config.threshold

        if self.config.is_upper_limit:
            # Value should be below threshold
            if value <= threshold:
                return 1.0
            # Score decreases as value exceeds threshold
            excess = value - threshold
            return max(0.0, 1.0 - (excess / threshold) if threshold else 0.0)
        else:
            # Value should be above threshold
            if value >= threshold:
                return 1.0
            if threshold == 0:
                return 0.0
            return max(0.0, value / threshold)


class EqualsMetric(BaseMetric[str]):
    """
    Metric for string equality comparison.

    Perfect for version checking (e.g., firmware upgrade verification).
    """

    def __init__(self, config: EqualsMetricConfig) -> None:
        super().__init__(config)
        self.config: EqualsMetricConfig = config

    def calculate_score(self, value: str) -> float:
        """Calculate score based on string equality."""
        expected = self.config.expected_value
        actual = value

        if not self.config.case_sensitive:
            expected = expected.lower()
            actual = actual.lower()

        return 1.0 if expected == actual else 0.0


class BooleanMetric(BaseMetric[str | bool]):
    """
    Metric for boolean/status values.

    Converts string status to boolean based on configured true_values.
    """

    def __init__(self, config: BooleanMetricConfig) -> None:
        super().__init__(config)
        self.config: BooleanMetricConfig = config

    def calculate_score(self, value: str | bool) -> float:
        """Calculate score based on boolean evaluation."""
        if isinstance(value, bool):
            return 1.0 if value else 0.0

        value_lower = str(value).lower().strip()
        true_values_lower = [v.lower() for v in self.config.true_values]
        return 1.0 if value_lower in true_values_lower else 0.0


# Factory for creating metrics from config
class MetricFactory:
    """
    Factory for creating metric instances from configuration.

    Follows Factory Pattern and Open-Closed Principle.
    """

    _metric_classes: dict[MetricType, type[BaseMetric[Any]]] = {
        MetricType.RANGE: RangeMetric,
        MetricType.THRESHOLD: ThresholdMetric,
        MetricType.EQUALS: EqualsMetric,
        MetricType.BOOLEAN: BooleanMetric,
    }

    @classmethod
    def register(
        cls,
        metric_type: MetricType,
        metric_class: type[BaseMetric[Any]],
    ) -> None:
        """Register a new metric type (for extensibility)."""
        cls._metric_classes[metric_type] = metric_class

    @classmethod
    def create(cls, config: MetricConfig) -> BaseMetric[Any]:
        """
        Create a metric instance from configuration.

        Args:
            config: Metric configuration

        Returns:
            BaseMetric: Metric instance

        Raises:
            ValueError: If metric type is not supported
        """
        metric_class = cls._metric_classes.get(config.metric_type)
        if metric_class is None:
            raise ValueError(
                f"Unsupported metric type: {config.metric_type}"
            )
        return metric_class(config)  # type: ignore
