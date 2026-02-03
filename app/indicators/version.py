"""
Version indicator evaluator.

檢查設備版本是否升級到預期版本。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import VersionExpectation, VersionRecord
from app.indicators.base import (
    BaseIndicator,
    DisplayConfig,
    IndicatorEvaluationResult,
    IndicatorMetadata,
    ObservedField,
    RawDataRow,
    TimeSeriesPoint,
)
from app.core.enums import MaintenancePhase
from app.repositories.typed_records import VersionRecordRepo


class VersionIndicator(BaseIndicator):
    """
    Version 版本指標評估器。

    檢查 NEW phase 中的設備版本是否符合預期。
    """

    indicator_type = "version"

    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
        phase: MaintenancePhase | None = None,
    ) -> IndicatorEvaluationResult:
        """評估版本指標。"""
        if phase is None:
            phase = MaintenancePhase.NEW

        # 從 DB 讀取版本期望
        version_expectations = await self._load_expectations(
            session, maintenance_id
        )

        # 若無期望，直接返回
        if not version_expectations:
            return IndicatorEvaluationResult(
                indicator_type=self.indicator_type,
                phase=phase,
                maintenance_id=maintenance_id,
                total_count=0,
                pass_count=0,
                fail_count=0,
                pass_rates={"version_match": 0},
                failures=None,
                summary="無版本期望設定",
            )

        # 查詢所有指定階段的版本數據（每台設備最新一筆）
        repo = VersionRecordRepo(session)
        records = await repo.get_latest_per_device(phase, maintenance_id)

        # 建立 hostname -> 最新版本記錄 的映射
        records_by_hostname: dict[str, VersionRecord] = {}
        for record in records:
            if record.switch_hostname not in records_by_hostname:
                records_by_hostname[record.switch_hostname] = record

        # 以「期望」為基準計算（而非以採集記錄為基準）
        total_count = len(version_expectations)
        pass_count = 0
        failures = []

        # 遍歷每個版本期望
        for hostname, expected_versions in version_expectations.items():
            record = records_by_hostname.get(hostname)

            if record is None:
                # 尚未採集到該設備的版本資料
                failures.append({
                    "device": hostname,
                    "reason": "尚未採集",
                    "expected": ";".join(expected_versions),
                    "actual": None,
                })
            else:
                actual_version = record.version
                # 比較版本（支援分號分隔的多個期望版本）
                if actual_version and actual_version in expected_versions:
                    pass_count += 1
                else:
                    failures.append({
                        "device": hostname,
                        "reason": "版本不符",
                        "expected": ";".join(expected_versions),
                        "actual": actual_version,
                    })

        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            phase=phase,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "version_match": (pass_count / total_count * 100)
                if total_count > 0 else 0
            },
            failures=failures if failures else None,
            summary=(
                f"版本驗收: {pass_count}/{total_count} 通過 "
                f"({pass_count / total_count * 100:.1f}%)"
            )
            if total_count > 0 else "無版本期望設定",
        )

    async def _load_expectations(
        self,
        session: AsyncSession,
        maintenance_id: str,
    ) -> dict[str, list[str]]:
        """從 DB 讀取版本期望。返回 hostname -> [expected_versions]。"""
        stmt = select(VersionExpectation).where(
            VersionExpectation.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        expectations = result.scalars().all()

        exp_map: dict[str, list[str]] = {}
        for exp in expectations:
            # expected_versions 是分號分隔的字串
            versions = [
                v.strip()
                for v in exp.expected_versions.split(";")
                if v.strip()
            ]
            exp_map[exp.hostname] = versions

        return exp_map

    def get_metadata(self) -> IndicatorMetadata:
        """獲取指標元數據。"""
        return IndicatorMetadata(
            name="version",
            title="韌體版本監控",
            description="驗證設備是否已升級到目標版本",
            object_type="switch",
            data_type="string",
            observed_fields=[
                ObservedField(
                    name="version",
                    display_name="目前版本",
                    metric_name="version",
                    unit=None,
                ),
            ],
            display_config=DisplayConfig(
                chart_type="gauge",
                show_raw_data_table=True,
                refresh_interval_seconds=3600,
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
        version_expectations = await self._load_expectations(
            session, maintenance_id
        )

        repo = VersionRecordRepo(session)
        records = await repo.get_time_series_records(
            maintenance_id, phase, limit
        )

        time_series = []
        for record in reversed(records):
            expected = version_expectations.get(
                record.switch_hostname, []
            )
            actual = record.version
            match_rate = (
                100.0
                if expected and actual in expected
                else 0.0
            )

            time_series.append(
                TimeSeriesPoint(
                    timestamp=record.collected_at,
                    values={"version_match": match_rate},
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
        version_expectations = await self._load_expectations(
            session, maintenance_id
        )

        repo = VersionRecordRepo(session)
        records = await repo.get_latest_records(
            maintenance_id, phase, limit
        )

        raw_data = []
        for record in records:
            expected = version_expectations.get(
                record.switch_hostname, []
            )
            actual = record.version

            raw_data.append(
                RawDataRow(
                    switch_hostname=record.switch_hostname,
                    version=actual,
                    expected_version=(
                        ";".join(expected) if expected else None
                    ),
                    version_match=(
                        actual in expected if expected else None
                    ),
                    collected_at=record.collected_at,
                )
            )

        return raw_data
