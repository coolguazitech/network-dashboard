"""
Indicator evaluation service.

協調所有指標評估器的運行。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.indicators.transceiver import TransceiverIndicator
from app.indicators.version import VersionIndicator
from app.indicators.uplink import UplinkIndicator
from app.indicators.port_channel import PortChannelIndicator
from app.indicators.power import PowerIndicator
from app.indicators.fan import FanIndicator
from app.indicators.error_count import ErrorCountIndicator
from app.indicators.ping import PingIndicator
from app.indicators.base import IndicatorEvaluationResult


class IndicatorService:
    """指標評估服務。"""
    
    def __init__(self) -> None:
        """初始化所有評估器。"""
        self.transceiver_indicator = TransceiverIndicator()
        self.version_indicator = VersionIndicator()
        self.uplink_indicator = UplinkIndicator()
        self.port_channel_indicator = PortChannelIndicator()
        self.power_indicator = PowerIndicator()
        self.fan_indicator = FanIndicator()
        self.error_count_indicator = ErrorCountIndicator()
        self.ping_indicator = PingIndicator()
    
    async def evaluate_all(
        self,
        maintenance_id: str,
        session: AsyncSession,
        phase: str = "NEW",
    ) -> dict[str, IndicatorEvaluationResult]:
        """
        評估所有指標。
        """
        from app.core.enums import MaintenancePhase
        maintenance_phase = (
            MaintenancePhase.OLD if phase.upper() == "OLD" 
            else MaintenancePhase.NEW
        )
        
        results = {}
        
        # 評估光模塊
        try:
            results["transceiver"] = await self.transceiver_indicator.evaluate(
                maintenance_id=maintenance_id,
                session=session,
                phase=maintenance_phase,
            )
        except Exception as e:
            print(f"Error evaluating transceiver: {e}")
        
        # 評估版本
        try:
            results["version"] = await self.version_indicator.evaluate(
                maintenance_id=maintenance_id,
                session=session,
                phase=maintenance_phase,
            )
        except Exception as e:
            print(f"Error evaluating version: {e}")
        
        # 評估 Uplink
        try:
            results["uplink"] = await self.uplink_indicator.evaluate(
                maintenance_id=maintenance_id,
                session=session,
                phase=maintenance_phase,
            )
        except Exception as e:
            print(f"Error evaluating uplink: {e}")
            
        # 評估 Port-Channel
        try:
            results["port_channel"] = await self.port_channel_indicator.evaluate(
                maintenance_id=maintenance_id,
                session=session,
                phase=maintenance_phase,
            )
        except Exception as e:
            print(f"Error evaluating port_channel: {e}")
            
        # 評估 Power
        try:
            results["power"] = await self.power_indicator.evaluate(
                maintenance_id=maintenance_id,
                session=session,
                phase=maintenance_phase,
            )
        except Exception as e:
            print(f"Error evaluating power: {e}")
            
        # 評估 Fan
        try:
            results["fan"] = await self.fan_indicator.evaluate(
                maintenance_id=maintenance_id,
                session=session,
                phase=maintenance_phase,
            )
        except Exception as e:
            print(f"Error evaluating fan: {e}")
            
        # 評估 Error Count
        try:
            results["error_count"] = await self.error_count_indicator.evaluate(
                maintenance_id=maintenance_id,
                session=session,
                phase=maintenance_phase,
            )
        except Exception as e:
            print(f"Error evaluating error_count: {e}")
            
        # 評估 Ping
        try:
            results["ping"] = await self.ping_indicator.evaluate(
                maintenance_id=maintenance_id,
                session=session,
                phase=maintenance_phase,
            )
        except Exception as e:
            print(f"Error evaluating ping: {e}")
        
        return results
    
    async def get_dashboard_summary(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """
        獲取 Dashboard 摘要。
        
        包含所有指標的通過率和快速統計。
        """
        results = await self.evaluate_all(maintenance_id, session)
        
        summary = {
            "maintenance_id": maintenance_id,
            "indicators": {},
            "overall": {
                "total_count": 0,
                "pass_count": 0,
                "fail_count": 0,
                "pass_rate": 0.0,
            }
        }
        
        for indicator_type, result in results.items():
            summary["indicators"][indicator_type] = {
                "total_count": result.total_count,
                "pass_count": result.pass_count,
                "fail_count": result.fail_count,
                "pass_rate": result.pass_rate_percent,
                "summary": result.summary,
            }
            
            # 累計整體統計
            summary["overall"]["total_count"] += result.total_count
            summary["overall"]["pass_count"] += result.pass_count
            summary["overall"]["fail_count"] += result.fail_count
        
        # 計算整體通過率
        if summary["overall"]["total_count"] > 0:
            summary["overall"]["pass_rate"] = (
                summary["overall"]["pass_count"] 
                / summary["overall"]["total_count"] * 100
            )
        
        return summary

    def get_all_indicators(self) -> list:
        """返回所有指标实例。"""
        return [
            self.transceiver_indicator,
            self.version_indicator,
            self.uplink_indicator,
            self.port_channel_indicator,
            self.power_indicator,
            self.fan_indicator,
            self.error_count_indicator,
            self.ping_indicator,
        ]

    def get_indicator(self, name: str):
        """根据名称获取指标实例。"""
        mapping = {
            "transceiver": self.transceiver_indicator,
            "version": self.version_indicator,
            "uplink": self.uplink_indicator,
            "port_channel": self.port_channel_indicator,
            "power": self.power_indicator,
            "fan": self.fan_indicator,
            "error_count": self.error_count_indicator,
            "ping": self.ping_indicator,
        }
        return mapping.get(name)
