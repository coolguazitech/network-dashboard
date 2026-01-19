"""
Client comparison indicator evaluator.

比較歲修前後客戶端的變化情況。
"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClientRecord, ClientComparison
from app.indicators.base import BaseIndicator, IndicatorEvaluationResult
from app.core.enums import MaintenancePhase


class ComparisonIndicator(BaseIndicator):
    """客戶端歲修前後比較指標評估器。"""
    
    indicator_type = "comparison"
    
    # 定義要比較的欄位及其嚴重程度
    CRITICAL_FIELDS = {
        "switch_hostname",  # 拓樸角色變化
        "interface_name",   # 端口變化
        "link_status",      # 連接狀態變化
    }
    
    WARNING_FIELDS = {
        "speed",           # 速率變化
        "duplex",          # 雙工變化
        "acl_passes",      # ACL 狀態變化
        "ping_reachable",  # Ping 可達性變化
    }
    
    INFO_FIELDS = {
        "vlan_id",
        "ip_address",
        "hostname",
    }
    
    async def evaluate(
        self,
        maintenance_id: str,
        session: AsyncSession,
        phase: MaintenancePhase | None = None,
    ) -> IndicatorEvaluationResult:
        """
        比較歲修前後客戶端的變化。
        
        Args:
            maintenance_id: 歲修 ID
            session: 資料庫會話
            phase: 階段（此指標會同時查詢 PRE 和 POST，所以不使用此參數）
        """
        # 查詢 PRE 階段的所有客戶端
        pre_stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.phase == MaintenancePhase.PRE,
            )
            .order_by(ClientRecord.collected_at.desc())
        )
        pre_result = await session.execute(pre_stmt)
        pre_records = pre_result.scalars().all()
        
        # 按 MAC 地址去重，只保留最新記錄
        pre_records_dict = {}
        for record in pre_records:
            if record.mac_address not in pre_records_dict:
                pre_records_dict[record.mac_address] = record
        
        # 查詢 POST 階段的所有客戶端
        post_stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.phase == MaintenancePhase.POST,
            )
            .order_by(ClientRecord.collected_at.desc())
        )
        post_result = await session.execute(post_stmt)
        post_records = post_result.scalars().all()
        
        # 按 MAC 地址去重，只保留最新記錄
        post_records_dict = {}
        for record in post_records:
            if record.mac_address not in post_records_dict:
                post_records_dict[record.mac_address] = record
        
        # 比較邏輯
        total_count = 0
        changed_count = 0
        unchanged_count = 0
        no_pre_data = 0
        no_post_data = 0
        critical_issues = []
        warning_issues = []
        info_changes = []
        
        # 遍歷所有被追蹤的 MAC（取 PRE 和 POST 的並集）
        all_macs = set(pre_records_dict.keys()) | set(post_records_dict.keys())
        
        for mac in all_macs:
            total_count += 1
            pre_record = pre_records_dict.get(mac)
            post_record = post_records_dict.get(mac)
            
            # 準備比較數據
            differences = self._compare_records(pre_record, post_record)
            
            if not differences["changed"]:
                unchanged_count += 1
            else:
                changed_count += 1
                
                # 分類問題嚴重程度
                if differences["critical"]:
                    critical_issues.append({
                        "mac": mac,
                        "changes": differences["critical"],
                    })
                
                if differences["warning"]:
                    warning_issues.append({
                        "mac": mac,
                        "changes": differences["warning"],
                    })
                
                if differences["info"]:
                    info_changes.append({
                        "mac": mac,
                        "changes": differences["info"],
                    })
            
            # 記錄沒有的階段數據
            if not pre_record:
                no_pre_data += 1
            if not post_record:
                no_post_data += 1
            
            # 將比較結果存入資料庫
            await self._save_comparison(
                session,
                maintenance_id,
                mac,
                pre_record,
                post_record,
                differences,
            )
        
        # 構建評估結果
        pass_rate = (unchanged_count / total_count * 100) if total_count > 0 else 0
        
        details = {
            "total_clients": total_count,
            "unchanged_clients": unchanged_count,
            "changed_clients": changed_count,
            "no_pre_data": no_pre_data,
            "no_post_data": no_post_data,
            "critical_issues_count": len(critical_issues),
            "warning_issues_count": len(warning_issues),
            "info_changes_count": len(info_changes),
            "critical_issues": critical_issues[:10],  # 只顯示前 10 個
            "warning_issues": warning_issues[:10],
            "info_changes": info_changes[:10],
        }
        
        return IndicatorEvaluationResult(
            pass_count=unchanged_count,
            total_count=total_count,
            pass_rate=pass_rate,
            details=details,
        )
    
    def _compare_records(
        self,
        pre_record: ClientRecord | None,
        post_record: ClientRecord | None,
    ) -> dict:
        """比較 PRE 和 POST 記錄的差異。"""
        result = {
            "changed": False,
            "critical": [],
            "warning": [],
            "info": [],
        }
        
        if not pre_record or not post_record:
            result["changed"] = True
            if not pre_record:
                result["critical"].append("Missing PRE phase data")
            if not post_record:
                result["critical"].append("Missing POST phase data")
            return result
        
        # 比較所有字段
        field_mappings = {
            "switch_hostname": ("switch_hostname", "switch_hostname", self.CRITICAL_FIELDS),
            "interface_name": ("interface_name", "interface_name", self.CRITICAL_FIELDS),
            "link_status": ("link_status", "link_status", self.CRITICAL_FIELDS),
            "speed": ("speed", "speed", self.WARNING_FIELDS),
            "duplex": ("duplex", "duplex", self.WARNING_FIELDS),
            "acl_passes": ("acl_passes", "acl_passes", self.WARNING_FIELDS),
            "ping_reachable": ("ping_reachable", "ping_reachable", self.WARNING_FIELDS),
            "vlan_id": ("vlan_id", "vlan_id", self.INFO_FIELDS),
            "ip_address": ("ip_address", "ip_address", self.INFO_FIELDS),
            "hostname": ("hostname", "hostname", self.INFO_FIELDS),
        }
        
        for field_name, (pre_attr, post_attr, severity_set) in field_mappings.items():
            pre_value = getattr(pre_record, pre_attr, None)
            post_value = getattr(post_record, post_attr, None)
            
            if pre_value != post_value:
                result["changed"] = True
                change_info = {
                    "field": field_name,
                    "pre": pre_value,
                    "post": post_value,
                }
                
                if field_name in self.CRITICAL_FIELDS:
                    result["critical"].append(change_info)
                elif field_name in self.WARNING_FIELDS:
                    result["warning"].append(change_info)
                else:
                    result["info"].append(change_info)
        
        return result
    
    async def _save_comparison(
        self,
        session: AsyncSession,
        maintenance_id: str,
        mac_address: str,
        pre_record: ClientRecord | None,
        post_record: ClientRecord | None,
        differences: dict,
    ) -> None:
        """將比較結果保存到資料庫。"""
        
        # 確定嚴重程度
        severity = "info"
        if differences["critical"]:
            severity = "critical"
        elif differences["warning"]:
            severity = "warning"
        
        # 建立比較記錄
        comparison = ClientComparison(
            maintenance_id=maintenance_id,
            mac_address=mac_address,
            # PRE 數據
            pre_ip_address=pre_record.ip_address if pre_record else None,
            pre_hostname=pre_record.hostname if pre_record else None,
            pre_switch_hostname=pre_record.switch_hostname if pre_record else None,
            pre_interface_name=pre_record.interface_name if pre_record else None,
            pre_vlan_id=pre_record.vlan_id if pre_record else None,
            pre_speed=pre_record.speed if pre_record else None,
            pre_duplex=pre_record.duplex if pre_record else None,
            pre_link_status=pre_record.link_status if pre_record else None,
            pre_ping_reachable=pre_record.ping_reachable if pre_record else None,
            pre_ping_latency_ms=pre_record.ping_latency_ms if pre_record else None,
            pre_acl_passes=pre_record.acl_passes if pre_record else None,
            # POST 數據
            post_ip_address=post_record.ip_address if post_record else None,
            post_hostname=post_record.hostname if post_record else None,
            post_switch_hostname=post_record.switch_hostname if post_record else None,
            post_interface_name=post_record.interface_name if post_record else None,
            post_vlan_id=post_record.vlan_id if post_record else None,
            post_speed=post_record.speed if post_record else None,
            post_duplex=post_record.duplex if post_record else None,
            post_link_status=post_record.link_status if post_record else None,
            post_ping_reachable=post_record.ping_reachable if post_record else None,
            post_ping_latency_ms=post_record.ping_latency_ms if post_record else None,
            post_acl_passes=post_record.acl_passes if post_record else None,
            # 比較結果
            differences=differences,
            is_changed=differences["changed"],
            severity=severity,
        )
        
        session.add(comparison)
