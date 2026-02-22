"""
Indicator evaluation service.

協調所有指標評估器的運行。
"""
from __future__ import annotations

import logging
import math
from collections import defaultdict
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CollectionError

logger = logging.getLogger(__name__)
from app.indicators.transceiver import TransceiverIndicator
from app.indicators.version import VersionIndicator
from app.indicators.uplink import UplinkIndicator
from app.indicators.port_channel import PortChannelIndicator
from app.indicators.power import PowerIndicator
from app.indicators.fan import FanIndicator
from app.indicators.error_count import ErrorCountIndicator
from app.indicators.ping import PingIndicator
from app.indicators.base import IndicatorEvaluationResult
from app.services.threshold_service import ensure_cache


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
    ) -> dict[str, IndicatorEvaluationResult]:
        """評估所有指標（從 DB 中的採集資料進行真實評估）。"""
        return await self._evaluate_all_real(maintenance_id, session)

    async def _evaluate_all_real(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> dict[str, IndicatorEvaluationResult]:
        """真實評估所有指標。"""
        import time as _time

        # 確保該歲修的閾值快取已載入
        await ensure_cache(session, maintenance_id)

        t0 = _time.monotonic()
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
                )
            except Exception as e:
                logger.error("Error evaluating %s: %s", name, e)

        elapsed = _time.monotonic() - t0
        parts = [
            f"{n}: {r.pass_count}/{r.total_count}"
            for n, r in results.items()
        ]
        logger.info(
            "Indicators for %s: %s (%.2fs)",
            maintenance_id,
            " | ".join(parts),
            elapsed,
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

        # 查詢採集錯誤（含設備主機名，用來判斷與 indicator 失敗的重疊）
        ce_device_sets = await self._get_collection_error_devices(
            session, maintenance_id
        )

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
            ce_devices = ce_device_sets.get(indicator_type, set())
            ce_count = len(ce_devices)

            # 只補上 indicator 自己尚未計入的 CE 設備
            # （expectations-based indicator 已把無資料設備當失敗，不需重複加）
            failure_devices = {
                f.get("device", "") for f in (result.failures or [])
            }
            overlap = len(failure_devices & ce_devices)
            supplement_count = ce_count - overlap

            adjusted_total = result.total_count + supplement_count
            adjusted_fail = result.fail_count + supplement_count
            adjusted_rate = (
                math.floor(result.pass_count / adjusted_total * 100)
                if adjusted_total > 0 else 0.0
            )

            status = self._compute_indicator_status(
                adjusted_total, adjusted_fail, adjusted_rate, ce_count,
            )

            summary["indicators"][indicator_type] = {
                "total_count": adjusted_total,
                "pass_count": result.pass_count,
                "fail_count": adjusted_fail,
                "pass_rate": adjusted_rate,
                "status": status,
                "summary": result.summary,
                "collection_errors": ce_count,
            }

            # 累計整體統計
            summary["overall"]["total_count"] += adjusted_total
            summary["overall"]["pass_count"] += result.pass_count
            summary["overall"]["fail_count"] += adjusted_fail

        # 計算整體通過率與狀態（向下取整）
        overall_rate = 0.0
        if summary["overall"]["total_count"] > 0:
            overall_rate = math.floor(
                summary["overall"]["pass_count"]
                / summary["overall"]["total_count"] * 100
            )
        summary["overall"]["pass_rate"] = overall_rate
        summary["overall"]["status"] = self._compute_overall_status(overall_rate)

        return summary

    @staticmethod
    def _compute_indicator_status(
        total: int, fail: int, rate: float, ce_count: int,
    ) -> str:
        """
        計算單一指標的顯示狀態。

        業務規則：
        - system-error: 採集異常（紫色）— 有 CollectionError
        - no-data: 無資料
        - error: 有失敗且通過率 < 80%（紅色）
        - warning: 有失敗但通過率 >= 80%（黃色）
        - success: 全部通過（綠色）
        """
        if total == 0:
            return "system-error" if ce_count > 0 else "no-data"
        if fail > 0 and ce_count > 0:
            return "system-error"
        if fail == 0:
            return "success"
        if rate < 80:
            return "error"
        return "warning"

    @staticmethod
    def _compute_overall_status(rate: float) -> str:
        """計算整體通過率的顯示狀態（rate 已經是 floor 過的整數）。"""
        if rate >= 100:
            return "success"
        if rate >= 80:
            return "warning"
        return "error"

    @staticmethod
    async def _get_collection_error_devices(
        session: AsyncSession,
        maintenance_id: str,
    ) -> dict[str, set[str]]:
        """查詢採集錯誤，按 collection_type 分組，回傳設備主機名集合。"""
        stmt = select(
            CollectionError.collection_type,
            CollectionError.switch_hostname,
        ).where(CollectionError.maintenance_id == maintenance_id)
        result = await session.execute(stmt)
        groups: dict[str, set[str]] = defaultdict(set)
        for row in result.all():
            groups[row.collection_type].add(row.switch_hostname)
        return groups

    def get_all_indicators(self) -> list:
        """回傳所有指標實例。"""
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
        """根據名稱獲取指標實例。"""
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
