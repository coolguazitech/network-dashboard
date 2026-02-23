"""
Uplink indicator evaluator.

驗證 NEW phase 的 uplink 拓樸是否符合預期。
合併 LLDP + CDP 兩個來源的鄰居資料進行評估。
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MaintenanceDeviceList, UplinkExpectation, NeighborRecord
from app.repositories.typed_records import (
    NeighborLldpRecordRepo,
    NeighborCdpRecordRepo,
    get_typed_repo,
)
from app.indicators.base import (
    BaseIndicator,
    IndicatorEvaluationResult,
    IndicatorMetadata,
    ObservedField,
    DisplayConfig,
    TimeSeriesPoint,
    RawDataRow,
)

# LLDP + CDP 兩個 collection_type，evaluate 時合併查詢
_UPLINK_COLLECTION_TYPES = ("get_uplink_lldp", "get_uplink_cdp")


class UplinkIndicator(BaseIndicator):
    """
    Uplink 拓樸驗收評估器。

    檢查 NEW phase 的設備鄰居是否符合預期。
    合併 LLDP 和 CDP 兩個來源，避免單一協定遺漏鄰居。
    """

    indicator_type = "uplink"

    async def _get_latest_all_protocols(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> list[NeighborRecord]:
        """合併 LLDP + CDP 的最新鄰居記錄。"""
        all_records: list[NeighborRecord] = []
        for ct in _UPLINK_COLLECTION_TYPES:
            repo = get_typed_repo(ct, session)
            records = await repo.get_latest_per_device(maintenance_id)
            all_records.extend(records)
        return all_records

    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> IndicatorEvaluationResult:
        """評估 Uplink 拓樸。"""
        # 從 DB 讀取 uplink 期望
        uplink_expectations = await self._load_expectations(
            session, maintenance_id
        )

        # 合併 LLDP + CDP 最新鄰居記錄
        records = await self._get_latest_all_protocols(
            maintenance_id, session
        )

        # 按設備分組並去重（同一鄰居可能同時出現在 CDP 和 LLDP）
        device_neighbors: dict[str, set[str]] = defaultdict(set)
        for record in records:
            device_neighbors[record.switch_hostname].add(
                record.remote_hostname
            )

        total_count = 0
        pass_count = 0
        failures = []
        passes = []

        # 遍歷每台有期望的設備（以期望值為主，而非收集到的資料）
        for device_hostname, expected_neighbors in uplink_expectations.items():
            if not expected_neighbors:
                continue

            # 取得該設備的實際鄰居
            actual_neighbors = device_neighbors.get(device_hostname, set())

            # 驗證每個期望的鄰居
            for expected_neighbor in expected_neighbors:
                total_count += 1

                if not actual_neighbors:
                    failures.append({
                        "device": device_hostname,
                        "expected_neighbor": expected_neighbor,
                        "reason": "無採集數據",
                    })
                elif expected_neighbor in actual_neighbors:
                    pass_count += 1
                    if len(passes) < 10:
                        passes.append({
                            "device": device_hostname,
                            "interface": "Uplink",
                            "reason": f"鄰居 '{expected_neighbor}' 已連接",
                        })
                else:
                    failures.append({
                        "device": device_hostname,
                        "expected_neighbor": expected_neighbor,
                        "reason": (
                            f"期望鄰居 '{expected_neighbor}' 未找到。"
                            f"實際: {sorted(actual_neighbors)}"
                        ),
                    })

        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "uplink_topology": (pass_count / total_count * 100)
                if total_count > 0 else 0
            },
            failures=failures if failures else None,
            passes=passes if passes else None,
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
        """從 DB 讀取 uplink 期望（僅限仍在設備清單中的設備）。"""
        active_hostnames = (
            select(MaintenanceDeviceList.new_hostname)
            .where(
                MaintenanceDeviceList.maintenance_id == maintenance_id,
                MaintenanceDeviceList.new_hostname.isnot(None),
            )
        )

        stmt = select(UplinkExpectation).where(
            UplinkExpectation.maintenance_id == maintenance_id,
            UplinkExpectation.hostname.in_(active_hostnames),
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
    ) -> list[TimeSeriesPoint]:
        """獲取時間序列數據（合併 LLDP + CDP）。"""
        uplink_expectations = await self._load_expectations(
            session, maintenance_id
        )

        # 合併兩個協定的 time series records
        all_records: list[NeighborRecord] = []
        for ct in _UPLINK_COLLECTION_TYPES:
            repo = get_typed_repo(ct, session)
            records = await repo.get_time_series_records(
                maintenance_id, limit
            )
            all_records.extend(records)

        # 按 (collected_at, switch_hostname) 分組，去重鄰居
        groups: dict[tuple, set[str]] = defaultdict(set)
        for record in all_records:
            key = (record.collected_at, record.switch_hostname)
            groups[key].add(record.remote_hostname)

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
    ) -> list[RawDataRow]:
        """獲取最新原始數據（合併 LLDP + CDP）。"""
        all_records: list[NeighborRecord] = []
        for ct in _UPLINK_COLLECTION_TYPES:
            repo = get_typed_repo(ct, session)
            records = await repo.get_latest_records(
                maintenance_id, limit
            )
            all_records.extend(records)

        # 按時間排序（最新優先）並限制數量
        all_records.sort(key=lambda r: r.collected_at, reverse=True)
        all_records = all_records[:limit]

        raw_data = []
        for record in all_records:
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
