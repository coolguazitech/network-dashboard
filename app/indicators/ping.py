"""
Ping Reachability indicator evaluator.

Evaluates if NEW devices are reachable via ICMP.

分母類型：期望類（EXPECTED COUNT）
- 分母 = MaintenanceDeviceList 中的新設備總數
- 分子 = 新設備中 ping 成功的數量
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MaintenancePhase
from app.db.models import CollectionRecord, MaintenanceDeviceList
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

        分母：MaintenanceDeviceList 中的新設備總數
        分子：新設備中 ping 成功（可達且成功率 >= 80%）的數量
        """
        if phase is None:
            phase = MaintenancePhase.NEW

        # 1. 獲取所有新設備清單（分母來源）
        expected_devices = await self._get_expected_devices(
            session, maintenance_id
        )
        total_count = len(expected_devices)

        if total_count == 0:
            return IndicatorEvaluationResult(
                indicator_type=self.indicator_type,
                phase=phase,
                maintenance_id=maintenance_id,
                total_count=0,
                pass_count=0,
                fail_count=0,
                pass_rates={"reachable": 0.0},
                failures=None,
                summary="無新設備資料"
            )

        # 2. 獲取採集數據，建立 hostname -> 結果 的映射
        collected_results = await self._get_collected_results(
            session, maintenance_id, phase
        )

        # 3. 逐一評估每個新設備
        pass_count = 0
        failures = []

        for device in expected_devices:
            hostname = device["new_hostname"]
            result = collected_results.get(hostname)

            if result is None:
                # 尚未採集數據
                failures.append({
                    "device": hostname,
                    "interface": "Mgmt",
                    "reason": "尚未採集 Ping 數據",
                    "data": None
                })
            elif result.get("error"):
                # 採集失敗
                failures.append({
                    "device": hostname,
                    "interface": "Mgmt",
                    "reason": f"Ping 採集失敗: {result.get('error')}",
                    "data": result
                })
            elif not result.get("is_reachable", False):
                # 不可達
                failures.append({
                    "device": hostname,
                    "interface": "Mgmt",
                    "reason": "Ping 不可達",
                    "data": result
                })
            else:
                success_rate = result.get("success_rate", 0.0)
                if success_rate < self.SUCCESS_RATE_THRESHOLD:
                    # 成功率過低
                    failures.append({
                        "device": hostname,
                        "interface": "Mgmt",
                        "reason": (
                            f"Ping 成功率過低: {success_rate}% "
                            f"(預期 >= {self.SUCCESS_RATE_THRESHOLD}%)"
                        ),
                        "data": result
                    })
                else:
                    # 通過
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
            summary=f"連通性檢查: {pass_count}/{total_count} 新設備可達"
        )

    async def _get_expected_devices(
        self,
        session: AsyncSession,
        maintenance_id: str,
    ) -> list[dict]:
        """獲取該歲修的所有新設備清單。"""
        stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        devices = result.scalars().all()
        return [
            {
                "new_hostname": d.new_hostname,
                "new_ip_address": d.new_ip_address,
            }
            for d in devices
        ]

    async def _get_collected_results(
        self,
        session: AsyncSession,
        maintenance_id: str,
        phase: MaintenancePhase,
    ) -> dict[str, dict]:
        """獲取採集數據，返回 hostname -> 結果 的映射。"""
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

        # 按設備去重，只保留最新記錄
        collected = {}
        for record in all_records:
            hostname = record.switch_hostname
            if hostname in collected:
                continue

            if not record.parsed_data:
                collected[hostname] = {"error": "無數據"}
                continue

            # 解析數據
            items = []
            if isinstance(record.parsed_data, dict):
                if "items" in record.parsed_data:
                    items = record.parsed_data["items"]
                else:
                    items = [record.parsed_data]
            elif isinstance(record.parsed_data, list):
                items = record.parsed_data

            # 取第一筆結果（通常一台設備只有一筆 ping 結果）
            if items:
                collected[hostname] = items[0]
            else:
                collected[hostname] = {"error": "無數據"}

        return collected

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
