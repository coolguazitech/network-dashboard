"""
Port-Channel indicator evaluator.

Evaluates if Port-Channels match the expected configuration and status.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import MaintenancePhase
from app.db.models import CollectionRecord, PortChannelExpectation
from app.indicators.base import (
    BaseIndicator,
    IndicatorEvaluationResult,
    IndicatorMetadata,
    ObservedField,
    DisplayConfig,
    TimeSeriesPoint,
    RawDataRow,
)


class PortChannelIndicator(BaseIndicator):
    """
    Port-Channel 指標評估器。
    
    檢查項目：
    1. Port-Channel 是否存在且狀態為 UP
    2. 成員介面是否完全匹配期望清單
    3. 所有成員介面狀態是否正常 (UP/Bundled)
    """
    
    indicator_type = "port_channel"
    
    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
        phase: MaintenancePhase | None = None,
    ) -> IndicatorEvaluationResult:
        """
        評估 Port-Channel 指標。
        
        Args:
            maintenance_id: 維護作業 ID
            session: 資料庫 session
            phase: 階段 (OLD 或 NEW)，預設 NEW
        """
        if phase is None:
            phase = MaintenancePhase.NEW
            
        # 1. 獲取所有期望設定
        stmt_exp = select(PortChannelExpectation).where(
            PortChannelExpectation.maintenance_id == maintenance_id
        )
        result_exp = await session.execute(stmt_exp)
        expectations = result_exp.scalars().all()
        
        # 建立期望查找表: hostname -> {pc_name: expectation}
        exp_map = {}
        for exp in expectations:
            if exp.hostname not in exp_map:
                exp_map[exp.hostname] = {}
            # Normalize PC name (optional logic here, e.g. Po1 vs Port-channel1)
            # For now assume exact match or simple normalization in parser
            exp_map[exp.hostname][exp.port_channel] = exp
            
        # 2. 獲取實際採集數據
        stmt_data = (
            select(CollectionRecord)
            .where(
                CollectionRecord.indicator_type == "port_channel",
                CollectionRecord.phase == phase,
                CollectionRecord.maintenance_id == maintenance_id,
            )
            .order_by(CollectionRecord.collected_at.desc())
        )
        result_data = await session.execute(stmt_data)
        all_records = result_data.scalars().all()
        
        # 按設備去重
        seen_devices = set()
        records = {}
        for record in all_records:
            if record.switch_hostname not in seen_devices:
                records[record.switch_hostname] = record
                seen_devices.add(record.switch_hostname)
                
        total_count = 0
        pass_count = 0
        failures = []
        
        # 3. 逐一評估每個期望
        for hostname, pcs in exp_map.items():
            record = records.get(hostname)
            
            if not record or not record.parsed_data:
                # 該設備無數據
                for pc_name in pcs:
                    total_count += 1
                    failures.append({
                        "device": hostname,
                        "interface": pc_name,
                        "reason": "無採集數據",
                        "data": None
                    })
                continue
                
            # 將實際數據轉為 map: pc_name -> data
            actual_pcs = {}
            if record.parsed_data and "items" in record.parsed_data:
                for item in record.parsed_data["items"]:
                    actual_pcs[item["interface_name"]] = item
            elif isinstance(record.parsed_data, list):
                 for item in record.parsed_data:
                    actual_pcs[item["interface_name"]] = item
            
            for pc_name, exp in pcs.items():
                total_count += 1
                
                # 嘗試查找實際 PC (支援簡單的名稱匹配 Po1 == Port-channel1)
                actual = actual_pcs.get(pc_name)
                if not actual:
                    # 嘗試標準化匹配
                    # 例如期望是 Po1，實際是 Port-channel1
                    for k, v in actual_pcs.items():
                        if self._normalize_name(k) == self._normalize_name(pc_name):
                            actual = v
                            break
                
                if not actual:
                    failures.append({
                        "device": hostname,
                        "interface": pc_name,
                        "reason": "Port-Channel 不存在",
                        "data": None
                    })
                    continue
                
                # 檢查 PC 狀態
                if actual["status"] != "UP":
                    failures.append({
                        "device": hostname,
                        "interface": pc_name,
                        "reason": f"Port-Channel 狀態異常: {actual['status']}",
                        "data": actual
                    })
                    continue
                
                # 檢查成員
                expected_members = set(
                    m.strip() for m in exp.member_interfaces.split(";") if m.strip()
                )
                actual_members = set(actual["members"])
                
                # 檢查成員是否一致
                missing = expected_members - actual_members
                extra = actual_members - expected_members
                
                if missing:
                    failures.append({
                        "device": hostname,
                        "interface": pc_name,
                        "reason": f"成員缺失: {', '.join(missing)}",
                        "data": actual
                    })
                    continue
                
                # 檢查成員狀態
                member_issues = []
                if "member_status" in actual and actual["member_status"]:
                    for m, status in actual["member_status"].items():
                        if status != "UP":
                            member_issues.append(f"{m}({status})")
                
                if member_issues:
                    failures.append({
                        "device": hostname,
                        "interface": pc_name,
                        "reason": f"成員狀態異常: {', '.join(member_issues)}",
                        "data": actual
                    })
                    continue
                
                # 通過所有檢查
                pass_count += 1
        
        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            phase=phase,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "status_ok": self._calc_percent(pass_count, total_count)
            },
            failures=failures if failures else None,
            summary=f"Port-Channel: {pass_count}/{total_count} 通過"
        )

    def _normalize_name(self, name: str) -> str:
        """Normalize interface name for comparison."""
        name = name.lower()
        name = name.replace("port-channel", "po")
        name = name.replace("bridge-aggregation", "bagg")
        return name

    @staticmethod
    def _calc_percent(passed: int, total: int) -> float:
        return (passed / total * 100) if total > 0 else 0.0

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

    async def get_time_series(
        self,
        limit: int,
        session: AsyncSession,
        maintenance_id: str,
        phase: MaintenancePhase = MaintenancePhase.NEW,
    ) -> list[TimeSeriesPoint]:
        """獲取時間序列數據。"""
        stmt = (
            select(CollectionRecord)
            .where(
                CollectionRecord.indicator_type == "port_channel",
                CollectionRecord.phase == phase,
                CollectionRecord.maintenance_id == maintenance_id,
            )
            .order_by(CollectionRecord.collected_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        records = result.scalars().all()

        time_series = []
        for record in reversed(records):
            if not record.parsed_data:
                continue

            items = []
            if record.parsed_data and "items" in record.parsed_data:
                items = record.parsed_data["items"]
            elif isinstance(record.parsed_data, list):
                items = record.parsed_data

            up_count = sum(1 for item in items if item.get("status") == "UP")
            up_rate = (up_count / len(items) * 100) if items else 0.0

            time_series.append(
                TimeSeriesPoint(
                    timestamp=record.collected_at,
                    values={"pc_status": up_rate},
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
        stmt = (
            select(CollectionRecord)
            .where(
                CollectionRecord.indicator_type == "port_channel",
                CollectionRecord.phase == phase,
                CollectionRecord.maintenance_id == maintenance_id,
            )
            .order_by(CollectionRecord.collected_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        records = result.scalars().all()

        raw_data = []
        for record in records:
            if not record.parsed_data:
                continue

            items = []
            if record.parsed_data and "items" in record.parsed_data:
                items = record.parsed_data["items"]
            elif isinstance(record.parsed_data, list):
                items = record.parsed_data

            for item in items:
                raw_data.append(
                    RawDataRow(
                        switch_hostname=record.switch_hostname,
                        interface_name=item.get("interface_name"),
                        status=item.get("status"),
                        members=item.get("members"),
                        collected_at=record.collected_at,
                    )
                )

        return raw_data[:limit]
