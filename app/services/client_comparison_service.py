"""
Client comparison service.

比較客戶端在歲修前後的變化。
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClientRecord, ClientComparison
from app.core.enums import MaintenancePhase


class ClientComparisonService:
    """客戶端比較服務。
    
    比較同一個 MAC 地址在歲修前後的變化情況，包括：
    - 拓樸角色（access/trunk/uplink）
    - 連接的交換機和埠口
    - 連接速率、雙工模式
    - ACL 規則
    - Ping 可達性和延遲
    """
    
    def __init__(self):
        """初始化並載入配置。"""
        self._load_config()
    
    def _load_config(self):
        """從 YAML 配置文件載入嚴重程度定義。"""
        config_path = Path(__file__).parent.parent.parent / "config" / "client_comparison.yaml"
        
        # 預設值（如果配置文件不存在）
        default_config = {
            "critical_fields": [
                "switch_hostname",
                "interface_name",
                "topology_role",
                "link_status",
                "ping_reachable",
                "acl_passes",
            ],
            "warning_fields": [
                "speed",
                "duplex",
                "vlan_id",
                "ping_latency_ms",
            ],
            "ping_latency_threshold_ms": 10.0,
        }
        
        try:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                    self.CRITICAL_FIELDS = set(config.get("critical_fields", default_config["critical_fields"]))
                    self.WARNING_FIELDS = set(config.get("warning_fields", default_config["warning_fields"]))
                    self.PING_LATENCY_THRESHOLD = config.get("ping_latency_threshold_ms", default_config["ping_latency_threshold_ms"])
            else:
                # 使用預設值
                self.CRITICAL_FIELDS = set(default_config["critical_fields"])
                self.WARNING_FIELDS = set(default_config["warning_fields"])
                self.PING_LATENCY_THRESHOLD = default_config["ping_latency_threshold_ms"]
        except Exception as e:
            print(f"Warning: Failed to load client comparison config: {e}")
            # 發生錯誤時使用預設值
            self.CRITICAL_FIELDS = set(default_config["critical_fields"])
            self.WARNING_FIELDS = set(default_config["warning_fields"])
            self.PING_LATENCY_THRESHOLD = default_config["ping_latency_threshold_ms"]
    
    async def generate_comparisons(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> list[ClientComparison]:
        """
        生成客戶端比較結果。
        
        查詢同一個 MAC 地址在 PRE 和 POST 階段的記錄，比較差異。
        """
        # 查詢 PRE 階段的記錄，按 MAC 地址分組，只保留最新的
        pre_stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.phase == MaintenancePhase.PRE,
            )
            .order_by(ClientRecord.mac_address, ClientRecord.collected_at.desc())
        )
        pre_result = await session.execute(pre_stmt)
        pre_records = pre_result.scalars().all()
        
        # 按 MAC 地址分組，只保留最新記錄
        pre_by_mac = {}
        for record in pre_records:
            if record.mac_address not in pre_by_mac:
                pre_by_mac[record.mac_address] = record
        
        # 查詢 POST 階段的記錄，按 MAC 地址分組，只保留最新的
        post_stmt = (
            select(ClientRecord)
            .where(
                ClientRecord.maintenance_id == maintenance_id,
                ClientRecord.phase == MaintenancePhase.POST,
            )
            .order_by(ClientRecord.mac_address, ClientRecord.collected_at.desc())
        )
        post_result = await session.execute(post_stmt)
        post_records = post_result.scalars().all()
        
        # 按 MAC 地址分組，只保留最新記錄
        post_by_mac = {}
        for record in post_records:
            if record.mac_address not in post_by_mac:
                post_by_mac[record.mac_address] = record
        
        # 生成比較結果
        comparisons = []
        all_macs = set(pre_by_mac.keys()) | set(post_by_mac.keys())
        
        for mac in all_macs:
            pre_record = pre_by_mac.get(mac)
            post_record = post_by_mac.get(mac)
            
            # 建立比較記錄
            comparison = ClientComparison(
                maintenance_id=maintenance_id,
                collected_at=datetime.utcnow(),
                mac_address=mac,
            )
            
            # 添加 PRE 階段數據
            if pre_record:
                comparison.pre_ip_address = pre_record.ip_address
                comparison.pre_hostname = pre_record.hostname
                comparison.pre_switch_hostname = pre_record.switch_hostname
                comparison.pre_interface_name = pre_record.interface_name
                comparison.pre_vlan_id = pre_record.vlan_id
                comparison.pre_speed = pre_record.speed
                comparison.pre_duplex = pre_record.duplex
                comparison.pre_link_status = pre_record.link_status
                comparison.pre_ping_reachable = pre_record.ping_reachable
                comparison.pre_ping_latency_ms = pre_record.ping_latency_ms
                comparison.pre_acl_passes = pre_record.acl_passes
                
                # 嘗試從 parsed_data 中提取 topology_role
                if pre_record.parsed_data and "topology_role" in pre_record.parsed_data:
                    comparison.pre_topology_role = pre_record.parsed_data["topology_role"]
            
            # 添加 POST 階段數據
            if post_record:
                comparison.post_ip_address = post_record.ip_address
                comparison.post_hostname = post_record.hostname
                comparison.post_switch_hostname = post_record.switch_hostname
                comparison.post_interface_name = post_record.interface_name
                comparison.post_vlan_id = post_record.vlan_id
                comparison.post_speed = post_record.speed
                comparison.post_duplex = post_record.duplex
                comparison.post_link_status = post_record.link_status
                comparison.post_ping_reachable = post_record.ping_reachable
                comparison.post_ping_latency_ms = post_record.ping_latency_ms
                comparison.post_acl_passes = post_record.acl_passes
                
                # 嘗試從 parsed_data 中提取 topology_role
                if post_record.parsed_data and "topology_role" in post_record.parsed_data:
                    comparison.post_topology_role = post_record.parsed_data["topology_role"]
            
            # 比較差異
            differences = self._find_differences(comparison)
            comparison.differences = differences
            
            # 判斷是否有變化和嚴重程度
            if differences:
                comparison.is_changed = True
                comparison.severity = self._calculate_severity(differences)
                comparison.notes = self._generate_notes(comparison, differences)
            else:
                comparison.is_changed = False
                comparison.severity = "info"
                comparison.notes = "未檢測到變化"
            
            comparisons.append(comparison)
        
        return comparisons
    
    def _find_differences(self, comparison: ClientComparison) -> dict[str, Any]:
        """找出比較記錄中的差異。"""
        differences = {}
        
        # 定義要比較的欄位對
        fields_to_compare = [
            ("pre_switch_hostname", "post_switch_hostname", "switch_hostname"),
            ("pre_interface_name", "post_interface_name", "interface_name"),
            ("pre_topology_role", "post_topology_role", "topology_role"),
            ("pre_vlan_id", "post_vlan_id", "vlan_id"),
            ("pre_speed", "post_speed", "speed"),
            ("pre_duplex", "post_duplex", "duplex"),
            ("pre_link_status", "post_link_status", "link_status"),
            ("pre_ping_reachable", "post_ping_reachable", "ping_reachable"),
            ("pre_ping_latency_ms", "post_ping_latency_ms", "ping_latency_ms"),
            ("pre_acl_passes", "post_acl_passes", "acl_passes"),
            ("pre_ip_address", "post_ip_address", "ip_address"),
            ("pre_hostname", "post_hostname", "hostname"),
        ]
        
        for pre_field, post_field, field_name in fields_to_compare:
            pre_value = getattr(comparison, pre_field, None)
            post_value = getattr(comparison, post_field, None)
            
            # 檢查是否有實際變化（忽略 None 值的比較）
            if pre_value != post_value:
                # 特殊處理 ping_latency_ms，只有差異超過閾值才記錄
                if field_name == "ping_latency_ms":
                    if pre_value is not None and post_value is not None:
                        if abs(pre_value - post_value) > self.PING_LATENCY_THRESHOLD:
                            differences[field_name] = {
                                "pre": pre_value,
                                "post": post_value,
                                "change": post_value - pre_value,
                            }
                # 對於布林值，只有都不為 None 時才比較
                elif field_name in ("ping_reachable", "acl_passes"):
                    if pre_value is not None and post_value is not None and pre_value != post_value:
                        differences[field_name] = {
                            "pre": pre_value,
                            "post": post_value,
                        }
                # 其他字符串字段，只有都不為 None 時才比較
                elif pre_value is not None and post_value is not None:
                    differences[field_name] = {
                        "pre": pre_value,
                        "post": post_value,
                    }
        
        return differences
    
    def _calculate_severity(self, differences: dict[str, Any]) -> str:
        """基於差異類型計算嚴重程度。"""
        diff_keys = set(differences.keys())
        
        # 如果包含 critical 欄位，則為 critical
        if diff_keys & self.CRITICAL_FIELDS:
            return "critical"
        
        # 如果包含 warning 欄位，則為 warning
        if diff_keys & self.WARNING_FIELDS:
            return "warning"
        
        return "info"
    
    def _generate_notes(
        self,
        comparison: ClientComparison,
        differences: dict[str, Any],
    ) -> str:
        """生成比較結果的註釋。"""
        notes = []
        
        for field_name, change_info in differences.items():
            if field_name in self.CRITICAL_FIELDS:
                prefix = "⚠️ CRITICAL: "
            elif field_name in self.WARNING_FIELDS:
                prefix = "⚠️ WARNING: "
            else:
                prefix = "ℹ️ INFO: "
            
            pre_val = change_info.get("pre")
            post_val = change_info.get("post")
            
            if field_name == "ping_latency_ms":
                change = change_info.get("change", 0)
                notes.append(f"{prefix}{field_name}: {pre_val}ms → {post_val}ms (變化: {change:+.1f}ms)")
            else:
                notes.append(f"{prefix}{field_name}: {pre_val} → {post_val}")
        
        return " | ".join(notes) if notes else "未檢測到變化"
    
    async def save_comparisons(
        self,
        comparisons: list[ClientComparison],
        session: AsyncSession,
    ) -> None:
        """保存比較結果到資料庫。"""
        # 先刪除舊的比較結果（如果需要）
        if comparisons:
            maintenance_id = comparisons[0].maintenance_id
            stmt = select(ClientComparison).where(
                ClientComparison.maintenance_id == maintenance_id
            )
            result = await session.execute(stmt)
            old_comparisons = result.scalars().all()
            for old in old_comparisons:
                await session.delete(old)
        
        # 添加新的比較結果
        for comparison in comparisons:
            session.add(comparison)
        
        await session.commit()
    
    async def get_comparisons(
        self,
        maintenance_id: str,
        session: AsyncSession,
        search_text: str | None = None,
        severity: str | None = None,
        changed_only: bool = False,
    ) -> list[ClientComparison]:
        """
        查詢比較結果。
        
        支持按 MAC 地址、IP 地址、嚴重程度和是否變化進行篩選。
        """
        from sqlalchemy import or_
        
        stmt = select(ClientComparison).where(
            ClientComparison.maintenance_id == maintenance_id
        )
        
        if search_text:
            # 搜尋 MAC 地址或 IP 地址（PRE 或 POST 階段）
            search_pattern = f"%{search_text}%"
            stmt = stmt.where(
                or_(
                    ClientComparison.mac_address.ilike(search_pattern),
                    ClientComparison.pre_ip_address.ilike(search_pattern),
                    ClientComparison.post_ip_address.ilike(search_pattern),
                )
            )
        
        if severity:
            stmt = stmt.where(ClientComparison.severity == severity)
        
        if changed_only:
            stmt = stmt.where(ClientComparison.is_changed == True)
        
        stmt = stmt.order_by(ClientComparison.collected_at.desc())
        
        result = await session.execute(stmt)
        return result.scalars().all()
    
    async def get_comparison_summary(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> dict[str, Any]:
        """獲取比較結果的摘要統計。"""
        comparisons = await self.get_comparisons(
            maintenance_id=maintenance_id,
            session=session,
        )
        
        total = len(comparisons)
        unchanged = sum(1 for c in comparisons if not c.is_changed)
        changed = sum(1 for c in comparisons if c.is_changed)
        critical = sum(1 for c in comparisons if c.severity == "critical")
        warning = sum(1 for c in comparisons if c.severity == "warning")
        
        return {
            "total": total,
            "unchanged": unchanged,
            "changed": changed,
            "unchanged_rate": (unchanged / total * 100) if total > 0 else 0,
            "changed_rate": (changed / total * 100) if total > 0 else 0,
            "critical": critical,
            "warning": warning,
            "info": total - critical - warning - unchanged,
        }
