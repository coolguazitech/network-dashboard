"""
Client Category API endpoints.

CRUD operations for client categories and category members.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select, func

from app.db.base import get_session_context
from app.db.models import (
    ClientCategory,
    ClientCategoryMember,
    ClientComparison,
    SeverityOverride,
)


# MAC 地址格式驗證正則
MAC_REGEX = re.compile(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$')


def validate_mac_address(mac: str) -> str:
    """
    驗證並標準化 MAC 地址格式。
    
    Args:
        mac: 原始 MAC 地址字串
        
    Returns:
        標準化的 MAC 地址（大寫，冒號分隔）
        
    Raises:
        HTTPException: MAC 格式錯誤
    """
    if not mac:
        raise HTTPException(
            status_code=400,
            detail="MAC 地址不能為空",
        )
    
    # 標準化：轉大寫，將 - 替換為 :
    normalized = mac.strip().upper().replace("-", ":")
    
    # 檢查格式
    if not MAC_REGEX.match(normalized):
        raise HTTPException(
            status_code=400,
            detail=f"MAC 格式錯誤：「{mac}」\n\n"
                   f"正確格式：XX:XX:XX:XX:XX:XX\n"
                   f"每組必須是兩個十六進制字符（0-9, A-F）\n"
                   f"使用冒號 : 分隔",
        )
    
    return normalized

router = APIRouter(prefix="/categories", tags=["categories"])

# 種類上限
MAX_CATEGORIES = 5


# ========== Pydantic Schemas ==========

class CategoryCreate(BaseModel):
    """創建種類請求。"""
    maintenance_id: str
    name: str
    description: str | None = None
    color: str | None = "#3B82F6"  # 預設藍色


class CategoryUpdate(BaseModel):
    """更新種類請求。"""
    name: str | None = None
    description: str | None = None
    color: str | None = None
    sort_order: int | None = None


class CategoryResponse(BaseModel):
    """種類回應。"""
    id: int
    name: str
    description: str | None
    color: str | None
    sort_order: int
    member_count: int
    is_active: bool


class MemberCreate(BaseModel):
    """新增成員請求。"""
    mac_address: str
    description: str | None = None


class MemberResponse(BaseModel):
    """成員回應。"""
    id: int
    mac_address: str
    description: str | None
    category_id: int
    category_name: str | None = None


class CategoryStatsResponse(BaseModel):
    """種類統計回應（用於卡片顯示）。"""
    category_id: int | None
    category_name: str
    color: str
    total_count: int        # 總數（包含未偵測）
    issue_count: int        # 有異常的數量
    critical_count: int     # 重大問題數量
    warning_count: int      # 警告數量
    undetected_count: int = 0  # 未偵測（分類中有但監測數據中沒有）


# ========== API Endpoints ==========

# 注意：/stats 路由必須放在 /{category_id} 之前，避免路由衝突
@router.get("/stats/{maintenance_id}", response_model=list[CategoryStatsResponse])
async def get_category_stats(
    maintenance_id: str,
    before_time: str | None = None,
) -> list[dict[str, Any]]:
    """
    獲取各種類的統計數據（用於卡片顯示）。
    
    優先使用 ClientRecord 動態生成比較結果，
    如果沒有 ClientRecord 數據，則直接使用 ClientComparison 表。
    """
    from datetime import datetime
    from sqlalchemy import func
    from app.db.models import ClientRecord
    from app.services.client_comparison_service import ClientComparisonService
    
    async with get_session_context() as session:
        # 獲取該歲修的所有種類
        cat_stmt = (
            select(ClientCategory)
            .where(
                ClientCategory.is_active == True,
                ClientCategory.maintenance_id == maintenance_id,
            )
            .order_by(ClientCategory.sort_order)
        )
        cat_result = await session.execute(cat_stmt)
        categories = cat_result.scalars().all()
        
        # 獲取種類成員對應（只取活躍分類的成員）
        active_cat_ids = [c.id for c in categories]
        member_stmt = (
            select(ClientCategoryMember)
            .where(ClientCategoryMember.category_id.in_(active_cat_ids))
        )
        member_result = await session.execute(member_stmt)
        members = member_result.scalars().all()
        
        # 建立 MAC -> category_ids 對照（一對多：一個 MAC 可屬於多個分類）
        mac_to_categories: dict[str, list[int]] = {}
        for m in members:
            if m.mac_address:
                normalized = m.mac_address.upper()
                if normalized not in mac_to_categories:
                    mac_to_categories[normalized] = []
                mac_to_categories[normalized].append(m.category_id)
        
        # 檢查是否有 ClientRecord 數據
        record_count_stmt = (
            select(func.count())
            .select_from(ClientRecord)
            .where(ClientRecord.maintenance_id == maintenance_id)
        )
        record_count_result = await session.execute(record_count_stmt)
        record_count = record_count_result.scalar() or 0
        
        comparisons = []
        
        if record_count > 0:
            # 有 ClientRecord 數據，使用動態生成
            first_stmt = (
                select(func.min(ClientRecord.collected_at))
                .where(ClientRecord.maintenance_id == maintenance_id)
            )
            first_result = await session.execute(first_stmt)
            first_time = first_result.scalar()
            
            latest_stmt = (
                select(func.max(ClientRecord.collected_at))
                .where(ClientRecord.maintenance_id == maintenance_id)
            )
            latest_result = await session.execute(latest_stmt)
            latest_time = latest_result.scalar()
            
            # 解析 before_time 參數
            if before_time:
                try:
                    before_dt = datetime.fromisoformat(before_time)
                except ValueError:
                    before_dt = first_time
            else:
                before_dt = first_time
            
            # 動態生成比較結果
            if before_dt and latest_time:
                service = ClientComparisonService()
                comparisons = await service._generate_comparisons_at_time(
                    maintenance_id=maintenance_id,
                    before_time=before_dt,
                    after_time=latest_time,
                    session=session,
                )
        else:
            # 沒有 ClientRecord 數據，直接使用 ClientComparison 表
            comp_stmt = (
                select(ClientComparison)
                .where(ClientComparison.maintenance_id == maintenance_id)
            )
            comp_result = await session.execute(comp_stmt)
            comparisons = comp_result.scalars().all()
        
        # 計算統計
        stats: dict[int | None, dict[str, Any]] = {}
        
        # 初始化種類統計
        for cat in categories:
            stats[cat.id] = {
                "category_id": cat.id,
                "category_name": cat.name,
                "color": cat.color or "#3B82F6",
                "total_count": 0,
                "issue_count": 0,
                "critical_count": 0,
                "warning_count": 0,
                "undetected_count": 0,
            }
        
        # 未分類
        stats[None] = {
            "category_id": None,
            "category_name": "未分類",
            "color": "#6B7280",
            "total_count": 0,
            "issue_count": 0,
            "critical_count": 0,
            "warning_count": 0,
            "undetected_count": 0,
        }
        
        # 獲取所有覆蓋記錄
        override_stmt = select(SeverityOverride).where(
            SeverityOverride.maintenance_id == maintenance_id
        )
        override_result = await session.execute(override_stmt)
        overrides = override_result.scalars().all()
        
        # 建立 MAC -> 覆蓋 severity 對照
        override_map = {
            o.mac_address.upper(): o.override_severity for o in overrides
        }
        
        # 建立已偵測到的 MAC 集合
        detected_macs = {
            c.mac_address.upper() for c in comparisons if c.mac_address
        }
        
        # 用於計算「全部」聯集的 MAC 集合
        all_macs: set[str] = set()
        all_issue_macs: set[str] = set()
        all_critical_macs: set[str] = set()
        all_warning_macs: set[str] = set()
        all_undetected_macs: set[str] = set()
        
        # 統計每個比較結果（標準化 MAC 為大寫）
        for comp in comparisons:
            normalized_mac = comp.mac_address.upper() if comp.mac_address else ""
            if not normalized_mac:
                continue
            
            # 獲取該 MAC 所屬的所有分類
            cat_ids = mac_to_categories.get(normalized_mac, [])
            
            # 如果沒有分類，歸入未分類
            if not cat_ids:
                cat_ids = [None]
            
            # 使用覆蓋的 severity（如果有）
            effective_severity = override_map.get(
                normalized_mac, comp.severity
            )
            
            # 判斷是否為異常：
            # - 如果是手動覆蓋且不是 info，則為異常
            # - 如果有變化且 severity 是 critical 或 warning，則為異常
            is_override = normalized_mac in override_map
            is_issue = False
            
            if is_override:
                # 手動覆蓋：根據覆蓋值判斷
                is_issue = effective_severity in ('critical', 'warning')
            else:
                # 自動判斷：有變化且嚴重程度不是 info
                is_issue = comp.is_changed and effective_severity != 'info'
            
            # 統計到每個所屬分類
            for cat_id in cat_ids:
                if cat_id not in stats:
                    continue
                stats[cat_id]["total_count"] += 1
                
                if is_issue:
                    stats[cat_id]["issue_count"] += 1
                    if effective_severity == "critical":
                        stats[cat_id]["critical_count"] += 1
                    elif effective_severity == "warning":
                        stats[cat_id]["warning_count"] += 1
            
            # 聯集統計（用於「全部」）
            all_macs.add(normalized_mac)
            if is_issue:
                all_issue_macs.add(normalized_mac)
                if effective_severity == "critical":
                    all_critical_macs.add(normalized_mac)
                elif effective_severity == "warning":
                    all_warning_macs.add(normalized_mac)
        
        # 統計分類成員中未偵測到的 MAC（只統計有分類的）
        # 未偵測預設算異常，但如果被覆蓋為 info 則不算異常
        for mac, cat_ids in mac_to_categories.items():
            if mac not in detected_macs:
                # 這個 MAC 在分類成員表中但沒有監測數據
                # 檢查是否有覆蓋
                effective_severity = override_map.get(mac, 'undetected')
                is_issue = effective_severity in ('critical', 'warning', 'undetected')
                
                for cat_id in cat_ids:
                    if cat_id in stats:
                        stats[cat_id]["total_count"] += 1
                        stats[cat_id]["undetected_count"] += 1
                        if is_issue:
                            stats[cat_id]["issue_count"] += 1
                            if effective_severity == "critical":
                                stats[cat_id]["critical_count"] += 1
                            elif effective_severity == "warning":
                                stats[cat_id]["warning_count"] += 1
                all_macs.add(mac)
                all_undetected_macs.add(mac)
                if is_issue:
                    all_issue_macs.add(mac)
                    if effective_severity == "critical":
                        all_critical_macs.add(mac)
                    elif effective_severity == "warning":
                        all_warning_macs.add(mac)
        
        # 加入「全部」統計（使用聯集計算）
        all_stats = {
            "category_id": -1,
            "category_name": "全部",
            "color": "#1F2937",
            "total_count": len(all_macs),  # 聯集：去重後的 MAC 總數
            "issue_count": len(all_issue_macs),
            "critical_count": len(all_critical_macs),
            "warning_count": len(all_warning_macs),
            "undetected_count": len(all_undetected_macs),
        }
        
        result = [all_stats]
        result.extend(stats[cat.id] for cat in categories)
        result.append(stats[None])
        
        return result


@router.get("", response_model=list[CategoryResponse])
async def list_categories(
    maintenance_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    獲取機台種類（按 maintenance_id 過濾）。
    
    Args:
        maintenance_id: 歲修 ID（必填以獲取該歲修的分類）
    
    返回按 sort_order 排序的種類列表。
    """
    async with get_session_context() as session:
        # 查詢種類及其成員數
        stmt = (
            select(
                ClientCategory,
                func.count(ClientCategoryMember.id).label("member_count"),
            )
            .outerjoin(ClientCategoryMember)
            .where(ClientCategory.is_active == True)
        )
        
        # 按 maintenance_id 過濾
        if maintenance_id:
            stmt = stmt.where(
                ClientCategory.maintenance_id == maintenance_id
            )
        
        stmt = stmt.group_by(ClientCategory.id).order_by(
            ClientCategory.sort_order
        )
        
        result = await session.execute(stmt)
        rows = result.all()
        
        return [
            {
                "id": cat.id,
                "name": cat.name,
                "description": cat.description,
                "color": cat.color,
                "sort_order": cat.sort_order,
                "member_count": member_count,
                "is_active": cat.is_active,
            }
            for cat, member_count in rows
        ]


