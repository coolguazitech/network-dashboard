"""
Client comparison service.

提供客戶端比較功能的業務邏輯。
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import and_, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ClientComparison, IndicatorResult
from app.indicators.comparison import ComparisonIndicator
from app.core.enums import MaintenancePhase


class ClientComparisonService:
    """客戶端比較服務。"""
    
    def __init__(self):
        self.comparison_indicator = ComparisonIndicator()
    
    async def evaluate_comparison(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> dict:
        """
        評估客戶端比較。
        
        Args:
            maintenance_id: 歲修 ID
            session: 資料庫會話
            
        Returns:
            評估結果
        """
        # 使用指標評估器進行比較
        result = await self.comparison_indicator.evaluate(
            maintenance_id=maintenance_id,
            session=session,
        )
        
        # 提交資料庫更改
        await session.commit()
        
        # 存儲指標結果
        indicator_result = IndicatorResult(
            indicator_type="comparison",
            pass_rates={"unchanged": result.pass_rate},
            total_count=result.total_count,
            pass_count=result.pass_count,
            fail_count=result.total_count - result.pass_count,
            maintenance_id=maintenance_id,
            details=result.details,
        )
        session.add(indicator_result)
        await session.commit()
        
        return {
            "maintenance_id": maintenance_id,
            "pass_rate": result.pass_rate,
            "details": result.details,
        }
    
    async def get_comparison_summary(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> dict:
        """
        取得客戶端比較摘要。
        
        Args:
            maintenance_id: 歲修 ID
            session: 資料庫會話
            
        Returns:
            摘要數據
        """
        stmt = select(ClientComparison).where(
            ClientComparison.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        comparisons = result.scalars().all()
        
        total = len(comparisons)
        changed = sum(1 for c in comparisons if c.is_changed)
        critical = sum(1 for c in comparisons if c.severity == "critical")
        warning = sum(1 for c in comparisons if c.severity == "warning")
        
        return {
            "total_clients": total,
            "changed_clients": changed,
            "unchanged_clients": total - changed,
            "critical_issues": critical,
            "warning_issues": warning,
            "change_rate": (changed / total * 100) if total > 0 else 0,
        }
    
    async def get_comparison_details(
        self,
        maintenance_id: str,
        session: AsyncSession,
        severity_filter: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        """
        取得詳細的客戶端比較結果。
        
        Args:
            maintenance_id: 歲修 ID
            session: 資料庫會話
            severity_filter: 嚴重程度過濾 (critical, warning, info)
            limit: 限制數量
            offset: 偏移量
            
        Returns:
            比較結果列表
        """
        stmt = select(ClientComparison).where(
            ClientComparison.maintenance_id == maintenance_id
        )
        
        # 只顯示有變化的
        stmt = stmt.where(ClientComparison.is_changed == True)
        
        if severity_filter:
            stmt = stmt.where(ClientComparison.severity == severity_filter)
        
        stmt = stmt.order_by(desc(ClientComparison.collected_at))
        stmt = stmt.limit(limit).offset(offset)
        
        result = await session.execute(stmt)
        comparisons = result.scalars().all()
        
        return [
            {
                "mac_address": c.mac_address,
                "severity": c.severity,
                "is_changed": c.is_changed,
                "pre": {
                    "ip": c.pre_ip_address,
                    "hostname": c.pre_hostname,
                    "switch": c.pre_switch_hostname,
                    "interface": c.pre_interface_name,
                    "vlan": c.pre_vlan_id,
                    "speed": c.pre_speed,
                    "duplex": c.pre_duplex,
                    "link_status": c.pre_link_status,
                    "ping_reachable": c.pre_ping_reachable,
                    "ping_latency": c.pre_ping_latency_ms,
                    "acl_passes": c.pre_acl_passes,
                },
                "post": {
                    "ip": c.post_ip_address,
                    "hostname": c.post_hostname,
                    "switch": c.post_switch_hostname,
                    "interface": c.post_interface_name,
                    "vlan": c.post_vlan_id,
                    "speed": c.post_speed,
                    "duplex": c.post_duplex,
                    "link_status": c.post_link_status,
                    "ping_reachable": c.post_ping_reachable,
                    "ping_latency": c.post_ping_latency_ms,
                    "acl_passes": c.post_acl_passes,
                },
                "differences": c.differences,
                "collected_at": c.collected_at.isoformat() if c.collected_at else None,
            }
            for c in comparisons
        ]
    
    async def get_client_comparison(
        self,
        maintenance_id: str,
        mac_address: str,
        session: AsyncSession,
    ) -> dict | None:
        """
        取得單個客戶端的比較結果。
        
        Args:
            maintenance_id: 歲修 ID
            mac_address: MAC 地址
            session: 資料庫會話
            
        Returns:
            比較結果或 None
        """
        stmt = select(ClientComparison).where(
            and_(
                ClientComparison.maintenance_id == maintenance_id,
                ClientComparison.mac_address == mac_address,
            )
        )
        result = await session.execute(stmt)
        comparison = result.scalars().first()
        
        if not comparison:
            return None
        
        return {
            "mac_address": comparison.mac_address,
            "severity": comparison.severity,
            "is_changed": comparison.is_changed,
            "pre": {
                "ip": comparison.pre_ip_address,
                "hostname": comparison.pre_hostname,
                "switch": comparison.pre_switch_hostname,
                "interface": comparison.pre_interface_name,
                "vlan": comparison.pre_vlan_id,
                "speed": comparison.pre_speed,
                "duplex": comparison.pre_duplex,
                "link_status": comparison.pre_link_status,
                "ping_reachable": comparison.pre_ping_reachable,
                "ping_latency": comparison.pre_ping_latency_ms,
                "acl_passes": comparison.pre_acl_passes,
            },
            "post": {
                "ip": comparison.post_ip_address,
                "hostname": comparison.post_hostname,
                "switch": comparison.post_switch_hostname,
                "interface": comparison.post_interface_name,
                "vlan": comparison.post_vlan_id,
                "speed": comparison.post_speed,
                "duplex": comparison.post_duplex,
                "link_status": comparison.post_link_status,
                "ping_reachable": comparison.post_ping_reachable,
                "ping_latency": comparison.post_ping_latency_ms,
                "acl_passes": comparison.post_acl_passes,
            },
            "differences": comparison.differences,
            "collected_at": comparison.collected_at.isoformat() if comparison.collected_at else None,
        }
    
    async def get_affected_fields_summary(
        self,
        maintenance_id: str,
        session: AsyncSession,
    ) -> dict:
        """
        取得受影響欄位的摘要統計。
        
        Args:
            maintenance_id: 歲修 ID
            session: 資料庫會話
            
        Returns:
            欄位變化統計
        """
        stmt = select(ClientComparison).where(
            and_(
                ClientComparison.maintenance_id == maintenance_id,
                ClientComparison.is_changed == True,
            )
        )
        result = await session.execute(stmt)
        comparisons = result.scalars().all()
        
        field_changes = {
            "switch_hostname": 0,
            "interface_name": 0,
            "link_status": 0,
            "speed": 0,
            "duplex": 0,
            "ping_reachable": 0,
            "ping_latency": 0,
            "acl_passes": 0,
            "vlan_id": 0,
            "ip_address": 0,
            "hostname": 0,
        }
        
        for comparison in comparisons:
            if not comparison.differences:
                continue
            
            for change in comparison.differences.get("critical", []):
                field = change.get("field")
                if field in field_changes:
                    field_changes[field] += 1
            
            for change in comparison.differences.get("warning", []):
                field = change.get("field")
                if field in field_changes:
                    field_changes[field] += 1
            
            for change in comparison.differences.get("info", []):
                field = change.get("field")
                if field in field_changes:
                    field_changes[field] += 1
        
        return {field: count for field, count in field_changes.items() if count > 0}
