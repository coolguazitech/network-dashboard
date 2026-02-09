"""
Interface Error Count indicator evaluator.

兩階段閾值（依 MaintenanceDeviceList.is_replaced 欄位判斷）：
- 換設備（is_replaced=True）→ error 必須為 0（新設備應已清空計數器）
- 未換設備（is_replaced=False）→ error <= ERROR_COUNT_SAME_DEVICE_MAX
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InterfaceErrorRecord, MaintenanceDeviceList
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
from app.services.threshold_service import get_threshold


class ErrorCountIndicator(BaseIndicator):
    """
    Error Count 指標評估器。

    檢查項目（依 MaintenanceDeviceList.is_replaced 判斷，不以 hostname 推斷）：
    1. 換設備（is_replaced=True）→ CRC/Input/Output 必須全為 0
    2. 未換設備（is_replaced=False）→ 各項 <= 容許閾值（ERROR_COUNT_SAME_DEVICE_MAX）

    閾值來源：DB 動態覆寫 → .env 預設值（透過 threshold_service.get_threshold()）。
    """

    indicator_type = "error_count"

    # 當前評估中的歲修 ID
    _maintenance_id: str | None = None

    @property
    def SAME_DEVICE_MAX(self) -> int:
        return get_threshold("error_count_same_device_max", self._maintenance_id)

    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> IndicatorEvaluationResult:
        """評估錯誤計數指標。"""
        self._maintenance_id = maintenance_id
        # 1. 載入設備清單，判斷哪些 hostname 是換過的設備（依 is_replaced 欄位）
        replaced_hostnames = await self._get_replaced_devices(
            session, maintenance_id
        )

        # 2. 取最新採集
        repo = InterfaceErrorRecordRepo(session)
        records = await repo.get_latest_per_device(maintenance_id)

        total_count = 0
        pass_count = 0
        failures = []
        passes = []

        for record in records:
            total_count += 1
            is_replaced = record.switch_hostname in replaced_hostnames
            threshold = 0 if is_replaced else self.SAME_DEVICE_MAX

            errors = self._check_record(record, threshold)

            if not errors:
                pass_count += 1
                if len(passes) < 10:
                    passes.append({
                        "device": record.switch_hostname,
                        "interface": record.interface_name,
                        "reason": "無錯誤" if is_replaced else f"錯誤數在容許範圍 (<= {threshold})",
                        "data": {
                            "crc_errors": record.crc_errors,
                            "input_errors": record.input_errors,
                            "output_errors": record.output_errors,
                        },
                    })
            else:
                label = "換新設備，必須為 0" if is_replaced else f"閾值: {threshold}"
                failures.append({
                    "device": record.switch_hostname,
                    "interface": record.interface_name,
                    "reason": f"{', '.join(errors)} ({label})",
                    "data": {
                        "crc_errors": record.crc_errors,
                        "input_errors": record.input_errors,
                        "output_errors": record.output_errors,
                    },
                })

        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "error_free": self._calc_percent(pass_count, total_count)
            },
            failures=failures if failures else None,
            passes=passes if passes else None,
            summary=f"錯誤計數: {pass_count}/{total_count} 介面通過"
        )

    @staticmethod
    def _check_record(
        record: InterfaceErrorRecord, threshold: int
    ) -> list[str]:
        """檢查單筆記錄，回傳超標項目的描述列表。"""
        errors = []
        if record.crc_errors > threshold:
            errors.append(f"CRC: {record.crc_errors}")
        if record.input_errors > threshold:
            errors.append(f"In: {record.input_errors}")
        if record.output_errors > threshold:
            errors.append(f"Out: {record.output_errors}")
        return errors

    @staticmethod
    async def _get_replaced_devices(
        session: AsyncSession, maintenance_id: str
    ) -> set[str]:
        """回傳有換設備的 new_hostname 集合（依 is_replaced 欄位判斷）。"""
        stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        devices = result.scalars().all()
        return {
            d.new_hostname
            for d in devices
            if d.is_replaced
        }

    @staticmethod
    def _calc_percent(passed: int, total: int) -> float:
        return (passed / total * 100) if total > 0 else 0.0

    def get_metadata(self) -> IndicatorMetadata:
        """獲取指標元數據。"""
        return IndicatorMetadata(
            name="error_count",
            title="Interface Error 監控",
            description="監控介面 CRC / Input / Output 錯誤計數",
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
                ObservedField(
                    name="output_errors",
                    display_name="Output Errors",
                    metric_name="output_errors",
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
    ) -> list[TimeSeriesPoint]:
        """獲取時間序列數據。"""
        repo = InterfaceErrorRecordRepo(session)
        records = await repo.get_time_series_records(
            maintenance_id=maintenance_id,
            limit=limit,
        )

        ts_map: dict[str, dict] = defaultdict(
            lambda: {"timestamp": None, "crc_errors": 0, "input_errors": 0}
        )
        for record in records:
            key = record.collected_at.isoformat()
            entry = ts_map[key]
            entry["timestamp"] = record.collected_at
            entry["crc_errors"] += record.crc_errors
            entry["input_errors"] += record.input_errors

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
    ) -> list[RawDataRow]:
        """獲取最新原始數據。"""
        repo = InterfaceErrorRecordRepo(session)
        records = await repo.get_latest_records(
            maintenance_id=maintenance_id,
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
