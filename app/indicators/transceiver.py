"""
Transceiver (光模塊) indicator evaluator.

Evaluates if POST phase transceiver data meets expectations.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CollectionRecord
from app.indicators.base import BaseIndicator, IndicatorEvaluationResult
from app.core.enums import MaintenancePhase


class TransceiverIndicator(BaseIndicator):
    """
    Transceiver 光模塊指標評估器。
    
    檢查 POST phase 中每個光模塊的 Tx/Rx 功率是否在正常範圍內。
    """
    
    indicator_type = "transceiver"
    
    # 光模塊預期值閾值
    TX_POWER_MIN = -12.0  # dBm
    RX_POWER_MIN = -18.0  # dBm
    TEMPERATURE_MAX = 60.0  # °C
    VOLTAGE_MIN = 3.2  # V
    
    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
        phase: MaintenancePhase | None = None,  # 新增參數
    ) -> IndicatorEvaluationResult:
        """
        評估光模塊指標。
        
        Args:
            maintenance_id: 維護作業 ID
            session: 資料庫 session
            phase: 階段 (PRE 或 POST)，如果為 None 則默認 POST
        """
        if phase is None:
            phase = MaintenancePhase.POST
        
        # 查詢所有指定階段的光模塊數據，按設備分組，取最新的
        stmt = (
            select(CollectionRecord)
            .where(
                CollectionRecord.indicator_type == "transceiver",
                CollectionRecord.phase == phase,  # 使用 phase 參數
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
            
            # parsed_data 是光模塊列表
            for transceiver_item in record.parsed_data:
                total_count += 1
                interface_name = transceiver_item.get("interface_name")
                
                # 檢查光模塊是否存在
                tx_power = transceiver_item.get("tx_power")
                rx_power = transceiver_item.get("rx_power")
                
                # 如果 tx_power 和 rx_power 都是 None，判定為光模塊缺失
                if tx_power is None and rx_power is None:
                    failures.append({
                        "device": record.switch_hostname,
                        "interface": interface_name,
                        "reason": "光模塊缺失或無法讀取",
                        "data": {
                            "tx_power": None,
                            "rx_power": None,
                            "temperature": None,
                            "voltage": None,
                        }
                    })
                    continue  # 跳過其他檢查
                
                # 檢查各項指標
                checks_passed = True
                failure_reason = []
                
                # 檢查 Tx Power
                if tx_power is not None and tx_power < self.TX_POWER_MIN:
                    checks_passed = False
                    failure_reason.append(
                        f"Tx Power低: {tx_power} dBm (預期: > {self.TX_POWER_MIN})"
                    )
                
                # 檢查 Rx Power
                rx_power = transceiver_item.get("rx_power")
                if rx_power is not None and rx_power < self.RX_POWER_MIN:
                    checks_passed = False
                    failure_reason.append(
                        f"Rx Power低: {rx_power} dBm (預期: > {self.RX_POWER_MIN})"
                    )
                
                # 檢查溫度
                temperature = transceiver_item.get("temperature")
                if temperature is not None and temperature > self.TEMPERATURE_MAX:
                    checks_passed = False
                    failure_reason.append(
                        f"溫度高: {temperature}°C (預期: < {self.TEMPERATURE_MAX}°C)"
                    )
                
                # 檢查電壓
                voltage = transceiver_item.get("voltage")
                if voltage is not None and voltage < self.VOLTAGE_MIN:
                    checks_passed = False
                    failure_reason.append(
                        f"電壓低: {voltage}V (預期: > {self.VOLTAGE_MIN}V)"
                    )
                
                if checks_passed:
                    pass_count += 1
                else:
                    failures.append({
                        "device": record.switch_hostname,
                        "interface": interface_name,
                        "reason": " | ".join(failure_reason),
                        "data": {
                            "tx_power": tx_power,
                            "rx_power": rx_power,
                            "temperature": transceiver_item.get("temperature"),
                            "voltage": transceiver_item.get("voltage"),
                        }
                    })
        
        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            phase=MaintenancePhase.POST,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "tx_power_ok": self._calculate_pass_rate(
                    records, "tx_power", self.TX_POWER_MIN
                ),
                "rx_power_ok": self._calculate_pass_rate(
                    records, "rx_power", self.RX_POWER_MIN
                ),
                "temperature_ok": self._calculate_pass_rate(
                    records, "temperature", None, self.TEMPERATURE_MAX
                ),
            },
            failures=failures if failures else None,
            summary=f"光模塊驗收: {pass_count}/{total_count} 通過 "
                   f"({self._calc_percent(pass_count, total_count):.1f}%)"
        )
    
    def _calculate_pass_rate(
        self,
        records: list[CollectionRecord],
        field: str,
        min_threshold: float | None = None,
        max_threshold: float | None = None,
    ) -> float:
        """計算特定字段的通過率。"""
        total = 0
        passed = 0
        
        for record in records:
            if not record.parsed_data:
                continue
            
            for item in record.parsed_data:
                value = item.get(field)
                if value is None:
                    continue
                
                total += 1
                
                if min_threshold is not None and value >= min_threshold:
                    passed += 1
                elif max_threshold is not None and value <= max_threshold:
                    passed += 1
                elif min_threshold is None and max_threshold is None:
                    passed += 1
        
        return self._calc_percent(passed, total)
    
    @staticmethod
    def _calc_percent(passed: int, total: int) -> float:
        """計算百分比。"""
        return (passed / total * 100) if total > 0 else 0.0
