"""
Uplink indicator evaluator.

驗證 POST phase 的 uplink 拓樸是否符合預期。
"""
from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CollectionRecord, DeviceMapping
from app.indicators.base import BaseIndicator, IndicatorEvaluationResult
from app.core.enums import MaintenancePhase
from app.core.config import settings


class UplinkIndicator(BaseIndicator):
    """
    Uplink 拓樸驗收評估器。
    
    檢查 POST phase 的設備鄰居是否符合預期。
    """
    
    indicator_type = "uplink"
    
    def __init__(self) -> None:
        """初始化並讀取 uplink 期望配置。"""
        self.uplink_expectations = self._load_uplink_expectations()
    
    def _load_uplink_expectations(self) -> dict[str, list[str]]:
        """從 switches.yaml 讀取 uplink 期望。"""
        try:
            config_path = Path(settings.switches_config_path)
            with open(config_path, encoding="utf-8") as f:
                config = yaml.safe_load(f)
            
            expectations = {}
            for expectation in config.get("uplink_expectations", []):
                hostname = expectation.get("switch_hostname")
                neighbors = []
                for neighbor_info in expectation.get("expected_neighbors", []):
                    neighbors.append(neighbor_info.get("remote_hostname"))
                expectations[hostname] = neighbors
            
            return expectations
        except Exception as e:
            print(f"Warning: Failed to load uplink expectations: {e}")
            return {}
    
    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
        phase: MaintenancePhase | None = None,
    ) -> IndicatorEvaluationResult:
        """
        評估 Uplink 拓樸。
        """
        if phase is None:
            phase = MaintenancePhase.POST
        
        # 查詢所有指定階段的 uplink 數據
        stmt = (
            select(CollectionRecord)
            .where(
                CollectionRecord.indicator_type == "uplink",
                CollectionRecord.phase == phase,
                CollectionRecord.maintenance_id == maintenance_id,
            )
            .order_by(CollectionRecord.collected_at.desc())
        )
        result = await session.execute(stmt)
        all_records = result.scalars().all()
        
        # 按設備去重，只保留每個設備的最新記錄
        seen_devices = set()
        records = []
        for record in all_records:
            if record.switch_hostname not in seen_devices:
                records.append(record)
                seen_devices.add(record.switch_hostname)
        
        total_count = 0
        pass_count = 0
        failures = []
        
        # 遍歷每條採集記錄
        for record in records:
            if not record.parsed_data:
                continue
            
            device_hostname = record.switch_hostname
            
            # 獲取期望的鄰居
            expected_neighbors = self.uplink_expectations.get(device_hostname, [])
            
            if not expected_neighbors:
                continue
            
            # 獲取實際鄰居
            actual_neighbors = []
            for neighbor_item in record.parsed_data:
                if isinstance(neighbor_item, dict):
                    actual_neighbors.append(neighbor_item.get("remote_hostname"))
            
            # 驗證每個期望的鄰居
            for expected_neighbor in expected_neighbors:
                total_count += 1
                
                if expected_neighbor in actual_neighbors:
                    pass_count += 1
                else:
                    failures.append({
                        "device": device_hostname,
                        "expected_neighbor": expected_neighbor,
                        "reason": f"期望鄰居 '{expected_neighbor}' 未找到。實際: {actual_neighbors}",
                    })
        
        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            phase=MaintenancePhase.POST,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "uplink_topology": (pass_count / total_count * 100)
                    if total_count > 0 else 0
            },
            failures=failures if failures else None,
            summary=f"Uplink 驗收: {pass_count}/{total_count} 通過 "
                   f"({pass_count/total_count*100:.1f}%)"
                   if total_count > 0 else "無 Uplink 數據"
        )
