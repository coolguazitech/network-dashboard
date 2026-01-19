"""
Client indicator evaluator.

評估網絡中客戶端設備的連接狀況。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClientRecord
from app.indicators.base import BaseIndicator, IndicatorEvaluationResult
from app.core.enums import MaintenancePhase


class ClientIndicator(BaseIndicator):
    """客戶端健康指標評估器。"""
    
    indicator_type = "client"
    
    # 閾值
    PING_LATENCY_MAX = 100.0  # ms
    MIN_LINK_SPEED = "1G"
    
    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
        phase: MaintenancePhase | None = None,
    ) -> IndicatorEvaluationResult:
        """
        評估客戶端健康狀況。
        """
        if phase is None:
            phase = MaintenancePhase.POST
        
        # 查詢所有指定階段的客戶端數據
        stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.phase == phase,
            )
            .order_by(ClientRecord.collected_at.desc())
        )
        result = await session.execute(stmt)
        all_records = result.scalars().all()
        
        # 按 MAC 地址去重，只保留最新記錄
        seen_macs = set()
        records = []
        for record in all_records:
            if record.mac_address not in seen_macs:
                records.append(record)
                seen_macs.add(record.mac_address)
        
        total_count = 0
        pass_count = 0
        failures = []
        
        # 遍歷每個客戶端
        for record in records:
            total_count += 1
            checks_passed = True
            failure_reasons = []
            
            # 檢查 Link 狀態
            if record.link_status != "up":
                checks_passed = False
                failure_reasons.append(f"Link 狀態異常: {record.link_status}")
            
            # 檢查 Ping 可達性
            if record.ping_reachable is False:
                checks_passed = False
                failure_reasons.append("無法 Ping 到客戶端")
            
            # 檢查 Ping 延遲
            if record.ping_latency_ms and record.ping_latency_ms > self.PING_LATENCY_MAX:
                checks_passed = False
                failure_reasons.append(f"Ping 延遲過高: {record.ping_latency_ms}ms (預期: < {self.PING_LATENCY_MAX}ms)")
            
            # 檢查 ACL
            if record.acl_passes is False:
                checks_passed = False
                failure_reasons.append("ACL 檢查未通過")
            
            # 檢查連接速度
            if record.speed and record.speed != self.MIN_LINK_SPEED:
                # 只警告，不失敗
                pass
            
            # 檢查 Duplex
            if record.duplex != "full":
                checks_passed = False
                failure_reasons.append(f"Duplex 異常: {record.duplex} (預期: full)")
            
            if checks_passed:
                pass_count += 1
            else:
                failures.append({
                    "device": record.switch_hostname,
                    "interface": record.interface_name,
                    "reason": " | ".join(failure_reasons),
                    "client_info": {
                        "mac": record.mac_address,
                        "ip": record.ip_address,
                        "hostname": record.hostname,
                        "vlan": record.vlan_id,
                    }
                })
        
        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            phase=phase,
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=total_count - pass_count,
            pass_rates={
                "client_health": (pass_count / total_count * 100) if total_count > 0 else 0
            },
            failures=failures if failures else None,
            summary=f"客戶端健康: {pass_count}/{total_count} 正常 "
                   f"({pass_count/total_count*100:.1f}%)" 
                   if total_count > 0 else "無客戶端數據"
        )


class ClientComparisonIndicator(BaseIndicator):
    """客戶端歲修前後比較指標評估器。
    
    比較同一個 MAC 地址在歲修前後的變化情況，包括：
    - 拓樸角色（access/trunk/uplink）
    - 連接的交換機和埠口
    - 連接速率、雙工模式
    - ACL 規則
    - Ping 可達性
    """
    
    indicator_type = "client_comparison"
    
    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
        phase: MaintenancePhase | None = None,
    ) -> IndicatorEvaluationResult:
        """
        評估客戶端歲修前後的變化。
        """
        from app.db.models import ClientComparison
        
        # 查詢所有比較結果
        stmt = select(ClientComparison).where(
            ClientComparison.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        comparisons = result.scalars().all()
        
        total_count = len(comparisons)
        unchanged_count = 0
        changed_count = 0
        critical_changes = []
        
        for comparison in comparisons:
            if not comparison.is_changed:
                unchanged_count += 1
            else:
                changed_count += 1
                
                # 評估變化的嚴重程度
                severity = comparison.severity or "info"
                if severity == "critical":
                    critical_changes.append({
                        "mac_address": comparison.mac_address,
                        "differences": comparison.differences,
                        "severity": severity,
                        "notes": comparison.notes,
                    })
        
        # 計算通過率 (未變化的為通過)
        pass_count = unchanged_count
        fail_count = changed_count
        pass_rate = (pass_count / total_count * 100) if total_count > 0 else 0
        
        return IndicatorEvaluationResult(
            indicator_type=self.indicator_type,
            phase=MaintenancePhase.POST,  # 比較結果總是 POST 階段
            maintenance_id=maintenance_id,
            total_count=total_count,
            pass_count=pass_count,
            fail_count=fail_count,
            pass_rates={
                "client_stability": pass_rate
            },
            failures=critical_changes if critical_changes else None,
            summary=f"客戶端穩定性: {pass_count}/{total_count} 未變化 "
                   f"({pass_rate:.1f}%)" 
                   if total_count > 0 else "無比較數據"
        )
