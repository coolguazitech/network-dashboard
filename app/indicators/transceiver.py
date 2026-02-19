"""
Transceiver (光模塊) indicator evaluator.

Uses TransceiverRecord with flat tx_power/rx_power/temperature/voltage fields.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
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
from app.repositories.typed_records import TransceiverRecordRepo
from app.services.threshold_service import get_threshold


@dataclass(frozen=True)
class _Thresholds:
    """Immutable snapshot of transceiver thresholds for a given maintenance."""
    tx_power_min: float
    tx_power_max: float
    rx_power_min: float
    rx_power_max: float
    temperature_min: float
    temperature_max: float
    voltage_min: float
    voltage_max: float


class TransceiverIndicator(BaseIndicator):
    """
    Transceiver 光模塊指標評估器。

    檢查每個光模塊的 Tx/Rx 功率、溫度、電壓是否在正常範圍內（雙向閾值）。
    閾值來源：DB 動態覆寫 → .env 預設值（透過 threshold_service.get_threshold()）。
    """

    indicator_type = "transceiver"

    @staticmethod
    def _load_thresholds(maintenance_id: str) -> _Thresholds:
        """Load all thresholds for a maintenance — no mutable state on self."""
        return _Thresholds(
            tx_power_min=get_threshold("transceiver_tx_power_min", maintenance_id),
            tx_power_max=get_threshold("transceiver_tx_power_max", maintenance_id),
            rx_power_min=get_threshold("transceiver_rx_power_min", maintenance_id),
            rx_power_max=get_threshold("transceiver_rx_power_max", maintenance_id),
            temperature_min=get_threshold("transceiver_temperature_min", maintenance_id),
            temperature_max=get_threshold("transceiver_temperature_max", maintenance_id),
            voltage_min=get_threshold("transceiver_voltage_min", maintenance_id),
            voltage_max=get_threshold("transceiver_voltage_max", maintenance_id),
        )

    # ── evaluate ────────────────────────────────────────────────

    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> IndicatorEvaluationResult:
        """評估光模塊指標。"""
        th = self._load_thresholds(maintenance_id)
        repo = TransceiverRecordRepo(session)
        records = await repo.get_latest_per_device(maintenance_id)

        total_count = 0
        pass_count = 0
        failures: list[dict[str, Any]] = []
        passes: list[dict[str, Any]] = []

        for record in records:
            total_count += 1
            failure = self._check_single_record(record, th)
            if failure is None:
                pass_count += 1
                if len(passes) < 10:
                    passes.append({
                        "device": record.switch_hostname,
                        "interface": record.interface_name,
                        "reason": "光模塊正常",
                        "data": self._record_data(record),
                    })
            else:
                failures.append(failure)

        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "tx_power_ok": self._field_pass_rate(
                    records, "tx_power",
                    th.tx_power_min, th.tx_power_max,
                ),
                "rx_power_ok": self._field_pass_rate(
                    records, "rx_power",
                    th.rx_power_min, th.rx_power_max,
                ),
                "temperature_ok": self._field_pass_rate(
                    records, "temperature",
                    th.temperature_min, th.temperature_max,
                ),
                "voltage_ok": self._field_pass_rate(
                    records, "voltage",
                    th.voltage_min, th.voltage_max,
                ),
            },
            failures=failures if failures else None,
            passes=passes if passes else None,
            summary=(
                f"光模塊驗收: {pass_count}/{total_count} 通過 "
                f"({self._calc_percent(pass_count, total_count):.1f}%)"
            ),
        )

    # ── single-record check ─────────────────────────────────────

    def _check_single_record(
        self, record: TransceiverRecord, th: _Thresholds,
    ) -> dict[str, Any] | None:
        """Check a single record. Return failure dict or None if passed."""
        if (
            record.tx_power is None
            and record.rx_power is None
            and record.temperature is None
            and record.voltage is None
        ):
            return {
                "device": record.switch_hostname,
                "interface": record.interface_name,
                "reason": "光模塊缺失或無法讀取",
                "data": self._record_data(record),
            }

        failure_reasons = self._collect_failure_reasons(record, th)
        if not failure_reasons:
            return None

        return {
            "device": record.switch_hostname,
            "interface": record.interface_name,
            "reason": " | ".join(failure_reasons),
            "data": self._record_data(record),
        }

    @staticmethod
    def _collect_failure_reasons(
        record: TransceiverRecord, th: _Thresholds,
    ) -> list[str]:
        """Return a list of human-readable failure reasons for *record*."""
        reasons: list[str] = []

        if record.tx_power is not None:
            if record.tx_power < th.tx_power_min:
                reasons.append(
                    f"Tx Power 過低: {record.tx_power} dBm "
                    f"(範圍: {th.tx_power_min}~{th.tx_power_max})"
                )
            elif record.tx_power > th.tx_power_max:
                reasons.append(
                    f"Tx Power 過高: {record.tx_power} dBm "
                    f"(範圍: {th.tx_power_min}~{th.tx_power_max})"
                )

        if record.rx_power is not None:
            if record.rx_power < th.rx_power_min:
                reasons.append(
                    f"Rx Power 過低: {record.rx_power} dBm "
                    f"(範圍: {th.rx_power_min}~{th.rx_power_max})"
                )
            elif record.rx_power > th.rx_power_max:
                reasons.append(
                    f"Rx Power 過高: {record.rx_power} dBm "
                    f"(範圍: {th.rx_power_min}~{th.rx_power_max})"
                )

        if record.temperature is not None:
            if record.temperature < th.temperature_min:
                reasons.append(
                    f"溫度過低: {record.temperature}°C "
                    f"(範圍: {th.temperature_min}~{th.temperature_max}°C)"
                )
            elif record.temperature > th.temperature_max:
                reasons.append(
                    f"溫度過高: {record.temperature}°C "
                    f"(範圍: {th.temperature_min}~{th.temperature_max}°C)"
                )

        if record.voltage is not None:
            if record.voltage < th.voltage_min:
                reasons.append(
                    f"電壓過低: {record.voltage}V "
                    f"(範圍: {th.voltage_min}~{th.voltage_max}V)"
                )
            elif record.voltage > th.voltage_max:
                reasons.append(
                    f"電壓過高: {record.voltage}V "
                    f"(範圍: {th.voltage_min}~{th.voltage_max}V)"
                )

        return reasons

    @staticmethod
    def _record_data(record: TransceiverRecord) -> dict[str, Any]:
        """Serialise key fields for failure/pass data payload."""
        return {
            "tx_power": record.tx_power,
            "rx_power": record.rx_power,
            "temperature": record.temperature,
            "voltage": record.voltage,
        }

    # ── pass-rate helpers ───────────────────────────────────────

    def _field_pass_rate(
        self,
        records: list[TransceiverRecord],
        field: str,
        min_threshold: float,
        max_threshold: float,
    ) -> float:
        """Calculate pass rate for a record-level field."""
        total = 0
        passed = 0
        for record in records:
            value = getattr(record, field)
            if value is None:
                continue
            total += 1
            if min_threshold <= value <= max_threshold:
                passed += 1
        return self._calc_percent(passed, total)

    @staticmethod
    def _calc_percent(passed: int, total: int) -> float:
        return (passed / total * 100) if total > 0 else 0.0

    # ── metadata ────────────────────────────────────────────────

    def get_metadata(self) -> IndicatorMetadata:
        """獲取指標元數據。"""
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
    ) -> list[TimeSeriesPoint]:
        """獲取時間序列數據。"""
        repo = TransceiverRecordRepo(session)
        records = await repo.get_time_series_records(maintenance_id, limit)

        grouped: dict[datetime, list[TransceiverRecord]] = defaultdict(list)
        for record in records:
            grouped[record.collected_at].append(record)

        time_series: list[TimeSeriesPoint] = []
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
        buckets: dict[str, list[float]] = {
            "tx_power": [],
            "rx_power": [],
            "temperature": [],
            "voltage": [],
        }

        for record in group:
            if record.tx_power is not None:
                buckets["tx_power"].append(record.tx_power)
            if record.rx_power is not None:
                buckets["rx_power"].append(record.rx_power)
            if record.temperature is not None:
                buckets["temperature"].append(record.temperature)
            if record.voltage is not None:
                buckets["voltage"].append(record.voltage)

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
    ) -> list[RawDataRow]:
        """獲取最新原始數據。"""
        th = self._load_thresholds(maintenance_id)
        repo = TransceiverRecordRepo(session)
        records = await repo.get_latest_records(maintenance_id, limit)

        return [
            RawDataRow(
                switch_hostname=record.switch_hostname,
                interface_name=record.interface_name,
                tx_power=record.tx_power,
                rx_power=record.rx_power,
                temperature=record.temperature,
                voltage=record.voltage,
                tx_pass=(
                    th.tx_power_min <= record.tx_power <= th.tx_power_max
                    if record.tx_power is not None
                    else None
                ),
                rx_pass=(
                    th.rx_power_min <= record.rx_power <= th.rx_power_max
                    if record.rx_power is not None
                    else None
                ),
                collected_at=record.collected_at,
            )
            for record in records
        ]
