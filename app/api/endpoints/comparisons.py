"""
Client comparison endpoints.

客戶端歲修前後比較的 API 端點。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.db.base import get_async_session
from app.db.models import SeverityOverride
from app.services.client_comparison_service import ClientComparisonService
from app.core.enums import MaintenancePhase


class SeverityOverrideCreate(BaseModel):
    """創建嚴重程度覆蓋的請求模型。"""
    mac_address: str
    override_severity: str  # 'critical', 'warning', 'info'
    original_severity: str | None = None
    note: str | None = None


router = APIRouter(
    prefix="/comparisons",
    tags=["comparisons"],
)

comparison_service = ClientComparisonService()


@router.get("/timepoints/{maintenance_id}")
async def get_timepoints(
    maintenance_id: str,
    max_days: int = Query(
        default=7,
        ge=1,
        le=30,
        description="時間範圍（天），預設 7 天",
    ),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    獲取指定維護 ID 的歷史時間點（限制在 max_days 天內）。

    回傳採集資料的時間點列表，用於時間選擇器和圖表。
    """
    timepoints = await comparison_service.get_timepoints(
        maintenance_id=maintenance_id,
        session=session,
        max_days=max_days,
    )
    return {
        "maintenance_id": maintenance_id,
        "max_days": max_days,
        "timepoints": timepoints,
    }