@router.post("", response_model=CategoryResponse)
async def create_category(data: CategoryCreate) -> dict[str, Any]:
    """
    創建新的機台種類（歲修專屬）。
    
    每個歲修最多只能創建 5 個種類。
    """
    async with get_session_context() as session:
        # 檢查該歲修的數量限制
        count_stmt = select(func.count()).select_from(ClientCategory).where(
            ClientCategory.is_active == True,
            ClientCategory.maintenance_id == data.maintenance_id,
        )
        result = await session.execute(count_stmt)
        current_count = result.scalar() or 0
        
        if current_count >= MAX_CATEGORIES:
            raise HTTPException(
                status_code=400,
                detail=f"該歲修已達到種類上限 ({MAX_CATEGORIES} 個)",
            )
        
        # 檢查名稱重複（同一歲修下的活躍種類）
        name_stmt = select(ClientCategory).where(
            ClientCategory.name == data.name,
            ClientCategory.maintenance_id == data.maintenance_id,
            ClientCategory.is_active == True,
        )
        existing = await session.execute(name_stmt)
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"該歲修已有名為 '{data.name}' 的種類",
            )
        
        # 創建種類（含 maintenance_id）
        category = ClientCategory(
            maintenance_id=data.maintenance_id,
            name=data.name,
            description=data.description,
            color=data.color,
            sort_order=current_count,
        )
        session.add(category)
        await session.commit()
        await session.refresh(category)
        
        return {
            "id": category.id,
            "name": category.name,
            "description": category.description,
            "color": category.color,
            "sort_order": category.sort_order,
            "member_count": 0,
            "is_active": category.is_active,
        }


