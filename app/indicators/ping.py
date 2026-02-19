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

from app.db.models import MaintenanceDeviceList, PingRecord
from app.indicators.base import (
    BaseIndicator,
    DisplayConfig,
    IndicatorEvaluationResult,
    IndicatorMetadata,
    ObservedField,
    RawDataRow,
    TimeSeriesPoint,
)
from app.repositories.typed_records import PingRecordRepo


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
    ) -> IndicatorEvaluationResult:
        """
        評估 Ping 指標。

        分母：MaintenanceDeviceList 中的新設備總數
        分子：新設備中 ping 成功（可達且成功率 >= 80%）的數量
        """
        # 1. 獲取所有新設備清單（分母來源）
        expected_devices = await self._get_expected_devices(
            session, maintenance_id
        )
        total_count = len(expected_devices)

        if total_count == 0:
            return IndicatorEvaluationResult(
                indicator_type=self.indicator_type,
                maintenance_id=maintenance_id,
                total_count=0,
                pass_count=0,
                fail_count=0,
                pass_rates={"reachable": 0.0},
                failures=None,
                summary="無新設備資料"
            )

        # 2. 獲取採集數據，建立 hostname -> PingRecord 的映射
        collected = await self._get_collected_results(
            session, maintenance_id
        )

        # 3. 逐一評估每個新設備
        pass_count = 0
        failures = []
        passes = []

        for device in expected_devices:
            hostname = device["new_hostname"]
            device_status = collected.get(hostname)

            if device_status is None:
                failures.append({
                    "device": hostname,
                    "interface": "Mgmt",
                    "reason": "尚無採集數據",
                    "data": None
                })
            elif not device_status["is_reachable"]:
                failures.append({
                    "device": hostname,
                    "interface": "Mgmt",
                    "reason": "Ping 不可達",
                    "data": {
                        "is_reachable": False,
                        "success_rate": device_status.get("success_rate"),
                        "last_check_at": str(device_status["last_check_at"]) if device_status["last_check_at"] else None,
                    }
                })
            else:
                pass_count += 1
                if len(passes) < 10:
                    passes.append({
                        "device": hostname,
                        "interface": "Mgmt",
                        "reason": "Ping 可達",
                        "data": {
                            "is_reachable": True,
                            "success_rate": device_status.get("success_rate"),
                            "last_check_at": str(device_status["last_check_at"]) if device_status["last_check_at"] else None,
                        }
                    })

        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "reachable": self._calc_percent(pass_count, total_count)
            },
            failures=failures if failures else None,
            passes=passes if passes else None,
            summary=f"連通性檢查: {pass_count}/{total_count} 新設備可達"
        )

    async def _get_expected_devices(
        self,
        session: AsyncSession,
        maintenance_id: str,
    ) -> list[dict]:
        """獲取該歲修的所有新設備清單（排除無 hostname/IP 的設備）。"""
        stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id,
            MaintenanceDeviceList.new_hostname != None,  # noqa: E711
            MaintenanceDeviceList.new_ip_address != None,  # noqa: E711
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
    ) -> dict[str, dict]:
        """
        從 PingRecord 採集紀錄讀取可達性數據。

        使用 PingRecordRepo.get_latest_per_device() 取得每台設備最新的
        ping 結果，與其他指標的資料流一致。
        """
        repo = PingRecordRepo(session)
        records = await repo.get_latest_per_device(maintenance_id)

        # 每台設備可能有多筆 record（多個 target），取最佳結果
        collected: dict[str, dict] = {}
        for record in records:
            hostname = record.switch_hostname
            existing = collected.get(hostname)
            if existing is None or (
                record.is_reachable and not existing["is_reachable"]
            ):
                collected[hostname] = {
                    "is_reachable": record.is_reachable,
                    "success_rate": record.success_rate,
                    "last_check_at": record.collected_at,
                }

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
    ) -> list[TimeSeriesPoint]:
        """獲取時間序列數據。"""
        repo = PingRecordRepo(session)
        records = await repo.get_time_series_records(
            maintenance_id, limit=limit
        )

        # Group records by collected_at to compute reachable rate per timestamp
        from collections import defaultdict

        by_timestamp: dict[object, list[PingRecord]] = defaultdict(list)
        for record in records:
            by_timestamp[record.collected_at].append(record)

        time_series = []
        for ts in sorted(by_timestamp.keys()):
            batch = by_timestamp[ts]
            reachable_count = sum(1 for r in batch if r.is_reachable)
            total = len(batch)
            reachable_rate = (reachable_count / total) * 100 if total > 0 else 0.0

            time_series.append(
                TimeSeriesPoint(
                    timestamp=ts,
                    values={"reachable": reachable_rate},
                )
            )

        return time_series

    async def get_latest_raw_data(
        self,
        limit: int,
        session: AsyncSession,
        maintenance_id: str,
    ) -> list[RawDataRow]:
        """獲取最新原始數據。"""
        repo = PingRecordRepo(session)
        records = await repo.get_latest_records(
            maintenance_id, limit=limit
        )

        raw_data = []
        for record in records:
            raw_data.append(
                RawDataRow(
                    switch_hostname=record.switch_hostname,
                    is_reachable=record.is_reachable,
                    success_rate=record.success_rate,
                    collected_at=record.collected_at,
                )
            )

        return raw_data
