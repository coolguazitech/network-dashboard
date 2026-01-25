"""
Version indicator evaluator.

檢查設備版本是否升級到預期版本。
"""
from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.core.enums import MaintenancePhase
from app.core.config import settings


class VersionIndicator(BaseIndicator):
    """
    Version 版本指標評估器。
    
    檢查 NEW phase 中的設備版本是否符合預期。
    """
    
    indicator_type = "version"
    
    def __init__(self) -> None:
        """初始化並讀取版本期望配置。"""
        self.version_expectations = self._load_version_expectations()
    
    def _load_version_expectations(self) -> dict[str, str]:
        """從 switches.yaml 讀取版本期望。"""
        try:
            config_path = Path(settings.switches_config_path)
            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)
            
            # 從配置中提取 version_expectations
            return config.get("version_expectations", {})
        except Exception as e:
            print(f"Warning: Failed to load version expectations: {e}")
            return {}
    
    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
        phase: MaintenancePhase | None = None,
    ) -> IndicatorEvaluationResult:
        """
        評估版本指標。
        """
        if phase is None:
            phase = MaintenancePhase.NEW
        
        # 查詢所有指定階段的版本數據
        stmt = (
            select(CollectionRecord)
            .where(
                CollectionRecord.indicator_type == "version",
                CollectionRecord.phase == phase,
                CollectionRecord.maintenance_id == maintenance_id,
            )
            .order_by(CollectionRecord.collected_at.desc())
        )
        result = await session.execute(stmt)
        records = result.scalars().all()
        
        total_count = 0
        pass_count = 0
        failures = []
        
        # 遍歷每條採集記錄
        for record in records:
            if not record.parsed_data:
                continue
            
            total_count += 1
            device_hostname = record.switch_hostname
            
            # 獲取期望版本
            expected_version = self.version_expectations.get(device_hostname)
            
            if not expected_version:
                failures.append({
                    "device": device_hostname,
                    "reason": "未定義版本期望",
                    "expected": None,
                    "actual": record.parsed_data.get("version")
                })
                continue
            
            # 獲取實際版本
            actual_version = record.parsed_data.get("version")
            
            # 比較版本
            if actual_version == expected_version:
                pass_count += 1
            else:
                failures.append({
                    "device": device_hostname,
                    "reason": f"版本不符",
                    "expected": expected_version,
                    "actual": actual_version,
                })
        
        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            phase=phase,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "version_match": (pass_count / total_count * 100) 
                    if total_count > 0 else 0
            },
            failures=failures if failures else None,
            summary=f"版本驗收: {pass_count}/{total_count} 通過 "
                   f"({pass_count/total_count*100:.1f}%)"
                   if total_count > 0 else "無版本數據"
        )

    def get_metadata(self) -> IndicatorMetadata:
        """獲取指標元數據。"""
        return IndicatorMetadata(
            name="version",
            title="韌體版本監控",
            description="驗證設備是否已升級到目標版本",
            object_type="switch",
            data_type="string",
            observed_fields=[
                ObservedField(
                    name="version",
                    display_name="目前版本",
                    metric_name="version",
                    unit=None,
                ),
            ],
            display_config=DisplayConfig(
                chart_type="gauge",
                show_raw_data_table=True,
                refresh_interval_seconds=3600,
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
                CollectionRecord.indicator_type == "version",
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

            # 計算版本匹配率
            expected = self.version_expectations.get(record.switch_hostname)
            actual = record.parsed_data.get("version")
            match_rate = 100.0 if expected and actual == expected else 0.0

            time_series.append(
                TimeSeriesPoint(
                    timestamp=record.collected_at,
                    values={"version_match": match_rate},
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
                CollectionRecord.indicator_type == "version",
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

            expected = self.version_expectations.get(record.switch_hostname)
            actual = record.parsed_data.get("version")

            raw_data.append(
                RawDataRow(
                    switch_hostname=record.switch_hostname,
                    version=actual,
                    expected_version=expected,
                    version_match=actual == expected if expected else None,
                    collected_at=record.collected_at,
                )
            )

        return raw_data
