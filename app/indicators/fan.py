"""
Fan Status indicator evaluator.

Evaluates if Fans are in healthy state.
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


class FanIndicator(BaseIndicator):
    """
    Fan Status 指標評估器。
    
    檢查項目：
    1. 所有風扇狀態是否正常
    """
    
    indicator_type = "fan"
    
    # 可接受的狀態字串 (normalized to lowercase)
    VALID_STATUSES = {"ok", "good", "normal", "active"}
    
    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
        phase: MaintenancePhase | None = None,
    ) -> IndicatorEvaluationResult:
        """
        評估風扇指標。
        
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
                CollectionRecord.indicator_type == "fan",
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
            
            # Check each Fan on the device
            device_passed = True
            device_issues = []
            
            if not items:
                failures.append({
                    "device": record.switch_hostname,
                    "interface": "N/A",
                    "reason": "未檢測到風扇",
                    "data": None
                })
                continue
            
            for item in items:
                fan_id = item.get("fan_id", "Unknown")
                status = str(item.get("status", "")).lower().strip()
                
                if status not in self.VALID_STATUSES:
                    device_passed = False
                    device_issues.append(f"Fan {fan_id}: 狀態異常 ({item.get('status')})")
            
            # Record result
            total_count += 1
            if device_passed:
                pass_count += 1
            else:
                failures.append({
                    "device": record.switch_hostname,
                    "interface": "Cooling System",
                    "reason": " | ".join(device_issues),
                    "data": items
                })
        
        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            phase=phase,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "status_ok": self._calc_percent(pass_count, total_count)
            },
            failures=failures if failures else None,
            summary=f"風扇檢查: {pass_count}/{total_count} 設備正常"
        )

    @staticmethod
    def _calc_percent(passed: int, total: int) -> float:
        return (passed / total * 100) if total > 0 else 0.0

    def get_metadata(self) -> IndicatorMetadata:
        """獲取指標元數據。"""
        return IndicatorMetadata(
            name="fan",
            title="風扇狀態監控",
            description="監控設備風扇是否正常運作",
            object_type="switch",
            data_type="string",
            observed_fields=[
                ObservedField(
                    name="status_ok",
                    display_name="風扇狀態",
                    metric_name="status_ok",
                    unit=None,
                ),
            ],
            display_config=DisplayConfig(
                chart_type="table",
                show_raw_data_table=True,
                refresh_interval_seconds=600,
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
                CollectionRecord.indicator_type == "fan",
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

            ok_count = sum(
                1 for item in items
                if str(item.get("status", "")).lower().strip() in self.VALID_STATUSES
            )
            ok_rate = (ok_count / len(items) * 100) if items else 0.0

            time_series.append(
                TimeSeriesPoint(
                    timestamp=record.collected_at,
                    values={"status_ok": ok_rate},
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
                CollectionRecord.indicator_type == "fan",
                CollectionRecord.phase == phase,
                CollectionRecord.maintenance_id == maintenance_id,
            )
            .order_by(CollectionRecord.collected_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        records = result.scalars().all()

        raw_data = []
        for record in records:
            if not record.parsed_data:
                continue

            items = []
            if isinstance(record.parsed_data, dict) and "items" in record.parsed_data:
                items = record.parsed_data["items"]
            elif isinstance(record.parsed_data, list):
                items = record.parsed_data

            for item in items:
                status = str(item.get("status", "")).lower().strip()
                raw_data.append(
                    RawDataRow(
                        switch_hostname=record.switch_hostname,
                        fan_id=item.get("fan_id"),
                        status=item.get("status"),
                        status_ok=status in self.VALID_STATUSES,
                        collected_at=record.collected_at,
                    )
                )

        return raw_data[:limit]
