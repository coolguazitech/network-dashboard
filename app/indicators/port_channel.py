"""
Port-Channel indicator evaluator.

Evaluates if Port-Channels match the expected configuration and status.
"""
from __future__ import annotations

from collections import OrderedDict, defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import LinkStatus
from app.db.models import PortChannelExpectation, PortChannelRecord
from app.indicators.base import (
    BaseIndicator,
    DisplayConfig,
    IndicatorEvaluationResult,
    IndicatorMetadata,
    ObservedField,
    RawDataRow,
    TimeSeriesPoint,
)
from app.repositories.typed_records import PortChannelRecordRepo

# Type aliases for readability
_ExpMap = dict[str, dict[str, PortChannelExpectation]]
_DevicePCMap = dict[str, dict[str, PortChannelRecord]]
_Failure = dict[str, Any]


class PortChannelIndicator(BaseIndicator):
    """
    Port-Channel 指標評估器。

    檢查項目：
    1. Port-Channel 是否存在且狀態為 UP
    2. 成員介面是否完全匹配期望清單
    3. 所有成員介面狀態是否正常 (UP/Bundled)
    """

    indicator_type = "port_channel"

    # ── evaluate ────────────────────────────────────────────────────

    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> IndicatorEvaluationResult:
        """
        評估 Port-Channel 指標。

        Args:
            maintenance_id: 維護作業 ID
            session: 資料庫 session
        """
        exp_map = await self._build_expectation_map(session, maintenance_id)

        repo = PortChannelRecordRepo(session)
        records = await repo.get_latest_per_device(maintenance_id)
        device_pcs = self._build_device_pc_map(records)

        total_count = 0
        pass_count = 0
        failures: list[_Failure] = []
        passes: list[_Failure] = []

        for hostname, pcs in exp_map.items():
            t, p, f, ps = self._evaluate_device(hostname, pcs, device_pcs)
            total_count += t
            pass_count += p
            failures.extend(f)
            if len(passes) < 10:
                passes.extend(ps[:10 - len(passes)])

        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "status_ok": self._calc_percent(pass_count, total_count),
            },
            failures=failures or None,
            passes=passes or None,
            summary=f"Port-Channel: {pass_count}/{total_count} 通過",
        )

    # ── evaluate helpers ────────────────────────────────────────────

    async def _build_expectation_map(
        self,
        session: AsyncSession,
        maintenance_id: str,
    ) -> _ExpMap:
        """Load expectations and index them as hostname -> {pc_name: exp}."""
        stmt = select(PortChannelExpectation).where(
            PortChannelExpectation.maintenance_id == maintenance_id,
        )
        result = await session.execute(stmt)
        expectations = result.scalars().all()

        exp_map: _ExpMap = {}
        for exp in expectations:
            exp_map.setdefault(exp.hostname, {})[exp.port_channel] = exp
        return exp_map

    @staticmethod
    def _build_device_pc_map(records: list[PortChannelRecord]) -> _DevicePCMap:
        """Group flat record list into hostname -> {interface_name: record}."""
        device_pcs: _DevicePCMap = defaultdict(dict)
        for record in records:
            device_pcs[record.switch_hostname][record.interface_name] = record
        return device_pcs

    def _evaluate_device(
        self,
        hostname: str,
        expected_pcs: dict[str, PortChannelExpectation],
        device_pcs: _DevicePCMap,
    ) -> tuple[int, int, list[_Failure], list[_Failure]]:
        """Evaluate all expected port-channels for a single device.

        Returns:
            (total_count, pass_count, failures, passes)
        """
        actual_pcs = device_pcs.get(hostname)
        if not actual_pcs:
            failures = [
                self._failure(hostname, pc_name, "無採集數據")
                for pc_name in expected_pcs
            ]
            return len(expected_pcs), 0, failures, []

        total = 0
        passed = 0
        failures: list[_Failure] = []
        passes: list[_Failure] = []
        for pc_name, exp in expected_pcs.items():
            total += 1
            fail = self._check_single_pc(hostname, pc_name, exp, actual_pcs)
            if fail is not None:
                failures.append(fail)
            else:
                passed += 1
                actual = self._find_actual_record(pc_name, actual_pcs)
                passes.append({
                    "device": hostname,
                    "interface": pc_name,
                    "reason": "Port-Channel 正常",
                    "data": self._record_to_data(actual) if actual else None,
                })

        return total, passed, failures, passes

    def _check_single_pc(
        self,
        hostname: str,
        pc_name: str,
        exp: PortChannelExpectation,
        actual_pcs: dict[str, PortChannelRecord],
    ) -> _Failure | None:
        """Check one expected port-channel against actual data.

        Returns:
            A failure dict if the check fails, or ``None`` if it passes.
        """
        actual = self._find_actual_record(pc_name, actual_pcs)
        if actual is None:
            return self._failure(hostname, pc_name, "Port-Channel 不存在")

        if actual.status.lower() != LinkStatus.UP.value:
            return self._failure(
                hostname, pc_name,
                f"Port-Channel 狀態異常: {actual.status}",
                actual,
            )

        missing = self._missing_members(exp, actual)
        if missing:
            return self._failure(
                hostname, pc_name,
                f"成員缺失: {', '.join(missing)}",
                actual,
            )

        member_issues = self._unhealthy_members(actual)
        if member_issues:
            return self._failure(
                hostname, pc_name,
                f"成員狀態異常: {', '.join(member_issues)}",
                actual,
            )

        return None

    def _find_actual_record(
        self,
        pc_name: str,
        actual_pcs: dict[str, PortChannelRecord],
    ) -> PortChannelRecord | None:
        """Look up a record by exact name, falling back to normalised match."""
        actual = actual_pcs.get(pc_name)
        if actual is not None:
            return actual

        norm = self._normalize_name(pc_name)
        for key, record in actual_pcs.items():
            if self._normalize_name(key) == norm:
                return record
        return None

    @staticmethod
    def _missing_members(
        exp: PortChannelExpectation,
        actual: PortChannelRecord,
    ) -> set[str]:
        """Return expected members that are absent from the actual record."""
        expected = {m.strip() for m in exp.member_interfaces.split(";") if m.strip()}
        present = set(actual.members) if actual.members else set()
        return expected - present

    @staticmethod
    def _unhealthy_members(actual: PortChannelRecord) -> list[str]:
        """Return formatted list of members whose status is not UP."""
        if actual.member_status is None:
            return []
        return [
            f"{m}({status})"
            for m, status in actual.member_status.items()
            if status.lower() != LinkStatus.UP.value
        ]

    @staticmethod
    def _record_to_data(record: PortChannelRecord) -> dict[str, Any]:
        """Serialise a record's key fields into a plain dict for failure data."""
        return {
            "interface_name": record.interface_name,
            "status": record.status,
            "members": record.members,
            "member_status": record.member_status,
        }

    @staticmethod
    def _failure(
        hostname: str,
        pc_name: str,
        reason: str,
        actual: PortChannelRecord | None = None,
    ) -> _Failure:
        """Build a standardised failure dict."""
        data: dict[str, Any] | None = None
        if actual is not None:
            data = {
                "interface_name": actual.interface_name,
                "status": actual.status,
                "members": actual.members,
                "member_status": actual.member_status,
            }
        return {
            "device": hostname,
            "interface": pc_name,
            "reason": reason,
            "data": data,
        }

    # ── shared helpers ──────────────────────────────────────────────

    def _normalize_name(self, name: str) -> str:
        """Normalize interface name for comparison."""
        name = name.lower()
        name = name.replace("port-channel", "po")
        name = name.replace("bridge-aggregation", "bagg")
        return name

    @staticmethod
    def _calc_percent(passed: int, total: int) -> float:
        return (passed / total * 100) if total > 0 else 0.0

    # ── metadata ────────────────────────────────────────────────────

    def get_metadata(self) -> IndicatorMetadata:
        """獲取指標元數據。"""
        return IndicatorMetadata(
            name="port_channel",
            title="Port-Channel 監控",
            description="驗證 Port-Channel 狀態及成員介面配置",
            object_type="switch",
            data_type="string",
            observed_fields=[
                ObservedField(
                    name="pc_status",
                    display_name="Port-Channel 狀態",
                    metric_name="pc_status",
                    unit=None,
                ),
            ],
            display_config=DisplayConfig(
                chart_type="table",
                show_raw_data_table=True,
                refresh_interval_seconds=600,
            ),
        )

    # ── time series ─────────────────────────────────────────────────

    async def get_time_series(
        self,
        limit: int,
        session: AsyncSession,
        maintenance_id: str,
    ) -> list[TimeSeriesPoint]:
        """獲取時間序列數據。"""
        repo = PortChannelRecordRepo(session)
        records = await repo.get_time_series_records(
            maintenance_id=maintenance_id,
            limit=limit,
        )

        # Group records by collected_at to compute per-timestamp UP rate
        ts_groups: OrderedDict[Any, dict[str, int]] = OrderedDict()
        for record in reversed(records):
            ts = record.collected_at
            if ts not in ts_groups:
                ts_groups[ts] = {"up": 0, "total": 0}
            ts_groups[ts]["total"] += 1
            if record.status.lower() == LinkStatus.UP.value:
                ts_groups[ts]["up"] += 1

        return [
            TimeSeriesPoint(
                timestamp=ts,
                values={
                    "pc_status": (
                        counts["up"] / counts["total"] * 100
                        if counts["total"]
                        else 0.0
                    ),
                },
            )
            for ts, counts in ts_groups.items()
        ]

    # ── raw data ────────────────────────────────────────────────────

    async def get_latest_raw_data(
        self,
        limit: int,
        session: AsyncSession,
        maintenance_id: str,
    ) -> list[RawDataRow]:
        """獲取最新原始數據。"""
        repo = PortChannelRecordRepo(session)
        records = await repo.get_latest_records(
            maintenance_id=maintenance_id,
            limit=limit,
        )

        return [
            RawDataRow(
                switch_hostname=record.switch_hostname,
                interface_name=record.interface_name,
                status=record.status,
                members=record.members,
                collected_at=record.collected_at,
            )
            for record in records
        ]