@router.put("/{category_id}", response_model=CategoryResponse)
async def update_category(
    category_id: int,
    data: CategoryUpdate,
) -> dict[str, Any]:
    """更新機台種類。"""
    async with get_session_context() as session:
        stmt = select(ClientCategory).where(ClientCategory.id == category_id)
        result = await session.execute(stmt)
        category = result.scalar_one_or_none()
        
        if not category:
            raise HTTPException(status_code=404, detail="種類不存在")
        
        # 檢查名稱重複（只檢查活躍的種類）
        if data.name and data.name != category.name:
            name_stmt = select(ClientCategory).where(
                ClientCategory.name == data.name,
                ClientCategory.id != category_id,
                ClientCategory.is_active == True,
            )
            existing = await session.execute(name_stmt)
            if existing.scalar_one_or_none():
                raise HTTPException(
                    status_code=400,
                    detail=f"種類名稱 '{data.name}' 已存在",
                )
        
        # 更新欄位
        if data.name is not None:
            category.name = data.name
        if data.description is not None:
            category.description = data.description
        if data.color is not None:
            category.color = data.color
        if data.sort_order is not None:
            category.sort_order = data.sort_order
        
        await session.commit()
        await session.refresh(category)
        
        # 計算成員數
        count_stmt = select(func.count()).select_from(
            ClientCategoryMember
        ).where(ClientCategoryMember.category_id == category_id)
        count_result = await session.execute(count_stmt)
        member_count = count_result.scalar() or 0
        
        return {
            "id": category.id,
            "name": category.name,
            "description": category.description,
            "color": category.color,
            "sort_order": category.sort_order,
            "member_count": member_count,
            "is_active": category.is_active,
        }


