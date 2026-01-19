"""
Client comparison endpoints.

客戶端歲修前後比較的 API 端點。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_async_session
from app.services.client_comparison_service import ClientComparisonService
from app.core.enums import MaintenancePhase


router = APIRouter(
    prefix="/comparisons",
    tags=["comparisons"],
)

comparison_service = ClientComparisonService()


@router.post("/generate/{maintenance_id}")
async def generate_comparisons(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    生成客戶端比較結果。
    
    比較指定維護 ID 下，所有客戶端在 PRE 和 POST 階段的變化。
    """
    try:
        # 生成比較結果
        comparisons = await comparison_service.generate_comparisons(
            maintenance_id=maintenance_id,
            session=session,
        )
        
        # 保存到資料庫
        await comparison_service.save_comparisons(
            comparisons=comparisons,
            session=session,
        )
        
        # 生成摘要
        summary = await comparison_service.get_comparison_summary(
            maintenance_id=maintenance_id,
            session=session,
        )
        
        return {
            "success": True,
            "maintenance_id": maintenance_id,
            "comparisons_count": len(comparisons),
            "summary": summary,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"生成比較結果失敗: {str(e)}",
        )


@router.get("/summary/{maintenance_id}")
async def get_comparison_summary(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    獲取客戶端比較結果的摘要。
    
    返回統計信息：總數、未變化數、變化數、嚴重程度分布等。
    """
    try:
        summary = await comparison_service.get_comparison_summary(
            maintenance_id=maintenance_id,
            session=session,
        )
        
        return {
            "success": True,
            "maintenance_id": maintenance_id,
            "summary": summary,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"獲取摘要失敗: {str(e)}",
        )


@router.get("/list/{maintenance_id}")
async def list_comparisons(
    maintenance_id: str,
    mac_address: str | None = Query(None, description="按 MAC 地址篩選"),
    severity: str | None = Query(None, description="按嚴重程度篩選 (critical/warning/info)"),
    changed_only: bool = Query(False, description="只返回有變化的結果"),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    列出客戶端比較結果。
    
    支持按 MAC 地址、嚴重程度和是否變化進行篩選。
    """
    try:
        comparisons = await comparison_service.get_comparisons(
            maintenance_id=maintenance_id,
            session=session,
            mac_address=mac_address,
            severity=severity,
            changed_only=changed_only,
        )
        
        # 轉換為字典格式
        results = []
        for comp in comparisons:
            results.append({
                "id": comp.id,
                "mac_address": comp.mac_address,
                "is_changed": comp.is_changed,
                "severity": comp.severity,
                "differences": comp.differences,
                "notes": comp.notes,
                "pre": {
                    "ip_address": comp.pre_ip_address,
                    "hostname": comp.pre_hostname,
                    "switch_hostname": comp.pre_switch_hostname,
                    "interface_name": comp.pre_interface_name,
                    "vlan_id": comp.pre_vlan_id,
                    "topology_role": comp.pre_topology_role,
                    "speed": comp.pre_speed,
                    "duplex": comp.pre_duplex,
                    "link_status": comp.pre_link_status,
                    "ping_reachable": comp.pre_ping_reachable,
                    "ping_latency_ms": comp.pre_ping_latency_ms,
                    "acl_passes": comp.pre_acl_passes,
                },
                "post": {
                    "ip_address": comp.post_ip_address,
                    "hostname": comp.post_hostname,
                    "switch_hostname": comp.post_switch_hostname,
                    "interface_name": comp.post_interface_name,
                    "vlan_id": comp.post_vlan_id,
                    "topology_role": comp.post_topology_role,
                    "speed": comp.post_speed,
                    "duplex": comp.post_duplex,
                    "link_status": comp.post_link_status,
                    "ping_reachable": comp.post_ping_reachable,
                    "ping_latency_ms": comp.post_ping_latency_ms,
                    "acl_passes": comp.post_acl_passes,
                },
                "collected_at": comp.collected_at.isoformat() if comp.collected_at else None,
            })
        
        return {
            "success": True,
            "maintenance_id": maintenance_id,
            "count": len(results),
            "results": results,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"列出比較結果失敗: {str(e)}",
        )


@router.get("/detail/{maintenance_id}/{mac_address}")
async def get_comparison_detail(
    maintenance_id: str,
    mac_address: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    獲取單個客戶端的詳細比較結果。
    """
    try:
        comparisons = await comparison_service.get_comparisons(
            maintenance_id=maintenance_id,
            session=session,
            mac_address=mac_address,
        )
        
        if not comparisons:
            raise HTTPException(
                status_code=404,
                detail=f"未找到 MAC 地址為 {mac_address} 的比較記錄",
            )
        
        comp = comparisons[0]
        
        return {
            "success": True,
            "maintenance_id": maintenance_id,
            "mac_address": mac_address,
            "is_changed": comp.is_changed,
            "severity": comp.severity,
            "differences": comp.differences,
            "notes": comp.notes,
            "pre": {
                "ip_address": comp.pre_ip_address,
                "hostname": comp.pre_hostname,
                "switch_hostname": comp.pre_switch_hostname,
                "interface_name": comp.pre_interface_name,
                "vlan_id": comp.pre_vlan_id,
                "topology_role": comp.pre_topology_role,
                "speed": comp.pre_speed,
                "duplex": comp.pre_duplex,
                "link_status": comp.pre_link_status,
                "ping_reachable": comp.pre_ping_reachable,
                "ping_latency_ms": comp.pre_ping_latency_ms,
                "acl_passes": comp.pre_acl_passes,
            },
            "post": {
                "ip_address": comp.post_ip_address,
                "hostname": comp.post_hostname,
                "switch_hostname": comp.post_switch_hostname,
                "interface_name": comp.post_interface_name,
                "vlan_id": comp.post_vlan_id,
                "topology_role": comp.post_topology_role,
                "speed": comp.post_speed,
                "duplex": comp.post_duplex,
                "link_status": comp.post_link_status,
                "ping_reachable": comp.post_ping_reachable,
                "ping_latency_ms": comp.post_ping_latency_ms,
                "acl_passes": comp.post_acl_passes,
            },
            "collected_at": comp.collected_at.isoformat() if comp.collected_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"獲取詳細比較結果失敗: {str(e)}",
        )
