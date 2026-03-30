"""
Uplink indicator evaluator.

驗證 NEW phase 的 uplink 拓樸是否符合預期。
合併 LLDP + CDP 兩個來源的鄰居資料進行評估。
"""
from __future__ import annotations

import logging
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import UplinkExpectation, NeighborRecord
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

logger = logging.getLogger(__name__)

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
        """評估 Uplink 拓樸。

        匹配邏輯（優先順序）：
        1. 正向 interface 精確匹配：A 的 LLDP 看到 (B, local_if, remote_if) 完全吻合
        2. 正向 hostname 匹配：A 的 LLDP 看到 B（hostname 一致即可）
        3. 反向匹配：B 的 LLDP 看到 A（處理用戶填反的情況）

        **鄰居不需要在設備清單中** — 只要本機 A 的 LLDP/CDP 採集到
        鄰居 B 就足夠，B 不必被 SNMP 採集。
        """
        # 從 DB 讀取 uplink 期望（含 interface）
        expectations = await self._load_expectations_full(
            session, maintenance_id
        )

        # 合併 LLDP + CDP 最新鄰居記錄
        records = await self._get_latest_all_protocols(
            maintenance_id, session
        )

        # 按設備分組 — hostname-level set + interface-level set
        device_neighbors: dict[str, set[str]] = defaultdict(set)
        # (switch_hostname, remote_hostname) → set of (local_if, remote_if)
        neighbor_interfaces: dict[
            tuple[str, str], set[tuple[str, str]]
        ] = defaultdict(set)

        for record in records:
            device_neighbors[record.switch_hostname].add(
                record.remote_hostname
            )
            neighbor_interfaces[
                (record.switch_hostname, record.remote_hostname)
            ].add((record.local_interface, record.remote_interface))

        total_count = 0
        pass_count = 0
        failures: list[dict] = []
        passes: list[dict] = []

        for exp in expectations:
            total_count += 1
            hostname = exp.hostname
            neighbor = exp.expected_neighbor
            exp_local_if = exp.local_interface
            exp_remote_if = exp.expected_interface

            actual_neighbors = device_neighbors.get(hostname, set())

            # ── 正向匹配（本機 LLDP 看到鄰居）──
            matched = False
            match_detail = ""

            if neighbor in actual_neighbors:
                # hostname 匹配成功 — 檢查 interface
                iface_pairs = neighbor_interfaces.get(
                    (hostname, neighbor), set()
                )
                if (exp_local_if, exp_remote_if) in iface_pairs:
                    matched = True
                    match_detail = (
                        f"{hostname}:{exp_local_if} ↔ "
                        f"{neighbor}:{exp_remote_if} ✓"
                    )
                else:
                    # hostname 對但 interface 不完全吻合 — 仍算通過
                    # （LLDP 的 interface 命名可能與期望不一致）
                    matched = True
                    actual_ifs = ", ".join(
                        f"{l}↔{r}" for l, r in sorted(iface_pairs)
                    )
                    match_detail = (
                        f"鄰居 '{neighbor}' 已連接"
                        f"（interface 不完全吻合: "
                        f"期望 {exp_local_if}↔{exp_remote_if}, "
                        f"實際 {actual_ifs}）"
                    )

            # ── 反向匹配（鄰居 LLDP 看到本機）──
            if not matched:
                reverse_neighbors = device_neighbors.get(neighbor, set())
                if hostname in reverse_neighbors:
                    matched = True
                    match_detail = (
                        f"鄰居 '{neighbor}' 反向確認 "
                        f"('{neighbor}' 的 LLDP 看到 '{hostname}')"
                    )

            if matched:
                pass_count += 1
                if len(passes) < 10:
                    passes.append({
                        "device": hostname,
                        "interface": exp_local_if,
                        "reason": match_detail,
                    })
            else:
                reason = self._build_failure_reason(
                    hostname, neighbor, exp_local_if, exp_remote_if,
                    actual_neighbors, device_neighbors,
                )
                failures.append({
                    "device": hostname,
                    "interface": exp_local_if,
                    "expected_neighbor": neighbor,
                    "expected_interface": exp_remote_if,
                    "reason": reason,
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

    @staticmethod
    def _build_failure_reason(
        hostname: str,
        neighbor: str,
        exp_local_if: str,
        exp_remote_if: str,
        actual_neighbors: set[str],
        device_neighbors: dict[str, set[str]],
    ) -> str:
        """Build a descriptive failure reason."""
        reverse_neighbors = device_neighbors.get(neighbor, set())

        if not actual_neighbors and not reverse_neighbors:
            return (
                f"無採集數據 — "
                f"{hostname} 未採集到任何 LLDP/CDP 鄰居，"
                f"且 {neighbor} 也無資料"
            )

        parts = [
            f"期望 {hostname}:{exp_local_if} ↔ "
            f"{neighbor}:{exp_remote_if} 未找到。"
        ]
        if actual_neighbors:
            parts.append(
                f"{hostname} 的實際鄰居: {sorted(actual_neighbors)}"
            )
        else:
            parts.append(f"{hostname} 未採集到任何 LLDP/CDP 鄰居")

        if reverse_neighbors:
            parts.append(
                f"{neighbor} 的鄰居（反向）: {sorted(reverse_neighbors)}"
            )
        else:
            parts.append(
                f"{neighbor} 無採集資料（可能不在設備清單中，這不影響正向匹配）"
            )

        return " | ".join(parts)

    async def _load_expectations_full(
        self,
        session: AsyncSession,
        maintenance_id: str,
    ) -> list[UplinkExpectation]:
        """從 DB 讀取 uplink 期望（含 interface 資訊）。"""
        stmt = select(UplinkExpectation).where(
            UplinkExpectation.maintenance_id == maintenance_id,
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def _load_expectations(
        self,
        session: AsyncSession,
        maintenance_id: str,
    ) -> dict[str, list[str]]:
        """從 DB 讀取 uplink 期望（hostname-level，供 time_series 使用）。"""
        exps = await self._load_expectations_full(session, maintenance_id)
        exp_map: dict[str, list[str]] = {}
        for exp in exps:
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

        # 按時間戳聚合：同一時間點所有設備的平均匹配率（雙向查找）
        ts_map: dict[object, list[float]] = defaultdict(list)
        for (collected_at, hostname), actual_neighbors in groups.items():
            expected_neighbors = uplink_expectations.get(hostname, [])
            if expected_neighbors:
                match_count = 0
                for n in expected_neighbors:
                    forward = n in actual_neighbors
                    reverse_neighbors = groups.get(
                        (collected_at, n), set()
                    )
                    reverse = hostname in reverse_neighbors
                    if forward or reverse:
                        match_count += 1
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
        offset: int = 0,
    ) -> list[RawDataRow]:
        """獲取最新原始數據（合併 LLDP + CDP）。"""
        all_records: list[NeighborRecord] = []
        for ct in _UPLINK_COLLECTION_TYPES:
            repo = get_typed_repo(ct, session)
            records = await repo.get_latest_records(
                maintenance_id, limit + offset
            )
            all_records.extend(records)

        # 按時間排序（最新優先）並分頁
        all_records.sort(key=lambda r: r.collected_at, reverse=True)
        all_records = all_records[offset:offset + limit]

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