@router.get("/statistics/{maintenance_id}")
async def get_statistics(
    maintenance_id: str,
    max_days: int = Query(
        default=7,
        ge=1,
        le=30,
        description="時間範圍（天），預設 7 天",
    ),
    hourly_sampling: bool = Query(
        default=True,
        description="是否每小時採樣（預設 True，最多 7×24=168 個時間點）",
    ),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    獲取每個時間點的統計資料，用於趨勢圖表。

    回傳每個時間點的客戶端數量統計，包括：
    - 全部客戶端數量
    - 有異常的客戶端數量
    - 嚴重問題數量
    - 警告數量

    使用 max_days 參數控制時間範圍（預設 7 天）。
    使用 hourly_sampling=True 時，每小時只保留最後一筆資料點。
    """
    statistics = await comparison_service.get_statistics(
        maintenance_id=maintenance_id,
        session=session,
        max_days=max_days,
        hourly_sampling=hourly_sampling,
    )
    return {
        "maintenance_id": maintenance_id,
        "max_days": max_days,
        "hourly_sampling": hourly_sampling,
        "statistics": statistics,
    }


@router.post("/generate/{maintenance_id}")
async def generate_comparisons(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    生成客戶端比較結果。
    
    比較指定維護 ID 下，所有客戶端在 OLD 和 NEW 階段的變化。
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
    before_time: str | None = Query(None, description="BEFORE 時間點（ISO 格式）"),
    mac_address: str | None = Query(None, description="按 MAC 地址篩選（已廢棄，請使用 search_text）"),
    search_text: str | None = Query(None, description="搜尋 MAC 地址或 IP 地址"),
    severity: str | None = Query(None, description="按嚴重程度篩選 (critical/warning/info/undetected)"),
    changed_only: bool = Query(False, description="只返回有變化的結果"),
    include_undetected: bool = Query(True, description="是否包含分類成員中未偵測的 MAC"),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    列出客戶端比較結果。
    
    支持按 MAC 地址、IP 地址、嚴重程度和是否變化進行篩選。
    包含分類成員中未偵測到的 MAC（severity='undetected'）。
    """
    from sqlalchemy import select
    from app.db.models import ClientCategoryMember
    
    try:
        # 向後兼容：如果提供 mac_address 但沒有 search_text，使用 mac_address
        search = search_text or mac_address
        
        comparisons = await comparison_service.get_comparisons(
            maintenance_id=maintenance_id,
            session=session,
            search_text=search,
            severity=severity if severity != 'undetected' else None,
            changed_only=changed_only,
            before_time=before_time,
        )
        
        # 建立已偵測到的 MAC 集合
        detected_macs = {
            comp.mac_address.upper() for comp in comparisons 
            if comp.mac_address
        }
        
        # 獲取所有覆蓋記錄
        override_stmt = select(SeverityOverride).where(
            SeverityOverride.maintenance_id == maintenance_id
        )
        override_result = await session.execute(override_stmt)
        overrides = override_result.scalars().all()
        
        # 建立 MAC -> 覆蓋記錄 對照
        override_map = {
            o.mac_address.upper(): o for o in overrides
        }
        
        # 轉換為字典格式
        results = []
        
        def has_any_data(comp, prefix: str) -> bool:
            """檢查指定前綴（old/new）是否有任何有效數據。"""
            fields = [
                f"{prefix}_switch_hostname",
                f"{prefix}_interface_name",
                f"{prefix}_ip_address",
                f"{prefix}_vlan_id",
                f"{prefix}_speed",
                f"{prefix}_duplex",
                f"{prefix}_link_status",
            ]
            for field in fields:
                value = getattr(comp, field, None)
                if value is not None and value != "":
                    return True
            return False
        
        for comp in comparisons:
            # 判斷偵測狀態（使用更全面的檢查）
            old_detected = has_any_data(comp, 'old')
            new_detected = has_any_data(comp, 'new')
            
            # 檢查是否有手動覆蓋
            normalized_mac = comp.mac_address.upper() if comp.mac_address else ""
            override = override_map.get(normalized_mac)
            
            # 決定最終顯示的 severity
            display_severity = comp.severity
            is_overridden = False
            original_severity = None
            override_note = None
            
            if override:
                is_overridden = True
                original_severity = override.original_severity or comp.severity
                display_severity = override.override_severity
                override_note = override.note
            
            results.append({
                "id": comp.id,
                "mac_address": comp.mac_address,
                "is_changed": comp.is_changed,
                "severity": display_severity,
                "auto_severity": comp.severity,  # 保留原始自動判斷值
                "is_overridden": is_overridden,
                "original_severity": original_severity,
                "override_note": override_note,
                "differences": comp.differences,
                "notes": comp.notes,
                "old_detected": old_detected,
                "new_detected": new_detected,
                "old": {
                    "ip_address": comp.old_ip_address,
                    "switch_hostname": comp.old_switch_hostname,
                    "interface_name": comp.old_interface_name,
                    "vlan_id": comp.old_vlan_id,
                    "speed": comp.old_speed,
                    "duplex": comp.old_duplex,
                    "link_status": comp.old_link_status,
                    "ping_reachable": comp.old_ping_reachable,
                    "acl_passes": comp.old_acl_passes,
                },
                "new": {
                    "ip_address": comp.new_ip_address,
                    "switch_hostname": comp.new_switch_hostname,
                    "interface_name": comp.new_interface_name,
                    "vlan_id": comp.new_vlan_id,
                    "speed": comp.new_speed,
                    "duplex": comp.new_duplex,
                    "link_status": comp.new_link_status,
                    "ping_reachable": comp.new_ping_reachable,
                    "acl_passes": comp.new_acl_passes,
                },
                "collected_at": comp.collected_at.isoformat() if comp.collected_at else None,
            })
        
        # 如果需要包含未偵測的 MAC
        if include_undetected:
            from app.db.models import ClientCategory
            
            # 只獲取該歲修下活躍分類的成員（必須過濾 maintenance_id）
            active_cat_stmt = select(ClientCategory.id).where(
                ClientCategory.is_active == True,
                ClientCategory.maintenance_id == maintenance_id,
            )
            active_cat_result = await session.execute(active_cat_stmt)
            active_cat_ids = [row[0] for row in active_cat_result.fetchall()]
            
            member_stmt = (
                select(ClientCategoryMember)
                .where(ClientCategoryMember.category_id.in_(active_cat_ids))
            )
            member_result = await session.execute(member_stmt)
            members = member_result.scalars().all()
            
            # 使用 set 避免重複添加（一個 MAC 可能在多個分類中）
            added_undetected_macs = set()
            
            # 添加未偵測的 MAC
            for member in members:
                normalized_mac = member.mac_address.upper() if member.mac_address else ""
                # 跳過已偵測或已添加的 MAC
                if not normalized_mac:
                    continue
                if normalized_mac in detected_macs:
                    continue
                if normalized_mac in added_undetected_macs:
                    continue
                added_undetected_macs.add(normalized_mac)
                
                # 檢查搜尋條件
                if search:
                    search_lower = search.lower()
                    if search_lower not in normalized_mac.lower():
                        continue
                
                # 檢查是否有覆蓋
                override = override_map.get(normalized_mac)
                display_severity = "undetected"
                is_overridden = False
                original_severity = None
                override_note = None
                
                if override:
                    is_overridden = True
                    original_severity = "undetected"  # 原始一定是 undetected
                    display_severity = override.override_severity
                    override_note = override.note
                
                # 如果篩選 severity，需要匹配覆蓋後的 severity
                if severity:
                    if severity == 'undetected':
                        # 只顯示沒有覆蓋或覆蓋值仍為 undetected 的
                        if is_overridden and display_severity != 'undetected':
                            continue
                    else:
                        # 篩選其他 severity
                        if display_severity != severity:
                            continue
                
                results.append({
                        "id": None,
                        "mac_address": normalized_mac,
                        "is_changed": False,
                        "severity": display_severity,
                        "auto_severity": "undetected",
                        "is_overridden": is_overridden,
                        "original_severity": original_severity,
                        "override_note": override_note,
                        "differences": {},
                        "notes": "此 MAC 在 OLD 和 NEW 階段均未偵測到",
                        "old_detected": False,
                        "new_detected": False,
                        "old": {
                            "ip_address": None,
                            "switch_hostname": None,
                            "interface_name": None,
                            "vlan_id": None,
                            "speed": None,
                            "duplex": None,
                            "link_status": None,
                            "ping_reachable": None,
                            "acl_passes": None,
                        },
                        "new": {
                            "ip_address": None,
                            "switch_hostname": None,
                            "interface_name": None,
                            "vlan_id": None,
                            "speed": None,
                            "duplex": None,
                            "link_status": None,
                            "ping_reachable": None,
                            "acl_passes": None,
                        },
                        "collected_at": None,
                        "description": member.description,
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
            search_text=mac_address,
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
            "old": {
                "ip_address": comp.old_ip_address,
                "switch_hostname": comp.old_switch_hostname,
                "interface_name": comp.old_interface_name,
                "vlan_id": comp.old_vlan_id,
                "speed": comp.old_speed,
                "duplex": comp.old_duplex,
                "link_status": comp.old_link_status,
                "ping_reachable": comp.old_ping_reachable,
                "acl_passes": comp.old_acl_passes,
            },
            "new": {
                "ip_address": comp.new_ip_address,
                "switch_hostname": comp.new_switch_hostname,
                "interface_name": comp.new_interface_name,
                "vlan_id": comp.new_vlan_id,
                "speed": comp.new_speed,
                "duplex": comp.new_duplex,
                "link_status": comp.new_link_status,
                "ping_reachable": comp.new_ping_reachable,
                "acl_passes": comp.new_acl_passes,
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


# ========== 嚴重程度覆蓋 API ==========

@router.get("/overrides/{maintenance_id}")
async def list_severity_overrides(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """列出所有嚴重程度覆蓋記錄。"""
    stmt = (
        select(SeverityOverride)
        .where(SeverityOverride.maintenance_id == maintenance_id)
        .order_by(SeverityOverride.updated_at.desc())
    )
    result = await session.execute(stmt)
    overrides = result.scalars().all()
    
    return {
        "success": True,
        "maintenance_id": maintenance_id,
        "count": len(overrides),
        "overrides": [
            {
                "id": o.id,
                "mac_address": o.mac_address,
                "override_severity": o.override_severity,
                "original_severity": o.original_severity,
                "note": o.note,
                "created_at": o.created_at.isoformat() if o.created_at else None,
                "updated_at": o.updated_at.isoformat() if o.updated_at else None,
            }
            for o in overrides
        ],
    }


@router.post("/overrides/{maintenance_id}")
async def create_or_update_severity_override(
    maintenance_id: str,
    data: SeverityOverrideCreate,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    創建或更新嚴重程度覆蓋。
    
    如果該 MAC 已有覆蓋記錄則更新，否則創建新記錄。
    """
    # 標準化 MAC 地址
    normalized_mac = data.mac_address.upper()
    
    # 驗證 severity 值
    valid_severities = ['critical', 'warning', 'info']
    if data.override_severity not in valid_severities:
        raise HTTPException(
            status_code=400,
            detail=f"無效的嚴重程度，必須是: {', '.join(valid_severities)}",
        )
    
    # 查詢是否已存在
    stmt = select(SeverityOverride).where(
        SeverityOverride.maintenance_id == maintenance_id,
        SeverityOverride.mac_address == normalized_mac,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    
    if existing:
        # 更新現有記錄
        existing.override_severity = data.override_severity
        if data.note is not None:
            existing.note = data.note
        # 保留 original_severity 不變
        await session.commit()
        await session.refresh(existing)
        override = existing
        message = "覆蓋記錄已更新"
    else:
        # 創建新記錄
        override = SeverityOverride(
            maintenance_id=maintenance_id,
            mac_address=normalized_mac,
            override_severity=data.override_severity,
            original_severity=data.original_severity,
            note=data.note,
        )
        session.add(override)
        await session.commit()
        await session.refresh(override)
        message = "覆蓋記錄已創建"
    
    return {
        "success": True,
        "message": message,
        "override": {
            "id": override.id,
            "mac_address": override.mac_address,
            "override_severity": override.override_severity,
            "original_severity": override.original_severity,
            "note": override.note,
        },
    }


@router.delete("/overrides/{maintenance_id}/{mac_address}")
async def delete_severity_override(
    maintenance_id: str,
    mac_address: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """刪除嚴重程度覆蓋（恢復自動判斷）。"""
    normalized_mac = mac_address.upper()
    
    stmt = select(SeverityOverride).where(
        SeverityOverride.maintenance_id == maintenance_id,
        SeverityOverride.mac_address == normalized_mac,
    )
    result = await session.execute(stmt)
    override = result.scalar_one_or_none()
    
    if not override:
        raise HTTPException(
            status_code=404,
            detail=f"找不到 MAC {mac_address} 的覆蓋記錄",
        )
    
    original = override.original_severity
    await session.delete(override)
    await session.commit()
    
    return {
        "success": True,
        "message": "已恢復自動判斷",
        "mac_address": normalized_mac,
        "original_severity": original,
    }


@router.delete("/overrides/{maintenance_id}")
async def clear_all_severity_overrides(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """清除所有嚴重程度覆蓋（恢復全部自動判斷）。"""
    stmt = delete(SeverityOverride).where(
        SeverityOverride.maintenance_id == maintenance_id
    )
    result = await session.execute(stmt)
    await session.commit()
    
    return {
        "success": True,
        "message": f"已清除 {result.rowcount} 筆覆蓋記錄",
        "deleted_count": result.rowcount,
    }
