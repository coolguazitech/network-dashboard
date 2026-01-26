"""
Indicator evaluation service.

協調所有指標評估器的運行。
"""
from __future__ import annotations

import random
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.enums import MaintenancePhase
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
        self._use_mock = settings.app_env == "testing"
    
    async def evaluate_all(
        self,
        maintenance_id: str,
        session: AsyncSession,
        phase: str = "NEW",
    ) -> dict[str, IndicatorEvaluationResult]:
        """評估所有指標。testing 模式下使用 mock 結果。"""
        maintenance_phase = (
            MaintenancePhase.OLD if phase.upper() == "OLD"
            else MaintenancePhase.NEW
        )

        if self._use_mock:
            return self._get_mock_results(maintenance_id, maintenance_phase)

        return await self._evaluate_all_real(
            maintenance_id, session, maintenance_phase
        )

    async def _evaluate_all_real(
        self,
        maintenance_id: str,
        session: AsyncSession,
        phase: MaintenancePhase,
    ) -> dict[str, IndicatorEvaluationResult]:
        """真實評估所有指標。"""
        indicators = {
            "transceiver": self.transceiver_indicator,
            "version": self.version_indicator,
            "uplink": self.uplink_indicator,
            "port_channel": self.port_channel_indicator,
            "power": self.power_indicator,
            "fan": self.fan_indicator,
            "error_count": self.error_count_indicator,
            "ping": self.ping_indicator,
        }

        results = {}
        for name, indicator in indicators.items():
            try:
                results[name] = await indicator.evaluate(
                    maintenance_id=maintenance_id,
                    session=session,
                    phase=phase,
                )
            except Exception as e:
                print(f"Error evaluating {name}: {e}")

        return results

    def _get_mock_results(
        self,
        maintenance_id: str,
        phase: MaintenancePhase,
    ) -> dict[str, IndicatorEvaluationResult]:
        """
        生成 mock 評估結果，用於前端開發測試。

        模擬真實情境：大部分通過，少數失敗並附帶原因。
        """
        mock_configs = {
            "ping": {
                "total": 34, "pass": 31,
                "pass_rates": {"reachable": 91.2},
                "summary": "連通性檢查: 31/34 新設備可達",
                "failures": [
                    {"device": "SW-NEW-005-AGG", "interface": "Mgmt",
                     "reason": "Ping 不可達", "data": None},
                    {"device": "SW-NEW-017-EQP", "interface": "Mgmt",
                     "reason": "Ping 成功率過低: 60% (預期 >= 80%)",
                     "data": {"success_rate": 60.0}},
                    {"device": "SW-NEW-029-SNR", "interface": "Mgmt",
                     "reason": "尚未採集 Ping 數據", "data": None},
                ],
            },
            "power": {
                "total": 34, "pass": 33,
                "pass_rates": {"status_ok": 97.1},
                "summary": "電源驗收: 33/34 設備通過",
                "failures": [
                    {"device": "SW-NEW-014-EQP", "interface": "PS2",
                     "reason": "電源狀態異常: Failed",
                     "data": {"status": "Failed"}},
                ],
            },
            "fan": {
                "total": 34, "pass": 34,
                "pass_rates": {"status_ok": 100.0},
                "summary": "風扇驗收: 34/34 設備通過",
                "failures": [],
            },
            "transceiver": {
                "total": 204, "pass": 198,
                "pass_rates": {"tx_power_ok": 98.0, "rx_power_ok": 97.1,
                               "temperature_ok": 100.0},
                "summary": "光模塊驗收: 198/204 通過 (97.1%)",
                "failures": [
                    {"device": "SW-NEW-003-AGG", "interface": "XGE1/0/1",
                     "reason": "Rx Power低: -19.2 dBm (預期: > -18.0)",
                     "data": {"rx_power": -19.2, "tx_power": -3.1}},
                    {"device": "SW-NEW-003-AGG", "interface": "XGE1/0/2",
                     "reason": "Rx Power低: -18.5 dBm (預期: > -18.0)",
                     "data": {"rx_power": -18.5, "tx_power": -2.8}},
                    {"device": "SW-NEW-008-AGG", "interface": "XGE1/0/5",
                     "reason": "Tx Power低: -12.8 dBm (預期: > -12.0)",
                     "data": {"tx_power": -12.8, "rx_power": -7.3}},
                    {"device": "SW-NEW-015-EQP", "interface": "XGE1/0/1",
                     "reason": "光模塊缺失或無法讀取",
                     "data": {"tx_power": None, "rx_power": None}},
                    {"device": "SW-NEW-022-AMHS", "interface": "XGE1/0/3",
                     "reason": "溫度高: 62.5°C (預期: < 60.0°C)",
                     "data": {"temperature": 62.5}},
                    {"device": "SW-NEW-030-OTHERS", "interface": "XGE1/0/2",
                     "reason": "Rx Power低: -20.1 dBm (預期: > -18.0)",
                     "data": {"rx_power": -20.1, "tx_power": -4.2}},
                ],
            },
            "error_count": {
                "total": 680, "pass": 674,
                "pass_rates": {"error_free": 99.1},
                "summary": "錯誤計數: 674/680 介面無錯誤",
                "failures": [
                    {"device": "SW-NEW-003-AGG",
                     "interface": "XGE1/0/5",
                     "reason": "CRC: 12, In: 3",
                     "data": {"crc_errors": 12, "input_errors": 3}},
                    {"device": "SW-NEW-010-AGG",
                     "interface": "XGE1/0/8",
                     "reason": "CRC: 5",
                     "data": {"crc_errors": 5}},
                    {"device": "SW-NEW-016-EQP",
                     "interface": "GE1/0/12",
                     "reason": "Out: 8",
                     "data": {"output_errors": 8}},
                    {"device": "SW-NEW-025-SNR",
                     "interface": "XGE1/0/1",
                     "reason": "CRC: 3, In: 1, Out: 2",
                     "data": {"crc_errors": 3, "input_errors": 1,
                              "output_errors": 2}},
                    {"device": "SW-NEW-031-OTHERS",
                     "interface": "GE1/0/3",
                     "reason": "In: 15",
                     "data": {"input_errors": 15}},
                    {"device": "SW-NEW-033-OTHERS",
                     "interface": "GE1/0/7",
                     "reason": "CRC: 2",
                     "data": {"crc_errors": 2}},
                ],
            },
            "port_channel": {
                "total": 32, "pass": 30,
                "pass_rates": {"status_ok": 93.8},
                "summary": "Port-Channel: 30/32 通過",
                "failures": [
                    {"device": "SW-NEW-009-AGG", "interface": "BAGG1",
                     "reason": "成員狀態異常: HGE1/0/26(DOWN)",
                     "data": {"status": "UP",
                              "member_status": {"HGE1/0/25": "UP",
                                                "HGE1/0/26": "DOWN"}}},
                    {"device": "SW-NEW-020-EQP", "interface": "BAGG1",
                     "reason": "Port-Channel 不存在", "data": None},
                ],
            },
            "uplink": {
                "total": 64, "pass": 62,
                "pass_rates": {"uplink_topology": 96.9},
                "summary": "Uplink 驗收: 62/64 通過 (96.9%)",
                "failures": [
                    {"device": "SW-NEW-020-EQP",
                     "expected_neighbor": "SW-NEW-009-AGG",
                     "reason": "期望鄰居 'SW-NEW-009-AGG' 未找到。"
                               "實際: ['SW-NEW-003-AGG']"},
                    {"device": "SW-NEW-028-SNR",
                     "expected_neighbor": "SW-NEW-010-AGG",
                     "reason": "期望鄰居 'SW-NEW-010-AGG' 未找到。"
                               "實際: []"},
                ],
            },
            "version": {
                "total": 34, "pass": 32,
                "pass_rates": {"version_match": 94.1},
                "summary": "版本驗收: 32/34 設備版本正確",
                "failures": [
                    {"device": "SW-OLD-011-EQP",
                     "reason": "版本不符: 6635P05 (預期: 6635P07)"},
                    {"device": "SW-OLD-021-AMHS",
                     "reason": "版本不符: 6635P06 (預期: 6635P07)"},
                ],
            },
        }

        results = {}
        for indicator_type, config in mock_configs.items():
            fail_count = config["total"] - config["pass"]
            results[indicator_type] = IndicatorEvaluationResult(
                indicator_type=indicator_type,
                phase=phase,
                maintenance_id=maintenance_id,
                total_count=config["total"],
                pass_count=config["pass"],
                fail_count=fail_count,
                pass_rates=config["pass_rates"],
                failures=config["failures"] if config["failures"] else None,
                summary=config["summary"],
            )

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
