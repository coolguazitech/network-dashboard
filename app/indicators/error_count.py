"""
Interface Error Count indicator evaluator.

Evaluates if interfaces have any errors.
Uses typed record table (InterfaceErrorRecord) instead of CollectionRecord JSON.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MaintenancePhase
from app.db.models import InterfaceErrorRecord
from app.indicators.base import (
    BaseIndicator,
    DisplayConfig,
    IndicatorEvaluationResult,
    IndicatorMetadata,
    ObservedField,
    RawDataRow,
    TimeSeriesPoint,
)
from app.repositories.typed_records import InterfaceErrorRecordRepo


class ErrorCountIndicator(BaseIndicator):
    """
    Error Count 指標評估器。

    檢查項目：
    1. 介面是否有 CRC 錯誤
    2. 介面是否有 Input/Output 錯誤
    """

    indicator_type = "error_count"

    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
        phase: MaintenancePhase | None = None,
    ) -> IndicatorEvaluationResult:
        """
        評估錯誤計數指標。

        Args:
            maintenance_id: 維護作業 ID
            session: 資料庫 session
            phase: 階段 (OLD 或 NEW)，預設 NEW
        """
        if phase is None:
            phase = MaintenancePhase.NEW

        repo = InterfaceErrorRecordRepo(session)
        records = await repo.get_latest_per_device(phase, maintenance_id)

        total_count = 0
        pass_count = 0
        failures = []

        for record in records:
            total_count += 1

            errors = []
            if record.crc_errors > 0:
                errors.append(f"CRC: {record.crc_errors}")
            if record.input_errors > 0:
                errors.append(f"In: {record.input_errors}")
            if record.output_errors > 0:
                errors.append(f"Out: {record.output_errors}")

            if not errors:
                pass_count += 1
            else:
                failures.append({
                    "device": record.switch_hostname,
                    "interface": record.interface_name,
                    "reason": ", ".join(errors),
                    "data": {
                        "interface_name": record.interface_name,
                        "crc_errors": record.crc_errors,
                        "input_errors": record.input_errors,
                        "output_errors": record.output_errors,
                    },
                })

        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            phase=phase,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "error_free": self._calc_percent(pass_count, total_count)
            },
            failures=failures if failures else None,
            summary=f"錯誤計數: {pass_count}/{total_count} 介面無錯誤"
        )

    @staticmethod
    def _calc_percent(passed: int, total: int) -> float:
        return (passed / total * 100) if total > 0 else 0.0

    def get_metadata(self) -> IndicatorMetadata:
        """獲取指標元數據。"""
        return IndicatorMetadata(
            name="error_count",
            title="Interface CRC Error 監控",
            description="監控介面 CRC 錯誤計數",
            object_type="interface",
            data_type="integer",
            observed_fields=[
                ObservedField(
                    name="crc_errors",
                    display_name="CRC Errors",
                    metric_name="crc_errors",
                    unit=None,
                ),
                ObservedField(
                    name="input_errors",
                    display_name="Input Errors",
                    metric_name="input_errors",
                    unit=None,
                ),
            ],
            display_config=DisplayConfig(
                chart_type="line",
                x_axis_label="Time",
                y_axis_label="Error Count",
                show_raw_data_table=True,
                refresh_interval_seconds=300,
            ),
        )

    async def get_time_series(
        self,
        limit: int,
        session: AsyncSession,
        maintenance_id: str,
        phase: MaintenancePhase = MaintenancePhase.NEW,
    ) -> list[TimeSeriesPoint]:
        """獲取時間序列數據。"""
        repo = InterfaceErrorRecordRepo(session)
        records = await repo.get_time_series_records(
            maintenance_id=maintenance_id,
            phase=phase,
            limit=limit,
        )

        # Group records by collected_at timestamp, sum errors across interfaces
        ts_map: dict[str, dict] = defaultdict(
            lambda: {"timestamp": None, "crc_errors": 0, "input_errors": 0}
        )
        for record in records:
            key = record.collected_at.isoformat()
            entry = ts_map[key]
            entry["timestamp"] = record.collected_at
            entry["crc_errors"] += record.crc_errors
            entry["input_errors"] += record.input_errors

        # Sort by timestamp ascending
        time_series = [
            TimeSeriesPoint(
                timestamp=entry["timestamp"],
                values={
                    "crc_errors": float(entry["crc_errors"]),
                    "input_errors": float(entry["input_errors"]),
                },
            )
            for entry in sorted(ts_map.values(), key=lambda e: e["timestamp"])
        ]

        return time_series

    async def get_latest_raw_data(
        self,
        limit: int,
        session: AsyncSession,
        maintenance_id: str,
        phase: MaintenancePhase = MaintenancePhase.NEW,
    ) -> list[RawDataRow]:
        """獲取最新原始數據。"""
        repo = InterfaceErrorRecordRepo(session)
        records = await repo.get_latest_records(
            maintenance_id=maintenance_id,
            phase=phase,
            limit=limit,
        )

        raw_data = []
        for record in records:
            raw_data.append(
                RawDataRow(
                    switch_hostname=record.switch_hostname,
                    interface_name=record.interface_name,
                    crc_errors=record.crc_errors,
                    input_errors=record.input_errors,
                    output_errors=record.output_errors,
                    collected_at=record.collected_at,
                )
            )

        return raw_data
