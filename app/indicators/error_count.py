"""
Interface Error Count indicator evaluator (device-level).

以設備為單位評估：
    分母 = 設備清單中的設備數
    分子 = 任一介面 CRC 計數器有增長的設備數

增量判定邏輯（per interface）：
    delta = 最新變化點 crc_errors - 上一個變化點 crc_errors
    若任一介面 delta > 0 → 該設備異常

設備無錯誤記錄（所有介面零錯誤）→ 通過。
只有一筆 batch（首次採集）時：無歷史可比，視為通過。
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
    Error Count 指標評估器（設備層級）。

    分母 = 設備數，分子 = 任一介面有 CRC 增長的設備數。
    設備無錯誤記錄時視為正常（collector 跳過零錯誤介面）。
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

        # 4. 逐設備評估（分母 = 設備數，分子 = 有 CRC 增長的設備數）
        total_count = len(device_hostnames)
        pass_count = 0
        failures: list[dict] = []
        passes: list[dict] = []

        for hostname in device_hostnames:
            current_rows = current_by_device.get(hostname, [])

            if not current_rows:
                # 無錯誤記錄（collector 跳過零錯誤介面）→ 設備正常
                pass_count += 1
                if len(passes) < 10:
                    passes.append({
                        "device": hostname,
                        "reason": "無錯誤記錄",
                        "data": {},
                    })
                continue

            prev_rows = prev_by_device.get(hostname, {})

            if not prev_rows:
                # 首次採集，無歷史比對 → 通過
                pass_count += 1
                if len(passes) < 10:
                    passes.append({
                        "device": hostname,
                        "reason": "首次採集，無歷史比對",
                        "data": {},
                    })
                continue

            # 檢查每個介面的增長
            growing_interfaces: list[dict] = []
            for record in current_rows:
                prev_info = prev_rows.get(record.interface_name)
                if prev_info is None:
                    continue  # 新介面，無歷史 → 不視為異常
                delta = record.crc_errors - prev_info["crc_errors"]
                if delta > 0:
                    growing_interfaces.append({
                        "interface": record.interface_name,
                        "delta": delta,
                        "prev_crc_errors": prev_info["crc_errors"],
                        "crc_errors": record.crc_errors,
                    })

            if growing_interfaces:
                # 設備有 CRC 增長 → 異常
                if len(failures) < 10:
                    show_limit = 5
                    iface_detail = "; ".join(
                        f"{gi['interface']}(+{gi['delta']})"
                        for gi in growing_interfaces[:show_limit]
                    )
                    if len(growing_interfaces) > show_limit:
                        iface_detail += f" ...等共{len(growing_interfaces)}介面"
                    iface_names = ", ".join(
                        gi["interface"]
                        for gi in growing_interfaces[:show_limit]
                    )
                    if len(growing_interfaces) > show_limit:
                        iface_names += f" ...等{len(growing_interfaces)}介面"
                    failures.append({
                        "device": hostname,
                        "interface": iface_names,
                        "reason": f"CRC 增長: {iface_detail}",
                        "data": {"growing_interfaces": growing_interfaces},
                    })
            else:
                # 所有介面未增長 → 通過
                pass_count += 1
                if len(passes) < 10:
                    passes.append({
                        "device": hostname,
                        "reason": "計數器未增長",
                        "data": {},
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
            summary=f"錯誤計數: {pass_count}/{total_count} 設備通過",
        )

    @staticmethod
    async def _get_previous_batches(
        session: AsyncSession,
        maintenance_id: str,
        device_batch: dict[str, int],
    ) -> dict[str, dict[str, dict]]:
        """
        取每台設備上一個變化點的 interface error 資料。

        使用兩次批量查詢取代 N+1 迴圈：
        1. 一次查出所有設備的倒數第二個 batch_id
        2. 一次查出這些 batch 的所有 error records

        Returns:
            {hostname: {interface_name: {"crc_errors": int}}}
        """
        if not device_batch:
            return {}

        from sqlalchemy import func as sa_func, and_, literal_column

        # ── 第 1 步：批量找每台設備的 prev batch_id ──
        # 用 lateral / correlated subquery 替代 N 次迴圈查詢
        # 構建 UNION ALL: 每台設備一個 (hostname, max_id < latest) 子查詢
        # 但更高效的做法：用 window function 在一次查詢中找到每台設備倒數第二批
        all_batches_stmt = (
            select(
                CollectionBatch.switch_hostname,
                CollectionBatch.id,
                sa_func.row_number().over(
                    partition_by=CollectionBatch.switch_hostname,
                    order_by=CollectionBatch.id.desc(),
                ).label("rn"),
            )
            .where(
                CollectionBatch.collection_type == "get_error_count",
                CollectionBatch.maintenance_id == maintenance_id,
                CollectionBatch.switch_hostname.in_(list(device_batch.keys())),
            )
            .subquery()
        )

        # rn=1 是最新，rn=2 是倒數第二
        prev_batch_stmt = (
            select(
                all_batches_stmt.c.switch_hostname,
                all_batches_stmt.c.id,
            )
            .where(all_batches_stmt.c.rn == 2)
        )
        prev_batch_result = await session.execute(prev_batch_stmt)
        prev_batch_rows = prev_batch_result.all()

        if not prev_batch_rows:
            return {}

        # hostname → prev_batch_id
        prev_batch_map: dict[str, int] = {
            row.switch_hostname: row.id for row in prev_batch_rows
        }

        # ── 第 2 步：批量取所有 prev batch 的 error records ──
        prev_batch_ids = list(prev_batch_map.values())
        rows_stmt = select(InterfaceErrorRecord).where(
            InterfaceErrorRecord.batch_id.in_(prev_batch_ids),
        )
        rows_result = await session.execute(rows_stmt)
        prev_records = rows_result.scalars().all()

        # 按 batch_id 分組，再映射回 hostname
        batch_to_host = {bid: host for host, bid in prev_batch_map.items()}
        result: dict[str, dict[str, dict]] = {}
        for r in prev_records:
            hostname = batch_to_host.get(r.batch_id)
            if hostname is None:
                continue
            if hostname not in result:
                result[hostname] = {}
            result[hostname][r.interface_name] = {
                "crc_errors": r.crc_errors,
            }

        return result

    @staticmethod
    def _calc_percent(passed: int, total: int) -> float:
        return (passed / total * 100) if total > 0 else 0.0

    def get_metadata(self) -> IndicatorMetadata:
        """獲取指標元數據。"""
        return IndicatorMetadata(
            name="error_count",
            title="Interface Error 監控",
            description="監控設備 CRC 錯誤計數增量（任一介面兩次變化點之間有增長即異常）",
            object_type="device",
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
        offset: int = 0,
    ) -> list[RawDataRow]:
        """獲取最新原始數據。"""
        repo = InterfaceErrorRecordRepo(session)
        records = await repo.get_latest_records(
            maintenance_id=maintenance_id,
            limit=limit,
            offset=offset,
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
