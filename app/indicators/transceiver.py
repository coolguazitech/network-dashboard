"""
Transceiver (光模塊) indicator evaluator.

Evaluates if NEW phase transceiver data meets expectations.
Uses typed TransceiverRecord table instead of CollectionRecord JSON blobs.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TransceiverRecord
from app.indicators.base import (
    BaseIndicator,
    DisplayConfig,
    IndicatorEvaluationResult,
    IndicatorMetadata,
    ObservedField,
    RawDataRow,
    TimeSeriesPoint,
)
from app.core.enums import MaintenancePhase
from app.repositories.typed_records import TransceiverRecordRepo

# Fields to aggregate when computing time-series averages.
_METRIC_FIELDS = ("tx_power", "rx_power", "temperature", "voltage")


class TransceiverIndicator(BaseIndicator):
    """
    Transceiver 光模塊指標評估器。

    檢查 NEW phase 中每個光模塊的 Tx/Rx 功率是否在正常範圍內。
    """

    indicator_type = "transceiver"

    # 光模塊預期值閾值
    TX_POWER_MIN = -12.0  # dBm
    RX_POWER_MIN = -18.0  # dBm
    TEMPERATURE_MAX = 60.0  # °C
    VOLTAGE_MIN = 3.2  # V

    # ── evaluate ────────────────────────────────────────────────

    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
        phase: MaintenancePhase | None = None,
    ) -> IndicatorEvaluationResult:
        """
        評估光模塊指標。

        Args:
            maintenance_id: 維護作業 ID
            session: 資料庫 session
            phase: 階段 (OLD 或 NEW)，如果為 None 則默認 NEW
        """
        if phase is None:
            phase = MaintenancePhase.NEW

        repo = TransceiverRecordRepo(session)
        records = await repo.get_latest_per_device(phase, maintenance_id)

        total_count = 0
        pass_count = 0
        failures: list[dict[str, Any]] = []

        for record in records:
            total_count += 1
            failure = self._check_single_record(record)
            if failure is None:
                pass_count += 1
            else:
                failures.append(failure)

        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            phase=phase,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "tx_power_ok": self._calculate_pass_rate(
                    records, "tx_power", self.TX_POWER_MIN
                ),
                "rx_power_ok": self._calculate_pass_rate(
                    records, "rx_power", self.RX_POWER_MIN
                ),
                "temperature_ok": self._calculate_pass_rate(
                    records, "temperature", None, self.TEMPERATURE_MAX
                ),
            },
            failures=failures if failures else None,
            summary=f"光模塊驗收: {pass_count}/{total_count} 通過 "
                   f"({self._calc_percent(pass_count, total_count):.1f}%)"
        )

    def _check_single_record(
        self, record: TransceiverRecord
    ) -> dict[str, Any] | None:
        """
        Check a single transceiver record against thresholds.

        Returns:
            A failure dict if the record fails any check, or None if it passes.
        """
        # 如果 tx_power 和 rx_power 都是 None，判定為光模塊缺失
        if record.tx_power is None and record.rx_power is None:
            return {
                "device": record.switch_hostname,
                "interface": record.interface_name,
                "reason": "光模塊缺失或無法讀取",
                "data": {
                    "tx_power": None,
                    "rx_power": None,
                    "temperature": None,
                    "voltage": None,
                },
            }

        failure_reasons = self._collect_failure_reasons(record)

        if not failure_reasons:
            return None

        return {
            "device": record.switch_hostname,
            "interface": record.interface_name,
            "reason": " | ".join(failure_reasons),
            "data": {
                "tx_power": record.tx_power,
                "rx_power": record.rx_power,
                "temperature": record.temperature,
                "voltage": record.voltage,
            },
        }

    def _collect_failure_reasons(
        self, record: TransceiverRecord
    ) -> list[str]:
        """Return a list of human-readable failure reasons for *record*."""
        reasons: list[str] = []

        if record.tx_power is not None and record.tx_power < self.TX_POWER_MIN:
            reasons.append(
                f"Tx Power低: {record.tx_power} dBm (預期: > {self.TX_POWER_MIN})"
            )
        if record.rx_power is not None and record.rx_power < self.RX_POWER_MIN:
            reasons.append(
                f"Rx Power低: {record.rx_power} dBm (預期: > {self.RX_POWER_MIN})"
            )
        if record.temperature is not None and record.temperature > self.TEMPERATURE_MAX:
            reasons.append(
                f"溫度高: {record.temperature}°C (預期: < {self.TEMPERATURE_MAX}°C)"
            )
        if record.voltage is not None and record.voltage < self.VOLTAGE_MIN:
            reasons.append(
                f"電壓低: {record.voltage}V (預期: > {self.VOLTAGE_MIN}V)"
            )

        return reasons

    # ── pass-rate helpers ───────────────────────────────────────

    def _calculate_pass_rate(
        self,
        records: list[TransceiverRecord],
        field: str,
        min_threshold: float | None = None,
        max_threshold: float | None = None,
    ) -> float:
        """計算特定字段的通過率。"""
        total = 0
        passed = 0

        for record in records:
            value = getattr(record, field)
            if value is None:
                continue

            total += 1
            if self._value_passes_threshold(value, min_threshold, max_threshold):
                passed += 1

        return self._calc_percent(passed, total)

    @staticmethod
    def _value_passes_threshold(
        value: float,
        min_threshold: float | None,
        max_threshold: float | None,
    ) -> bool:
        """Return True when *value* satisfies the given threshold(s)."""
        if min_threshold is not None:
            return value >= min_threshold
        if max_threshold is not None:
            return value <= max_threshold
        return True

    @staticmethod
    def _calc_percent(passed: int, total: int) -> float:
        """計算百分比。"""
        return (passed / total * 100) if total > 0 else 0.0

    # ── metadata ────────────────────────────────────────────────

    def get_metadata(self) -> IndicatorMetadata:
        """獲取指標元數據（從 indicators.yaml 配置）。"""
        return IndicatorMetadata(
            name="transceiver",
            title="光模組 Tx/Rx 功率監控",
            description="監控光模組的發射/接收功率是否在正常範圍",
            object_type="interface",
            data_type="float",
            observed_fields=[
                ObservedField(
                    name="tx_power",
                    display_name="Tx Power",
                    metric_name="tx_power",
                    unit="dBm",
                ),
                ObservedField(
                    name="rx_power",
                    display_name="Rx Power",
                    metric_name="rx_power",
                    unit="dBm",
                ),
                ObservedField(
                    name="temperature",
                    display_name="Temperature",
                    metric_name="temperature",
                    unit="°C",
                ),
                ObservedField(
                    name="voltage",
                    display_name="Voltage",
                    metric_name="voltage",
                    unit="V",
                ),
            ],
            display_config=DisplayConfig(
                chart_type="line",
                x_axis_label="Time",
                y_axis_label="Power (dBm)",
                y_axis_min=-20.0,
                y_axis_max=5.0,
                line_colors=["#4CAF50", "#2196F3", "#FF9800", "#F44336"],
                show_raw_data_table=True,
                refresh_interval_seconds=300,
            ),
        )

    # ── time series ─────────────────────────────────────────────

    async def get_time_series(
        self,
        limit: int,
        session: AsyncSession,
        maintenance_id: str,
        phase: MaintenancePhase = MaintenancePhase.NEW,
    ) -> list[TimeSeriesPoint]:
        """獲取時間序列數據。"""
        repo = TransceiverRecordRepo(session)
        records = await repo.get_time_series_records(maintenance_id, phase, limit)

        # Group records by collected_at to aggregate averages per timestamp
        grouped: dict[datetime, list[TransceiverRecord]] = defaultdict(list)
        for record in records:
            grouped[record.collected_at].append(record)

        time_series: list[TimeSeriesPoint] = []

        # Iterate in chronological order (records come desc, so sort the keys)
        for timestamp in sorted(grouped.keys()):
            values = self._aggregate_group_averages(grouped[timestamp])
            if values:
                time_series.append(
                    TimeSeriesPoint(timestamp=timestamp, values=values)
                )

        return time_series

    @staticmethod
    def _aggregate_group_averages(
        group: list[TransceiverRecord],
    ) -> dict[str, float]:
        """Compute per-field averages for a group of records sharing a timestamp."""
        buckets: dict[str, list[float]] = {f: [] for f in _METRIC_FIELDS}

        for record in group:
            for field in _METRIC_FIELDS:
                value = getattr(record, field)
                if value is not None:
                    buckets[field].append(value)

        return {
            field: sum(vals) / len(vals)
            for field, vals in buckets.items()
            if vals
        }

    # ── raw data ────────────────────────────────────────────────

    async def get_latest_raw_data(
        self,
        limit: int,
        session: AsyncSession,
        maintenance_id: str,
        phase: MaintenancePhase = MaintenancePhase.NEW,
    ) -> list[RawDataRow]:
        """獲取最新原始數據。"""
        repo = TransceiverRecordRepo(session)
        records = await repo.get_latest_records(maintenance_id, phase, limit)

        return [self._record_to_raw_row(record) for record in records]

    def _record_to_raw_row(self, record: TransceiverRecord) -> RawDataRow:
        """Convert a single TransceiverRecord to a RawDataRow."""
        return RawDataRow(
            switch_hostname=record.switch_hostname,
            interface_name=record.interface_name,
            tx_power=record.tx_power,
            rx_power=record.rx_power,
            temperature=record.temperature,
            voltage=record.voltage,
            tx_pass=(
                record.tx_power >= self.TX_POWER_MIN
                if record.tx_power is not None
                else None
            ),
            rx_pass=(
                record.rx_power >= self.RX_POWER_MIN
                if record.rx_power is not None
                else None
            ),
            collected_at=record.collected_at,
        )
