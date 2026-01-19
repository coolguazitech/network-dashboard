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
from app.indicators.base import BaseIndicator, IndicatorEvaluationResult
from app.core.enums import MaintenancePhase
from app.core.config import settings


class VersionIndicator(BaseIndicator):
    """
    Version 版本指標評估器。
    
    檢查 POST phase 中的設備版本是否符合預期。
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
            phase = MaintenancePhase.POST
        
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
            phase=MaintenancePhase.POST,
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