@router.delete("/{category_id}")
async def delete_category(category_id: int) -> dict[str, str]:
    """
    刪除機台種類。
    
    該種類下的所有成員會變成未分類。
    """
    async with get_session_context() as session:
        stmt = select(ClientCategory).where(ClientCategory.id == category_id)
        result = await session.execute(stmt)
        category = result.scalar_one_or_none()
        
        if not category:
            raise HTTPException(status_code=404, detail="種類不存在")
        
        # 軟刪除
        category.is_active = False
        await session.commit()
        
        return {"message": f"種類 '{category.name}' 已刪除"}


# ========== 成員管理 ==========

@router.get("/{category_id}/members", response_model=list[MemberResponse])
async def list_members(category_id: int) -> list[dict[str, Any]]:
    """獲取種類下的所有成員。"""
    async with get_session_context() as session:
        stmt = (
            select(ClientCategoryMember)
            .where(ClientCategoryMember.category_id == category_id)
            .order_by(ClientCategoryMember.mac_address)
        )
        result = await session.execute(stmt)
        members = result.scalars().all()
        
        # 獲取種類名稱
        cat_stmt = select(ClientCategory).where(
            ClientCategory.id == category_id
        )
        cat_result = await session.execute(cat_stmt)
        category = cat_result.scalar_one_or_none()
        cat_name = category.name if category else None
        
        return [
            {
                "id": m.id,
                "mac_address": m.mac_address,
                "description": m.description,
                "category_id": m.category_id,
                "category_name": cat_name,
            }
            for m in members
        ]


