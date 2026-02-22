"""
Interface Error Count indicator evaluator.

增量判定邏輯：
    delta = 最新變化點 crc_errors - 上一個變化點 crc_errors
    若 delta > 0 → 異常（error 計數器有增長）

只有一筆 batch（首次採集）時：無歷史可比，視為通過。
delta <= 0（未增長或計數器重置）→ 通過。
"""
from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CollectionBatch, InterfaceErrorRecord
from app.indicators.base import (
    BaseIndicator,
    DisplayConfig,
    IndicatorEvaluationResult,
    IndicatorMetadata,
    ObservedField,
    RawDataRow,
    TimeSeriesPoint,
)
from app.repositories.typed_records import InterfaceErrorRecordRepo


class ErrorCountIndicator(BaseIndicator):
    """
    Error Count 指標評估器。

    公式：delta = 最新 crc_errors - 上次變化點 crc_errors
    若 delta > 0 → 異常（計數器增長代表有新錯誤產生）
    """

    indicator_type = "error_count"

    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> IndicatorEvaluationResult:
        """評估錯誤計數指標。"""
        # 設備清單為空 → 沒有驗收項目
        device_hostnames = await self._get_active_device_hostnames(
            session, maintenance_id,
        )
        if not device_hostnames:
            return IndicatorEvaluationResult(
                indicator_type=self.indicator_type,
                maintenance_id=maintenance_id,
                total_count=0, pass_count=0, fail_count=0,
                pass_rates={"error_no_growth": 0},
                summary="無設備資料",
            )

        repo = InterfaceErrorRecordRepo(session)
        active_set = set(device_hostnames)

        # 1. 取最新採集（per device 最新 batch 的所有 rows）
        current_records = await repo.get_latest_per_device(maintenance_id)

        # 2. 按 device 分組（只保留設備清單中的設備），記錄 latest batch_id
        device_batch: dict[str, int] = {}
        current_by_device: dict[str, list[InterfaceErrorRecord]] = defaultdict(list)
        for r in current_records:
            if r.switch_hostname not in active_set:
                continue
            current_by_device[r.switch_hostname].append(r)
            device_batch[r.switch_hostname] = r.batch_id

        # 3. 找每台設備的上一個 batch（倒數第二個變化點）
        prev_by_device = await self._get_previous_batches(
            session, maintenance_id, device_batch,
        )

        # 4. 逐介面評估
        total_count = 0
        pass_count = 0
        failures: list[dict] = []
        passes: list[dict] = []

        for hostname, current_rows in current_by_device.items():
            prev_rows = prev_by_device.get(hostname, {})

            for record in current_rows:
                total_count += 1
                iface = record.interface_name
                cur_crc = record.crc_errors

                prev_info = prev_rows.get(iface)
                if prev_info is None:
                    # 首次採集，無歷史比對 → 通過
                    pass_count += 1
                    if len(passes) < 10:
                        passes.append({
                            "device": hostname,
                            "interface": iface,
                            "reason": "首次採集，無歷史比對",
                            "data": {"crc_errors": cur_crc, "delta": 0},
                        })
                    continue

                prev_crc = prev_info["crc_errors"]
                delta = cur_crc - prev_crc

                if delta <= 0:
                    # 未增長 or 計數器重置 → 通過
                    pass_count += 1
                    if len(passes) < 10:
                        passes.append({
                            "device": hostname,
                            "interface": iface,
                            "reason": "計數器未增長" if delta == 0 else "計數器已重置",
                            "data": {"crc_errors": cur_crc, "delta": delta},
                        })
                else:
                    # delta > 0 → 異常
                    failures.append({
                        "device": hostname,
                        "interface": iface,
                        "reason": f"CRC 增長 +{delta} ({prev_crc} → {cur_crc})",
                        "data": {
                            "crc_errors": cur_crc,
                            "prev_crc_errors": prev_crc,
                            "delta": delta,
                        },
                    })

        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "error_no_growth": self._calc_percent(pass_count, total_count),
            },
            failures=failures if failures else None,
            passes=passes if passes else None,
            summary=f"錯誤計數: {pass_count}/{total_count} 介面通過",
        )

    @staticmethod
    async def _get_previous_batches(
        session: AsyncSession,
        maintenance_id: str,
        device_batch: dict[str, int],
    ) -> dict[str, dict[str, dict]]:
        """
        取每台設備上一個變化點的 interface error 資料。

        Returns:
            {hostname: {interface_name: {"crc_errors": int}}}
        """
        result: dict[str, dict[str, dict]] = {}

        for hostname, latest_batch_id in device_batch.items():
            # 找倒數第二個 batch
            stmt = (
                select(CollectionBatch.id)
                .where(
                    CollectionBatch.collection_type == "get_error_count",
                    CollectionBatch.maintenance_id == maintenance_id,
                    CollectionBatch.switch_hostname == hostname,
                    CollectionBatch.id < latest_batch_id,
                )
                .order_by(CollectionBatch.id.desc())
                .limit(1)
            )
            batch_result = await session.execute(stmt)
            prev_row = batch_result.scalar_one_or_none()

            if prev_row is None:
                continue

            # 取該 batch 的所有 rows
            rows_stmt = select(InterfaceErrorRecord).where(
                InterfaceErrorRecord.batch_id == prev_row,
            )
            rows_result = await session.execute(rows_stmt)
            prev_records = rows_result.scalars().all()

            iface_map: dict[str, dict] = {}
            for r in prev_records:
                iface_map[r.interface_name] = {
                    "crc_errors": r.crc_errors,
                }
            result[hostname] = iface_map

        return result

    @staticmethod
    def _calc_percent(passed: int, total: int) -> float:
        return (passed / total * 100) if total > 0 else 0.0

    def get_metadata(self) -> IndicatorMetadata:
        """獲取指標元數據。"""
        return IndicatorMetadata(
            name="error_count",
            title="Interface Error 監控",
            description="監控介面 CRC 錯誤計數增量（兩次變化點之間有增長即異常）",
            object_type="interface",
            data_type="integer",
            observed_fields=[
                ObservedField(
                    name="crc_errors",
                    display_name="CRC Errors",
                    metric_name="crc_errors",
                    unit=None,
                ),
            ],
            display_config=DisplayConfig(
                chart_type="line",
                x_axis_label="Time",
                y_axis_label="Error Count",
                show_raw_data_table=True,
                refresh_interval_seconds=300,
            ),
        )

    async def get_time_series(
        self,
        limit: int,
        session: AsyncSession,
        maintenance_id: str,
    ) -> list[TimeSeriesPoint]:
        """獲取時間序列數據。"""
        repo = InterfaceErrorRecordRepo(session)
        records = await repo.get_time_series_records(
            maintenance_id=maintenance_id,
            limit=limit,
        )

        ts_map: dict[str, dict] = defaultdict(
            lambda: {"timestamp": None, "crc_errors": 0}
        )
        for record in records:
            key = record.collected_at.isoformat()
            entry = ts_map[key]
            entry["timestamp"] = record.collected_at
            entry["crc_errors"] += record.crc_errors

        return [
            TimeSeriesPoint(
                timestamp=entry["timestamp"],
                values={"crc_errors": float(entry["crc_errors"])},
            )
            for entry in sorted(ts_map.values(), key=lambda e: e["timestamp"])
        ]

    async def get_latest_raw_data(
        self,
        limit: int,
        session: AsyncSession,
        maintenance_id: str,
    ) -> list[RawDataRow]:
        """獲取最新原始數據。"""
        repo = InterfaceErrorRecordRepo(session)
        records = await repo.get_latest_records(
            maintenance_id=maintenance_id,
            limit=limit,
        )

        return [
            RawDataRow(
                switch_hostname=record.switch_hostname,
                interface_name=record.interface_name,
                crc_errors=record.crc_errors,
                collected_at=record.collected_at,
            )
            for record in records
        ]
