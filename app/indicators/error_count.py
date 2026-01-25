"""
Interface Error Count indicator evaluator.

Evaluates if interfaces have any errors.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MaintenancePhase
from app.db.models import CollectionRecord
from app.indicators.base import (
    BaseIndicator,
    IndicatorEvaluationResult,
    IndicatorMetadata,
    ObservedField,
    DisplayConfig,
    TimeSeriesPoint,
    RawDataRow,
)


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
            
        # 獲取實際採集數據
        stmt = (
            select(CollectionRecord)
            .where(
                CollectionRecord.indicator_type == "error_count",
                CollectionRecord.phase == phase,
                CollectionRecord.maintenance_id == maintenance_id,
            )
            .order_by(CollectionRecord.collected_at.desc())
        )
        result = await session.execute(stmt)
        all_records = result.scalars().all()
        
        # 按設備去重
        seen_devices = set()
        records = []
        for record in all_records:
            if record.switch_hostname not in seen_devices:
                records.append(record)
                seen_devices.add(record.switch_hostname)
                
        total_count = 0
        pass_count = 0
        failures = []
        
        for record in records:
            if not record.parsed_data:
                continue
                
            items = []
            if isinstance(record.parsed_data, dict) and "items" in record.parsed_data:
                items = record.parsed_data["items"]
            elif isinstance(record.parsed_data, list):
                items = record.parsed_data
            
            for item in items:
                interface = item.get("interface_name")
                crc = item.get("crc_errors", 0)
                input_err = item.get("input_errors", 0)
                output_err = item.get("output_errors", 0)
                
                total_count += 1
                
                errors = []
                if crc > 0:
                    errors.append(f"CRC: {crc}")
                if input_err > 0:
                    errors.append(f"In: {input_err}")
                if output_err > 0:
                    errors.append(f"Out: {output_err}")
                
                if not errors:
                    pass_count += 1
                else:
                    failures.append({
                        "device": record.switch_hostname,
                        "interface": interface,
                        "reason": ", ".join(errors),
                        "data": item
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
        stmt = (
            select(CollectionRecord)
            .where(
                CollectionRecord.indicator_type == "error_count",
                CollectionRecord.phase == phase,
                CollectionRecord.maintenance_id == maintenance_id,
            )
            .order_by(CollectionRecord.collected_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        records = result.scalars().all()

        time_series = []
        for record in reversed(records):
            if not record.parsed_data:
                continue

            items = []
            if isinstance(record.parsed_data, dict) and "items" in record.parsed_data:
                items = record.parsed_data["items"]
            elif isinstance(record.parsed_data, list):
                items = record.parsed_data

            total_crc = sum(item.get("crc_errors", 0) for item in items)
            total_input = sum(item.get("input_errors", 0) for item in items)

            time_series.append(
                TimeSeriesPoint(
                    timestamp=record.collected_at,
                    values={"crc_errors": float(total_crc), "input_errors": float(total_input)},
                )
            )

        return time_series

    async def get_latest_raw_data(
        self,
        limit: int,
        session: AsyncSession,
        maintenance_id: str,
        phase: MaintenancePhase = MaintenancePhase.NEW,
    ) -> list[RawDataRow]:
        """獲取最新原始數據。"""
        stmt = (
            select(CollectionRecord)
            .where(
                CollectionRecord.indicator_type == "error_count",
                CollectionRecord.phase == phase,
                CollectionRecord.maintenance_id == maintenance_id,
            )
            .order_by(CollectionRecord.collected_at.desc())
            .limit(10)
        )
        result = await session.execute(stmt)
        records = result.scalars().all()

        raw_data = []
        count = 0
        for record in records:
            if not record.parsed_data:
                continue

            items = []
            if isinstance(record.parsed_data, dict) and "items" in record.parsed_data:
                items = record.parsed_data["items"]
            elif isinstance(record.parsed_data, list):
                items = record.parsed_data

            for item in items:
                if count >= limit:
                    break

                raw_data.append(
                    RawDataRow(
                        switch_hostname=record.switch_hostname,
                        interface_name=item.get("interface_name"),
                        crc_errors=item.get("crc_errors"),
                        input_errors=item.get("input_errors"),
                        output_errors=item.get("output_errors"),
                        collected_at=record.collected_at,
                    )
                )
                count += 1

            if count >= limit:
                break

        return raw_data
