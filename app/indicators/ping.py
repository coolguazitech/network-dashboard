"""
Ping Reachability indicator evaluator.

Evaluates if devices are reachable via ICMP.
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


class PingIndicator(BaseIndicator):
    """
    Ping 指標評估器。
    
    檢查項目：
    1. 設備是否可達
    2. 封包遺失率是否低於閾值 (成功率 >= 80%)
    """
    
    indicator_type = "ping"
    
    # 成功率閾值
    SUCCESS_RATE_THRESHOLD = 80.0
    
    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
        phase: MaintenancePhase | None = None,
    ) -> IndicatorEvaluationResult:
        """
        評估 Ping 指標。
        
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
                CollectionRecord.indicator_type == "ping",
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
                # 可能是採集失敗 (Connection Error)
                total_count += 1
                failures.append({
                    "device": record.switch_hostname,
                    "interface": "Mgmt",
                    "reason": "Ping 採集失敗或無數據",
                    "data": None
                })
                continue
                
            items = []
            if isinstance(record.parsed_data, dict) and "items" in record.parsed_data:
                items = record.parsed_data["items"]
            elif isinstance(record.parsed_data, list):
                items = record.parsed_data
            
            for item in items:
                total_count += 1
                
                is_reachable = item.get("is_reachable", False)
                success_rate = item.get("success_rate", 0.0)
                
                if not is_reachable or success_rate < self.SUCCESS_RATE_THRESHOLD:
                    failures.append({
                        "device": record.switch_hostname,
                        "interface": "Mgmt",
                        "reason": f"Ping 失敗: {success_rate}% (預期 >= {self.SUCCESS_RATE_THRESHOLD}%)",
                        "data": item
                    })
                else:
                    pass_count += 1
        
        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            phase=phase,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "reachable": self._calc_percent(pass_count, total_count)
            },
            failures=failures if failures else None,
            summary=f"連通性檢查: {pass_count}/{total_count} 設備可達"
        )

    @staticmethod
    def _calc_percent(passed: int, total: int) -> float:
        return (passed / total * 100) if total > 0 else 0.0

    def get_metadata(self) -> IndicatorMetadata:
        """獲取指標元數據。"""
        return IndicatorMetadata(
            name="ping",
            title="設備連通性監控",
            description="監控設備是否可達",
            object_type="switch",
            data_type="boolean",
            observed_fields=[
                ObservedField(
                    name="reachable",
                    display_name="可達性",
                    metric_name="reachable",
                    unit=None,
                ),
            ],
            display_config=DisplayConfig(
                chart_type="gauge",
                show_raw_data_table=True,
                refresh_interval_seconds=60,
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
                CollectionRecord.indicator_type == "ping",
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

            reachable_count = sum(1 for item in items if item.get("is_reachable", False))
            total = len(items) if items else 1
            reachable_rate = (reachable_count / total) * 100

            time_series.append(
                TimeSeriesPoint(
                    timestamp=record.collected_at,
                    values={"reachable": reachable_rate},
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
                CollectionRecord.indicator_type == "ping",
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
                raw_data.append(
                    RawDataRow(
                        switch_hostname=record.switch_hostname,
                        is_reachable=item.get("is_reachable"),
                        success_rate=item.get("success_rate"),
                        collected_at=record.collected_at,
                    )
                )

        return raw_data[:limit]
