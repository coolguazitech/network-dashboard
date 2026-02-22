"""
Fan Status indicator evaluator.

Evaluates if Fans are in healthy state.
Uses typed FanRecord table via FanRecordRepo.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import FanRecord
from app.indicators.base import (
    BaseIndicator,
    IndicatorEvaluationResult,
    IndicatorMetadata,
    ObservedField,
    DisplayConfig,
    TimeSeriesPoint,
    RawDataRow,
)
from app.repositories.typed_records import FanRecordRepo


class FanIndicator(BaseIndicator):
    """
    Fan Status 指標評估器。

    檢查項目：
    1. 所有風扇狀態是否正常
    """

    indicator_type = "fan"

    @property
    def VALID_STATUSES(self) -> set[str]:
        return settings.operational_healthy_set

    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> IndicatorEvaluationResult:
        """
        評估風扇指標。

        分母 = 設備清單中的設備數（source of truth）。
        分子 = 風扇狀態全部正常的設備數。
        """
        # 1. 設備清單 = 分母
        device_hostnames = await self._get_active_device_hostnames(
            session, maintenance_id,
        )
        total_count = len(device_hostnames)

        if total_count == 0:
            return IndicatorEvaluationResult(
                indicator_type=self.indicator_type,
                maintenance_id=maintenance_id,
                total_count=0, pass_count=0, fail_count=0,
                pass_rates={"status_ok": 0},
                summary="無設備資料",
            )

        # 2. 取採集資料，按設備分組
        repo = FanRecordRepo(session)
        records = await repo.get_latest_per_device(maintenance_id)

        records_by_host: dict[str, list[FanRecord]] = defaultdict(list)
        for record in records:
            records_by_host[record.switch_hostname].append(record)

        # 3. 以設備清單為基準遍歷
        pass_count = 0
        failures = []
        passes = []

        for hostname in device_hostnames:
            device_records = records_by_host.get(hostname, [])

            if not device_records:
                failures.append({
                    "device": hostname,
                    "interface": "Cooling System",
                    "reason": "尚無採集資料",
                    "data": None,
                })
                continue

            device_passed = True
            device_issues = []

            for record in device_records:
                status = str(record.status).lower().strip()
                if status not in self.VALID_STATUSES:
                    device_passed = False
                    device_issues.append(
                        f"Fan {record.fan_id}: 狀態異常 ({record.status})"
                    )

            if device_passed:
                pass_count += 1
                if len(passes) < 10:
                    passes.append({
                        "device": hostname,
                        "interface": "Cooling System",
                        "reason": f"全部 {len(device_records)} 個風扇正常",
                        "data": [
                            {"fan_id": r.fan_id, "status": r.status}
                            for r in device_records
                        ],
                    })
            else:
                failures.append({
                    "device": hostname,
                    "interface": "Cooling System",
                    "reason": " | ".join(device_issues),
                    "data": [
                        {"fan_id": r.fan_id, "status": r.status}
                        for r in device_records
                    ],
                })

        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "status_ok": self._calc_percent(pass_count, total_count)
            },
            failures=failures if failures else None,
            passes=passes if passes else None,
            summary=f"風扇檢查: {pass_count}/{total_count} 設備正常",
        )

    @staticmethod
    def _calc_percent(passed: int, total: int) -> float:
        return (passed / total * 100) if total > 0 else 0.0

    def get_metadata(self) -> IndicatorMetadata:
        """獲取指標元數據。"""
        return IndicatorMetadata(
            name="fan",
            title="風扇狀態監控",
            description="監控設備風扇是否正常運作",
            object_type="switch",
            data_type="string",
            observed_fields=[
                ObservedField(
                    name="status_ok",
                    display_name="風扇狀態",
                    metric_name="status_ok",
                    unit=None,
                ),
            ],
            display_config=DisplayConfig(
                chart_type="table",
                show_raw_data_table=True,
                refresh_interval_seconds=600,
            ),
        )

    async def get_time_series(
        self,
        limit: int,
        session: AsyncSession,
        maintenance_id: str,
    ) -> list[TimeSeriesPoint]:
        """獲取時間序列數據。"""
        repo = FanRecordRepo(session)
        records = await repo.get_time_series_records(
            maintenance_id=maintenance_id,
            limit=limit,
        )

        # Group records by collected_at to compute per-snapshot OK rate
        snapshots: dict[str, list[FanRecord]] = defaultdict(list)
        for record in records:
            snapshots[record.collected_at].append(record)

        time_series = []
        for collected_at in sorted(snapshots.keys()):
            snapshot_records = snapshots[collected_at]
            ok_count = sum(
                1
                for r in snapshot_records
                if str(r.status).lower().strip() in self.VALID_STATUSES
            )
            ok_rate = (
                (ok_count / len(snapshot_records) * 100)
                if snapshot_records
                else 0.0
            )
            time_series.append(
                TimeSeriesPoint(
                    timestamp=collected_at,
                    values={"status_ok": ok_rate},
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
        repo = FanRecordRepo(session)
        records = await repo.get_latest_records(
            maintenance_id=maintenance_id,
            limit=limit,
        )

        raw_data = []
        for record in records:
            status = str(record.status).lower().strip()
            raw_data.append(
                RawDataRow(
                    switch_hostname=record.switch_hostname,
                    fan_id=record.fan_id,
                    status=record.status,
                    status_ok=status in self.VALID_STATUSES,
                    collected_at=record.collected_at,
                )
            )

        return raw_data
