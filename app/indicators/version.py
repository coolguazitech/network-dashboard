"""
Version indicator evaluator.

檢查設備版本（含補丁）是否符合預期。

驗收邏輯：
- 期望值以分號分隔多個子字串（如 "R1238P06;PATCH-R1238P06H01"）
- 實際值是 packages 列表（如 ["flash:/5710-CMW710-BOOT-R1238P06.bin", ...]）
- 每個期望子字串只要是某個實際 package 的 substring 即算匹配
- 所有期望子字串都匹配 → 該設備通過
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
from app.repositories.typed_records import VersionRecordRepo


class VersionIndicator(BaseIndicator):
    """
    Version 版本指標評估器。

    檢查 NEW phase 中的設備版本是否符合預期。
    """

    indicator_type = "version"

    @staticmethod
    def _match_expectations(
        expected_substrings: list[str],
        actual_packages: list[str],
    ) -> tuple[bool, list[str]]:
        """檢查每個期望子字串是否為某個實際 package 的 substring。

        Returns:
            (all_matched, list_of_unmatched_substrings)
        """
        unmatched: list[str] = []
        for exp in expected_substrings:
            found = any(exp in pkg for pkg in actual_packages)
            if not found:
                unmatched.append(exp)
        return len(unmatched) == 0, unmatched

    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> IndicatorEvaluationResult:
        """評估版本指標。"""
        # 從 DB 讀取版本期望
        version_expectations = await self._load_expectations(
            session, maintenance_id
        )

        # 若無期望，直接返回
        if not version_expectations:
            return IndicatorEvaluationResult(
                indicator_type=self.indicator_type,
                maintenance_id=maintenance_id,
                total_count=0,
                pass_count=0,
                fail_count=0,
                pass_rates={"version_match": 0},
                failures=None,
                summary="無版本期望設定",
            )

        # 查詢版本數據（每台設備最新一筆）
        repo = VersionRecordRepo(session)
        records = await repo.get_latest_per_device(maintenance_id)

        # 建立 hostname -> 最新版本記錄 的映射
        records_by_hostname: dict[str, VersionRecord] = {}
        for record in records:
            if record.switch_hostname not in records_by_hostname:
                records_by_hostname[record.switch_hostname] = record

        # 以「期望」為基準計算
        total_count = len(version_expectations)
        pass_count = 0
        failures = []
        passes = []

        for hostname, expected_substrings in version_expectations.items():
            record = records_by_hostname.get(hostname)

            if record is None:
                failures.append({
                    "device": hostname,
                    "reason": "尚未採集",
                    "expected": ";".join(expected_substrings),
                    "actual": None,
                })
                continue

            actual_packages = record.packages or []
            if not actual_packages:
                failures.append({
                    "device": hostname,
                    "reason": "採集結果為空",
                    "expected": ";".join(expected_substrings),
                    "actual": None,
                })
                continue

            matched, unmatched = self._match_expectations(
                expected_substrings, actual_packages,
            )

            if matched:
                pass_count += 1
                if len(passes) < 10:
                    passes.append({
                        "device": hostname,
                        "reason": "版本符合",
                        "expected": ";".join(expected_substrings),
                        "actual": "; ".join(actual_packages),
                    })
            else:
                failures.append({
                    "device": hostname,
                    "reason": f"版本不符（未匹配: {', '.join(unmatched)}）",
                    "expected": ";".join(expected_substrings),
                    "actual": "; ".join(actual_packages),
                })

        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "version_match": (pass_count / total_count * 100)
                if total_count > 0 else 0
            },
            failures=failures if failures else None,
            passes=passes if passes else None,
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
        """從 DB 讀取版本期望。

        expected_versions 以分號分隔，每個子字串代表一個期望的 substring。
        """
        stmt = select(VersionExpectation).where(
            VersionExpectation.maintenance_id == maintenance_id,
        )
        result = await session.execute(stmt)
        expectations = result.scalars().all()

        exp_map: dict[str, list[str]] = {}
        for exp in expectations:
            substrings = [
                v.strip()
                for v in exp.expected_versions.split(";")
                if v.strip()
            ]
            exp_map[exp.hostname] = substrings

        return exp_map

    def get_metadata(self) -> IndicatorMetadata:
        """獲取指標元數據。"""
        return IndicatorMetadata(
            name="version",
            title="韌體版本監控",
            description="驗證設備是否已升級到目標版本（含補丁）",
            object_type="switch",
            data_type="string",
            observed_fields=[
                ObservedField(
                    name="version",
                    display_name="安裝套件",
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
    ) -> list[TimeSeriesPoint]:
        """獲取時間序列數據。"""
        version_expectations = await self._load_expectations(
            session, maintenance_id
        )

        repo = VersionRecordRepo(session)
        records = await repo.get_time_series_records(
            maintenance_id, limit
        )

        time_series = []
        for record in reversed(records):
            expected = version_expectations.get(
                record.switch_hostname, []
            )
            actual_packages = record.packages or []
            if expected and actual_packages:
                matched, _ = self._match_expectations(
                    expected, actual_packages,
                )
                match_rate = 100.0 if matched else 0.0
            else:
                match_rate = 0.0

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
        offset: int = 0,
    ) -> list[RawDataRow]:
        """獲取最新原始數據。"""
        version_expectations = await self._load_expectations(
            session, maintenance_id
        )

        repo = VersionRecordRepo(session)
        records = await repo.get_latest_records(
            maintenance_id, limit, offset=offset
        )

        raw_data = []
        for record in records:
            expected = version_expectations.get(
                record.switch_hostname, []
            )
            actual_packages = record.packages or []
            if expected and actual_packages:
                matched, _ = self._match_expectations(
                    expected, actual_packages,
                )
            else:
                matched = False

            raw_data.append(
                RawDataRow(
                    switch_hostname=record.switch_hostname,
                    version="; ".join(actual_packages) if actual_packages else None,
                    expected_version=(
                        ";".join(expected) if expected else None
                    ),
                    version_match=matched if expected else None,
                    collected_at=record.collected_at,
                )
            )

        return raw_data
