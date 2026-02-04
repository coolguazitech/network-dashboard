"""
Uplink indicator evaluator.

驗證 NEW phase 的 uplink 拓樸是否符合預期。
Uses typed NeighborRecord table instead of CollectionRecord JSON blobs.
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NeighborRecord, UplinkExpectation
from app.repositories.typed_records import NeighborRecordRepo
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


class UplinkIndicator(BaseIndicator):
    """
    Uplink 拓樸驗收評估器。

    檢查 NEW phase 的設備鄰居是否符合預期。
    """

    indicator_type = "uplink"

    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
        phase: MaintenancePhase | None = None,
    ) -> IndicatorEvaluationResult:
        """評估 Uplink 拓樸。"""
        if phase is None:
            phase = MaintenancePhase.NEW

        # 從 DB 讀取 uplink 期望
        uplink_expectations = await self._load_expectations(
            session, maintenance_id
        )

        # 使用 NeighborRecordRepo 取得每台設備最新批次的鄰居記錄
        repo = NeighborRecordRepo(session)
        records = await repo.get_latest_per_device(phase, maintenance_id)

        # 按設備分組：每台設備有多筆 NeighborRecord（每個鄰居一筆）
        device_neighbors: dict[str, list[str]] = defaultdict(list)
        for record in records:
            device_neighbors[record.switch_hostname].append(
                record.remote_hostname
            )

        total_count = 0
        pass_count = 0
        failures = []

        # 遍歷每台有期望的設備（以期望值為主，而非收集到的資料）
        for device_hostname, expected_neighbors in uplink_expectations.items():
            if not expected_neighbors:
                continue

            # 取得該設備的實際鄰居
            actual_neighbors = device_neighbors.get(device_hostname, [])

            # 驗證每個期望的鄰居
            for expected_neighbor in expected_neighbors:
                total_count += 1

                if not actual_neighbors:
                    # 沒有收集到資料 → 失敗
                    failures.append({
                        "device": device_hostname,
                        "expected_neighbor": expected_neighbor,
                        "reason": "無採集數據",
                    })
                elif expected_neighbor in actual_neighbors:
                    pass_count += 1
                else:
                    failures.append({
                        "device": device_hostname,
                        "expected_neighbor": expected_neighbor,
                        "reason": (
                            f"期望鄰居 '{expected_neighbor}' 未找到。"
                            f"實際: {actual_neighbors}"
                        ),
                    })

        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            phase=phase,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "uplink_topology": (pass_count / total_count * 100)
                if total_count > 0 else 0
            },
            failures=failures if failures else None,
            summary=(
                f"Uplink 驗收: {pass_count}/{total_count} 通過 "
                f"({pass_count / total_count * 100:.1f}%)"
            )
            if total_count > 0 else "無 Uplink 數據",
        )

    async def _load_expectations(
        self,
        session: AsyncSession,
        maintenance_id: str,
    ) -> dict[str, list[str]]:
        """從 DB 讀取 uplink 期望。"""
        stmt = select(UplinkExpectation).where(
            UplinkExpectation.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        expectations = result.scalars().all()

        exp_map: dict[str, list[str]] = {}
        for exp in expectations:
            if exp.hostname not in exp_map:
                exp_map[exp.hostname] = []
            exp_map[exp.hostname].append(exp.expected_neighbor)

        return exp_map

    def get_metadata(self) -> IndicatorMetadata:
        """獲取指標元數據。"""
        return IndicatorMetadata(
            name="uplink",
            title="Uplink 連接監控",
            description="驗證 Uplink 是否連接到正確的鄰居設備",
            object_type="switch",
            data_type="boolean",
            observed_fields=[
                ObservedField(
                    name="neighbor_connected",
                    display_name="鄰居連接狀態",
                    metric_name="neighbor_connected",
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
        phase: MaintenancePhase = MaintenancePhase.NEW,
    ) -> list[TimeSeriesPoint]:
        """獲取時間序列數據。"""
        uplink_expectations = await self._load_expectations(
            session, maintenance_id
        )

        repo = NeighborRecordRepo(session)
        records = await repo.get_time_series_records(
            maintenance_id, phase, limit
        )

        # 按 (collected_at, switch_hostname) 分組，計算每組的匹配率
        groups: dict[
            tuple, list[str]
        ] = defaultdict(list)
        for record in records:
            key = (record.collected_at, record.switch_hostname)
            groups[key].append(record.remote_hostname)

        # 按時間戳聚合：同一時間點所有設備的平均匹配率
        ts_map: dict[object, list[float]] = defaultdict(list)
        for (collected_at, hostname), actual_neighbors in groups.items():
            expected_neighbors = uplink_expectations.get(hostname, [])
            if expected_neighbors:
                match_count = sum(
                    1 for n in expected_neighbors if n in actual_neighbors
                )
                match_rate = (match_count / len(expected_neighbors)) * 100
            else:
                match_rate = 100.0
            ts_map[collected_at].append(match_rate)

        # 建構 TimeSeriesPoint，按時間正序排列
        time_series = []
        for collected_at in sorted(ts_map.keys()):
            rates = ts_map[collected_at]
            avg_rate = sum(rates) / len(rates) if rates else 100.0
            time_series.append(
                TimeSeriesPoint(
                    timestamp=collected_at,
                    values={"neighbor_connected": avg_rate},
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
        repo = NeighborRecordRepo(session)
        records = await repo.get_latest_records(
            maintenance_id, phase, limit
        )

        raw_data = []
        for record in records:
            raw_data.append(
                RawDataRow(
                    switch_hostname=record.switch_hostname,
                    local_interface=record.local_interface,
                    remote_hostname=record.remote_hostname,
                    remote_interface=record.remote_interface,
                    collected_at=record.collected_at,
                )
            )

        return raw_data