@router.post("/{category_id}/members", response_model=MemberResponse)
async def add_member(
    category_id: int,
    data: MemberCreate,
) -> dict[str, Any]:
    """
    新增成員到種類。
    
    一個 MAC 可以屬於多個種類（多對多關係）。
    只檢查同一種類下是否已有該 MAC。
    """
    async with get_session_context() as session:
        # 檢查種類存在
        cat_stmt = select(ClientCategory).where(
            ClientCategory.id == category_id
        )
        cat_result = await session.execute(cat_stmt)
        category = cat_result.scalar_one_or_none()
        
        if not category:
            raise HTTPException(status_code=404, detail="種類不存在")
        
        # 驗證並標準化 MAC 地址（嚴格格式檢查）
        mac = validate_mac_address(data.mac_address)
        
        # 只檢查同一種類下是否已有該 MAC（允許同一 MAC 在不同種類）
        existing_stmt = select(ClientCategoryMember).where(
            ClientCategoryMember.category_id == category_id,
            ClientCategoryMember.mac_address == mac,
        )
        existing = await session.execute(existing_stmt)
        existing_member = existing.scalar_one_or_none()
        
        if existing_member:
            # 該種類已有此 MAC，更新描述
            existing_member.description = data.description
            await session.commit()
            await session.refresh(existing_member)
            member = existing_member
        else:
            # 創建新成員（即使該 MAC 在其他種類已存在）
            member = ClientCategoryMember(
                category_id=category_id,
                mac_address=mac,
                description=data.description,
            )
            session.add(member)
            await session.commit()
            await session.refresh(member)
        
        return {
            "id": member.id,
            "mac_address": member.mac_address,
            "description": member.description,
            "category_id": member.category_id,
            "category_name": category.name,
        }


@router.delete("/{category_id}/members/{mac_address}")
async def remove_member(
    category_id: int,
    mac_address: str,
) -> dict[str, str]:
    """從種類中移除成員。"""
    mac = mac_address.upper().replace("-", ":")
    
    async with get_session_context() as session:
        stmt = select(ClientCategoryMember).where(
            ClientCategoryMember.category_id == category_id,
            ClientCategoryMember.mac_address == mac,
        )
        result = await session.execute(stmt)
        member = result.scalar_one_or_none()
        
        if not member:
            raise HTTPException(status_code=404, detail="成員不存在")
        
        await session.delete(member)
        await session.commit()
        
        return {"message": f"已移除 {mac}"}


@router.post("/{category_id}/import-csv")
async def import_members_csv(
    category_id: int,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """
    從 CSV 檔案批量導入成員。
    
    CSV 格式: mac_address,description (description 可選)
    """
    async with get_session_context() as session:
        # 檢查種類存在
        cat_stmt = select(ClientCategory).where(
            ClientCategory.id == category_id
        )
        cat_result = await session.execute(cat_stmt)
        category = cat_result.scalar_one_or_none()
        
        if not category:
            raise HTTPException(status_code=404, detail="種類不存在")
        
        # 讀取 CSV
        content = await file.read()
        try:
            text = content.decode("utf-8-sig")  # 處理 BOM
        except UnicodeDecodeError:
            text = content.decode("utf-8")
        
        reader = csv.DictReader(io.StringIO(text))
        
        imported = 0
        updated = 0
        errors = []
        
        for row_num, row in enumerate(reader, start=2):
            raw_mac = row.get("mac_address", "").strip()
            desc = row.get("description", "").strip() or None
            
            if not raw_mac:
                errors.append(f"Row {row_num}: MAC 地址為空")
                continue
            
            # 標準化 MAC 格式
            mac = raw_mac.upper().replace("-", ":")
            
            # 驗證 MAC 格式（嚴格檢查：必須是合法十六進制字符）
            if not MAC_REGEX.match(mac):
                errors.append(
                    f"Row {row_num}: MAC 格式錯誤 ({raw_mac})"
                    f" - 正確格式: XX:XX:XX:XX:XX:XX"
                )
                continue
            
            # 只檢查同一分類下是否已存在（允許同 MAC 在不同分類）
            existing_stmt = select(ClientCategoryMember).where(
                ClientCategoryMember.category_id == category_id,
                ClientCategoryMember.mac_address == mac,
            )
            existing = await session.execute(existing_stmt)
            existing_member = existing.scalar_one_or_none()
            
            if existing_member:
                # 該分類已有此 MAC，更新描述
                existing_member.description = desc
                updated += 1
            else:
                # 新增到該分類（即使 MAC 在其他分類已存在）
                member = ClientCategoryMember(
                    category_id=category_id,
                    mac_address=mac,
                    description=desc,
                )
                session.add(member)
                imported += 1
        
        await session.commit()
        
        return {
            "imported": imported,
            "updated": updated,
            "errors": errors[:10],  # 最多回傳 10 個錯誤
            "total_errors": len(errors),
        }
