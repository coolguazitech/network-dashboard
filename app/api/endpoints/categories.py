"""
Client Category API endpoints.

CRUD operations for client categories and category members.
"""
from __future__ import annotations

import csv
import io
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy import select, func

from app.api.endpoints.auth import get_current_user, require_write
from app.db.base import get_session_context
from app.db.models import (
    ClientCategory,
    ClientCategoryMember,
    ClientComparison,
)
from app.services.system_log import write_log


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
    undetected_count: int = 0  # 未偵測（分類中有但監測數據中沒有）


# ========== API Endpoints ==========

# 注意：/stats 路由必須放在 /{category_id} 之前，避免路由衝突
@router.get("/stats/{maintenance_id}", response_model=list[CategoryStatsResponse])
async def get_category_stats(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
    before_time: str | None = None,
) -> list[dict[str, Any]]:
    """
    獲取各種類的統計數據（用於卡片顯示）。

    當提供 before_time 時，使用動態比較（Checkpoint vs Current）。
    否則使用 ClientComparison 表的靜態數據。
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

        # 如果提供 before_time，使用動態比較（與 /diff 端點一致）
        if before_time:
            checkpoint_time = datetime.fromisoformat(before_time)

            # 獲取最新快照時間
            latest_stmt = (
                select(func.max(ClientRecord.collected_at))
                .where(
                    ClientRecord.maintenance_id == maintenance_id,
                )
            )
            latest_result = await session.execute(latest_stmt)
            current_time = latest_result.scalar()

            # 使用動態 Checkpoint vs Current 比較
            comparison_service = ClientComparisonService()
            comparisons = await comparison_service._generate_checkpoint_diff(
                maintenance_id=maintenance_id,
                checkpoint_time=checkpoint_time,
                current_time=current_time,
                session=session,
            )
        else:
            # 沒有 before_time 時，使用 ClientComparison 表的靜態數據
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
                "undetected_count": 0,
            }

        # 未分類
        stats[None] = {
            "category_id": None,
            "category_name": "未分類",
            "color": "#6B7280",
            "total_count": 0,
            "issue_count": 0,
            "undetected_count": 0,
        }

        # 建立已偵測到的 MAC 集合
        detected_macs = {
            c.mac_address.upper() for c in comparisons if c.mac_address
        }

        # 用於計算「全部」聯集的 MAC 集合
        all_macs: set[str] = set()
        all_issue_macs: set[str] = set()
        all_undetected_macs: set[str] = set()

        # 統計每個比較結果
        for comp in comparisons:
            normalized_mac = comp.mac_address.upper() if comp.mac_address else ""
            if not normalized_mac:
                continue

            cat_ids = mac_to_categories.get(normalized_mac, [])
            if not cat_ids:
                cat_ids = [None]

            is_issue = comp.is_changed or comp.severity == "undetected"

            for cat_id in cat_ids:
                if cat_id not in stats:
                    continue
                stats[cat_id]["total_count"] += 1
                if comp.severity == "undetected":
                    stats[cat_id]["undetected_count"] += 1
                if is_issue:
                    stats[cat_id]["issue_count"] += 1

            all_macs.add(normalized_mac)
            if comp.severity == "undetected":
                all_undetected_macs.add(normalized_mac)
            if is_issue:
                all_issue_macs.add(normalized_mac)

        # 統計分類成員中未偵測到的 MAC
        for mac, cat_ids in mac_to_categories.items():
            if mac not in detected_macs:
                for cat_id in cat_ids:
                    if cat_id in stats:
                        stats[cat_id]["total_count"] += 1
                        stats[cat_id]["undetected_count"] += 1
                        stats[cat_id]["issue_count"] += 1
                all_macs.add(mac)
                all_undetected_macs.add(mac)
                all_issue_macs.add(mac)

        # 加入「全部」統計（使用聯集計算）
        all_stats = {
            "category_id": -1,
            "category_name": "全部",
            "color": "#1F2937",
            "total_count": len(all_macs),
            "issue_count": len(all_issue_macs),
            "undetected_count": len(all_undetected_macs),
        }

        result = [all_stats]
        result.extend(stats[cat.id] for cat in categories)
        result.append(stats[None])

        return result


@router.get("", response_model=list[CategoryResponse])
async def list_categories(
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
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
async def create_category(
    _user: Annotated[dict[str, Any], Depends(require_write())],
    data: CategoryCreate,
) -> dict[str, Any]:
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

        await write_log(
            level="INFO",
            source="api",
            summary=f"新增分類: {data.name}",
            module="category",
            maintenance_id=data.maintenance_id,
        )

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
    _user: Annotated[dict[str, Any], Depends(require_write())],
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

        await write_log(
            level="INFO",
            source="api",
            summary=f"更新分類: {category.name}",
            module="category",
            maintenance_id=category.maintenance_id,
        )

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
async def delete_category(
    category_id: int,
    _user: Annotated[dict[str, Any], Depends(require_write())],
) -> dict[str, str]:
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

        await write_log(
            level="WARNING",
            source="api",
            summary=f"刪除分類: {category.name}",
            module="category",
            maintenance_id=category.maintenance_id,
        )

        return {"message": f"種類 '{category.name}' 已刪除"}


# ========== 成員管理 ==========

@router.get("/{category_id}/members", response_model=list[MemberResponse])
async def list_members(
    category_id: int,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> list[dict[str, Any]]:
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
    _user: Annotated[dict[str, Any], Depends(require_write())],
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

        await write_log(
            level="INFO",
            source="api",
            summary=f"分類成員: {mac} → {category.name}",
            module="category",
            maintenance_id=category.maintenance_id,
        )

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
    _user: Annotated[dict[str, Any], Depends(require_write())],
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

        await write_log(
            level="WARNING",
            source="api",
            summary=f"移除分類成員: {mac}",
            module="category",
            maintenance_id=None,
        )

        return {"message": f"已移除 {mac}"}


@router.post("/{category_id}/import-csv")
async def import_members_csv(
    category_id: int,
    _user: Annotated[dict[str, Any], Depends(require_write())],
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

        if imported + updated > 0:
            await write_log(
                level="INFO",
                source="api",
                summary=f"CSV 匯入分類成員: 新增 {imported}, 更新 {updated}",
                module="category",
                maintenance_id=category.maintenance_id,
            )

        return {
            "imported": imported,
            "updated": updated,
            "errors": errors[:10],  # 最多回傳 10 個錯誤
            "total_errors": len(errors),
        }


@router.post("/bulk-import")
async def bulk_import_categories(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(require_write())],
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """
    批量匯入分類及成員。

    CSV 格式: category_name,mac_address,description
    會自動建立不存在的分類，並將成員加入對應分類。
    """
    # 預設顏色列表（循環使用）
    DEFAULT_COLORS = [
        "#3B82F6",  # 藍
        "#10B981",  # 綠
        "#F59E0B",  # 黃
        "#EF4444",  # 紅
        "#8B5CF6",  # 紫
    ]

    async with get_session_context() as session:
        # 讀取 CSV
        content = await file.read()
        try:
            text = content.decode("utf-8-sig")  # 處理 BOM
        except UnicodeDecodeError:
            text = content.decode("utf-8")

        reader = csv.DictReader(io.StringIO(text))

        # 獲取現有分類
        existing_stmt = select(ClientCategory).where(
            ClientCategory.maintenance_id == maintenance_id,
            ClientCategory.is_active == True,
        )
        existing_result = await session.execute(existing_stmt)
        existing_categories = {c.name: c for c in existing_result.scalars().all()}

        # 統計
        categories_created = 0
        members_imported = 0
        members_updated = 0
        errors = []

        # 按分類分組處理
        category_members: dict[str, list[dict]] = {}

        for row_num, row in enumerate(reader, start=2):
            cat_name = row.get("category_name", "").strip()
            raw_mac = row.get("mac_address", "").strip()
            desc = row.get("description", "").strip() or None

            if not cat_name:
                errors.append(f"Row {row_num}: 分類名稱為空")
                continue

            if not raw_mac:
                errors.append(f"Row {row_num}: MAC 地址為空")
                continue

            # 標準化 MAC 格式
            mac = raw_mac.upper().replace("-", ":")

            # 驗證 MAC 格式
            if not MAC_REGEX.match(mac):
                errors.append(f"Row {row_num}: MAC 格式錯誤 ({raw_mac})")
                continue

            if cat_name not in category_members:
                category_members[cat_name] = []
            category_members[cat_name].append({"mac": mac, "desc": desc})

        # 檢查分類數量限制
        new_categories = set(category_members.keys()) - set(existing_categories.keys())
        total_categories = len(existing_categories) + len(new_categories)

        if total_categories > MAX_CATEGORIES:
            raise HTTPException(
                status_code=400,
                detail=f"匯入後分類總數 ({total_categories}) 超過上限 ({MAX_CATEGORIES})",
            )

        # 建立新分類
        color_idx = len(existing_categories)
        for cat_name in new_categories:
            category = ClientCategory(
                maintenance_id=maintenance_id,
                name=cat_name,
                color=DEFAULT_COLORS[color_idx % len(DEFAULT_COLORS)],
                sort_order=color_idx,
            )
            session.add(category)
            await session.flush()  # 獲取 ID
            existing_categories[cat_name] = category
            categories_created += 1
            color_idx += 1

        # 匯入成員
        for cat_name, members in category_members.items():
            category = existing_categories[cat_name]

            for member_data in members:
                mac = member_data["mac"]
                desc = member_data["desc"]

                # 檢查是否已存在
                existing_stmt = select(ClientCategoryMember).where(
                    ClientCategoryMember.category_id == category.id,
                    ClientCategoryMember.mac_address == mac,
                )
                existing = await session.execute(existing_stmt)
                existing_member = existing.scalar_one_or_none()

                if existing_member:
                    existing_member.description = desc
                    members_updated += 1
                else:
                    member = ClientCategoryMember(
                        category_id=category.id,
                        mac_address=mac,
                        description=desc,
                    )
                    session.add(member)
                    members_imported += 1

        await session.commit()

        if categories_created + members_imported > 0:
            await write_log(
                level="INFO",
                source="api",
                summary=f"批量匯入分類: 建立 {categories_created} 分類, 新增 {members_imported} 成員",
                module="category",
                maintenance_id=maintenance_id,
            )

        return {
            "categories_created": categories_created,
            "members_imported": members_imported,
            "members_updated": members_updated,
            "errors": errors[:10],
            "total_errors": len(errors),
        }
