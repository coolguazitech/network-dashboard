"""
Transceiver (光模塊) indicator evaluator.

Evaluates if transceiver data meets expectations (bilateral thresholds).
Uses typed TransceiverRecord table via TransceiverRecordRepo.
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
from app.repositories.typed_records import TransceiverRecordRepo
from app.services.threshold_service import get_threshold

# Fields to aggregate when computing time-series averages.
_METRIC_FIELDS = ("tx_power", "rx_power", "temperature", "voltage")


class TransceiverIndicator(BaseIndicator):
    """
    Transceiver 光模塊指標評估器。

    檢查每個光模塊的 Tx/Rx 功率、溫度、電壓是否在正常範圍內（雙向閾值）。
    閾值來源：DB 動態覆寫 → .env 預設值（透過 threshold_service.get_threshold()）。
    """

    indicator_type = "transceiver"

    # 當前評估中的歲修 ID（由 evaluate / get_time_series / get_latest_raw_data 設定）
    _maintenance_id: str | None = None

    # 光模塊閾值：優先讀 DB 覆寫，fallback 到 .env（見 threshold_service.py）
    @property
    def TX_POWER_MIN(self) -> float:
        return get_threshold("transceiver_tx_power_min", self._maintenance_id)

    @property
    def TX_POWER_MAX(self) -> float:
        return get_threshold("transceiver_tx_power_max", self._maintenance_id)

    @property
    def RX_POWER_MIN(self) -> float:
        return get_threshold("transceiver_rx_power_min", self._maintenance_id)

    @property
    def RX_POWER_MAX(self) -> float:
        return get_threshold("transceiver_rx_power_max", self._maintenance_id)

    @property
    def TEMPERATURE_MIN(self) -> float:
        return get_threshold("transceiver_temperature_min", self._maintenance_id)

    @property
    def TEMPERATURE_MAX(self) -> float:
        return get_threshold("transceiver_temperature_max", self._maintenance_id)

    @property
    def VOLTAGE_MIN(self) -> float:
        return get_threshold("transceiver_voltage_min", self._maintenance_id)

    @property
    def VOLTAGE_MAX(self) -> float:
        return get_threshold("transceiver_voltage_max", self._maintenance_id)

    # ── evaluate ────────────────────────────────────────────────

    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> IndicatorEvaluationResult:
        """
        評估光模塊指標。

        Args:
            maintenance_id: 維護作業 ID
            session: 資料庫 session
        """
        self._maintenance_id = maintenance_id
        repo = TransceiverRecordRepo(session)
        records = await repo.get_latest_per_device(maintenance_id)

        total_count = 0
        pass_count = 0
        failures: list[dict[str, Any]] = []
        passes: list[dict[str, Any]] = []

        for record in records:
            total_count += 1
            failure = self._check_single_record(record)
            if failure is None:
                pass_count += 1
                if len(passes) < 10:
                    passes.append({
                        "device": record.switch_hostname,
                        "interface": record.interface_name,
                        "reason": "光模塊正常",
                        "data": {
                            "tx_power": record.tx_power,
                            "rx_power": record.rx_power,
                            "temperature": record.temperature,
                            "voltage": record.voltage,
                        },
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
                "tx_power_ok": self._calculate_pass_rate(
                    records, "tx_power",
                    self.TX_POWER_MIN, self.TX_POWER_MAX,
                ),
                "rx_power_ok": self._calculate_pass_rate(
                    records, "rx_power",
                    self.RX_POWER_MIN, self.RX_POWER_MAX,
                ),
                "temperature_ok": self._calculate_pass_rate(
                    records, "temperature",
                    self.TEMPERATURE_MIN, self.TEMPERATURE_MAX,
                ),
                "voltage_ok": self._calculate_pass_rate(
                    records, "voltage",
                    self.VOLTAGE_MIN, self.VOLTAGE_MAX,
                ),
            },
            failures=failures if failures else None,
            passes=passes if passes else None,
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

        if record.tx_power is not None:
            if record.tx_power < self.TX_POWER_MIN:
                reasons.append(
                    f"Tx Power 過低: {record.tx_power} dBm "
                    f"(範圍: {self.TX_POWER_MIN}~{self.TX_POWER_MAX})"
                )
            elif record.tx_power > self.TX_POWER_MAX:
                reasons.append(
                    f"Tx Power 過高: {record.tx_power} dBm "
                    f"(範圍: {self.TX_POWER_MIN}~{self.TX_POWER_MAX})"
                )

        if record.rx_power is not None:
            if record.rx_power < self.RX_POWER_MIN:
                reasons.append(
                    f"Rx Power 過低: {record.rx_power} dBm "
                    f"(範圍: {self.RX_POWER_MIN}~{self.RX_POWER_MAX})"
                )
            elif record.rx_power > self.RX_POWER_MAX:
                reasons.append(
                    f"Rx Power 過高: {record.rx_power} dBm "
                    f"(範圍: {self.RX_POWER_MIN}~{self.RX_POWER_MAX})"
                )

        if record.temperature is not None:
            if record.temperature < self.TEMPERATURE_MIN:
                reasons.append(
                    f"溫度過低: {record.temperature}°C "
                    f"(範圍: {self.TEMPERATURE_MIN}~{self.TEMPERATURE_MAX}°C)"
                )
            elif record.temperature > self.TEMPERATURE_MAX:
                reasons.append(
                    f"溫度過高: {record.temperature}°C "
                    f"(範圍: {self.TEMPERATURE_MIN}~{self.TEMPERATURE_MAX}°C)"
                )

        if record.voltage is not None:
            if record.voltage < self.VOLTAGE_MIN:
                reasons.append(
                    f"電壓過低: {record.voltage}V "
                    f"(範圍: {self.VOLTAGE_MIN}~{self.VOLTAGE_MAX}V)"
                )
            elif record.voltage > self.VOLTAGE_MAX:
                reasons.append(
                    f"電壓過高: {record.voltage}V "
                    f"(範圍: {self.VOLTAGE_MIN}~{self.VOLTAGE_MAX}V)"
                )

        return reasons

    # ── pass-rate helpers ───────────────────────────────────────

    def _calculate_pass_rate(
        self,
        records: list[TransceiverRecord],
        field: str,
        min_threshold: float,
        max_threshold: float,
    ) -> float:
        """計算特定字段的通過率（雙向閾值）。"""
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
        self._maintenance_id = maintenance_id
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
    ) -> list[RawDataRow]:
        """獲取最新原始數據。"""
        self._maintenance_id = maintenance_id
        repo = TransceiverRecordRepo(session)
        records = await repo.get_latest_records(maintenance_id, limit)

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
                self.TX_POWER_MIN <= record.tx_power <= self.TX_POWER_MAX
                if record.tx_power is not None
                else None
            ),
            rx_pass=(
                self.RX_POWER_MIN <= record.rx_power <= self.RX_POWER_MAX
                if record.rx_power is not None
                else None
            ),
            collected_at=record.collected_at,
        )
