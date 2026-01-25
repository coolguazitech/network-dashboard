"""
Maintenance MAC List API endpoints.

歲修 MAC 清單管理 - 負責人先匯入本次歲修涉及的全部 MAC。
"""
from __future__ import annotations

import csv
import io
import re
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from sqlalchemy import select, func, delete

from app.db.base import get_session_context
from app.db.models import (
    MaintenanceMacList, ClientCategoryMember, ClientCategory,
    ClientComparison
)


# MAC 地址格式驗證
MAC_REGEX = re.compile(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$')

router = APIRouter(prefix="/mac-list", tags=["mac-list"])


class MacCreate(BaseModel):
    """新增 MAC 請求。"""
    mac_address: str
    description: str | None = None
    category: str | None = None  # 分類名稱（若不存在會自動建立）


class MacResponse(BaseModel):
    """MAC 回應。"""
    id: int
    mac_address: str
    description: str | None
    maintenance_id: str
    # 擴充欄位
    is_detected: bool | None = None  # 是否可偵測
    category_name: str | None = None  # 所屬分類
    category_id: int | None = None


class MacListStats(BaseModel):
    """MAC 清單統計。"""
    total: int
    categorized: int
    uncategorized: int


def normalize_mac(mac: str) -> str:
    """標準化 MAC 地址格式。"""
    return mac.strip().upper().replace("-", ":")


def validate_mac(mac: str) -> str:
    """驗證並標準化 MAC 地址。"""
    normalized = normalize_mac(mac)
    if not MAC_REGEX.match(normalized):
        raise HTTPException(
            status_code=400,
            detail=f"MAC 格式錯誤：{mac}"
        )
    return normalized


@router.get("/{maintenance_id}", response_model=list[MacResponse])
async def list_macs(
    maintenance_id: str,
    search: str | None = Query(None, description="搜尋 MAC 或備註"),
    limit: int = Query(1000, description="返回數量上限"),
    offset: int = Query(0, description="偏移量"),
) -> list[dict[str, Any]]:
    """獲取歲修的 MAC 清單。"""
    async with get_session_context() as session:
        stmt = (
            select(MaintenanceMacList)
            .where(MaintenanceMacList.maintenance_id == maintenance_id)
        )
        
        if search:
            keywords = search.strip().split()
            for keyword in keywords:
                search_pattern = f"%{keyword.upper()}%"
                desc_pattern = f"%{keyword}%"
                stmt = stmt.where(
                    (MaintenanceMacList.mac_address.like(search_pattern)) |
                    (MaintenanceMacList.description.like(desc_pattern))
                )
        
        stmt = stmt.order_by(MaintenanceMacList.mac_address)
        stmt = stmt.offset(offset).limit(limit)
        
        result = await session.execute(stmt)
        macs = result.scalars().all()
        
        return [
            {
                "id": m.id,
                "mac_address": m.mac_address,
                "description": m.description,
                "maintenance_id": m.maintenance_id,
            }
            for m in macs
        ]


@router.get("/{maintenance_id}/stats", response_model=MacListStats)
async def get_stats(maintenance_id: str) -> dict[str, int]:
    """獲取 MAC 清單統計。"""
    async with get_session_context() as session:
        # 獲取已導入的 MAC 清單
        mac_stmt = select(MaintenanceMacList.mac_address).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        mac_result = await session.execute(mac_stmt)
        imported_macs = {r[0] for r in mac_result.fetchall()}
        
        total = len(imported_macs)
        
        if total == 0:
            # 如果還沒導入任何 MAC，返回 0
            return {
                "total": 0,
                "categorized": 0,
                "uncategorized": 0,
            }
        
        # 獲取該歲修的活躍分類 ID
        cat_stmt = select(ClientCategory.id).where(
            ClientCategory.maintenance_id == maintenance_id,
            ClientCategory.is_active == True,
        )
        cat_result = await session.execute(cat_stmt)
        cat_ids = [r[0] for r in cat_result.fetchall()]
        
        # 已分類數量（僅計算已導入 MAC 清單中的）
        categorized = 0
        if cat_ids and imported_macs:
            member_stmt = (
                select(func.count(func.distinct(ClientCategoryMember.mac_address)))
                .where(
                    ClientCategoryMember.category_id.in_(cat_ids),
                    ClientCategoryMember.mac_address.in_(imported_macs),
                )
            )
            member_result = await session.execute(member_stmt)
            categorized = member_result.scalar() or 0
        
        return {
            "total": total,
            "categorized": categorized,
            "uncategorized": total - categorized,
        }


async def get_or_create_category(
    session, maintenance_id: str, category_name: str
) -> ClientCategory:
    """獲取或創建分類。"""
    cat_stmt = select(ClientCategory).where(
        ClientCategory.maintenance_id == maintenance_id,
        ClientCategory.name == category_name,
        ClientCategory.is_active == True,  # noqa: E712
    )
    cat_result = await session.execute(cat_stmt)
    category = cat_result.scalar_one_or_none()
    
    if not category:
        # 自動建立分類（使用預設顏色）
        colors = ["#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6"]
        existing_count_stmt = select(func.count(ClientCategory.id)).where(
            ClientCategory.maintenance_id == maintenance_id,
            ClientCategory.is_active == True,  # noqa: E712
        )
        count_result = await session.execute(existing_count_stmt)
        count = count_result.scalar() or 0
        color = colors[count % len(colors)]
        
        category = ClientCategory(
            name=category_name,
            color=color,
            maintenance_id=maintenance_id,
            is_active=True,
        )
        session.add(category)
        await session.flush()
    
    return category


async def add_mac_to_category(
    session, mac_address: str, category_id: int
) -> None:
    """將 MAC 加入分類（如果不存在的話）。"""
    existing_stmt = select(ClientCategoryMember).where(
        ClientCategoryMember.category_id == category_id,
        ClientCategoryMember.mac_address == mac_address,
    )
    existing = await session.execute(existing_stmt)
    if not existing.scalar_one_or_none():
        member = ClientCategoryMember(
            category_id=category_id,
            mac_address=mac_address,
        )
        session.add(member)


@router.post("/{maintenance_id}", response_model=MacResponse)
async def add_mac(
    maintenance_id: str,
    data: MacCreate,
) -> dict[str, Any]:
    """新增單一 MAC。"""
    mac = validate_mac(data.mac_address)
    
    async with get_session_context() as session:
        # 檢查是否已存在
        existing_stmt = select(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id,
            MaintenanceMacList.mac_address == mac,
        )
        existing = await session.execute(existing_stmt)
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"MAC {mac} 已存在於此歲修清單中"
            )
        
        # 新增 MAC
        entry = MaintenanceMacList(
            maintenance_id=maintenance_id,
            mac_address=mac,
            description=data.description,
        )
        session.add(entry)
        
        # 如果指定了分類，自動建立並加入
        category_id = None
        category_name = None
        if data.category:
            category = await get_or_create_category(
                session, maintenance_id, data.category.strip()
            )
            category_id = category.id
            category_name = category.name
            await add_mac_to_category(session, mac, category.id)
        
        await session.commit()
        await session.refresh(entry)
        
        return {
            "id": entry.id,
            "mac_address": entry.mac_address,
            "description": entry.description,
            "maintenance_id": entry.maintenance_id,
            "category_id": category_id,
            "category_name": category_name,
        }


@router.delete("/{maintenance_id}/{mac_address}")
async def remove_mac(
    maintenance_id: str,
    mac_address: str,
) -> dict[str, str]:
    """移除單一 MAC。"""
    mac = normalize_mac(mac_address)
    
    async with get_session_context() as session:
        stmt = select(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id,
            MaintenanceMacList.mac_address == mac,
        )
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()
        
        if not entry:
            raise HTTPException(status_code=404, detail="MAC 不存在")
        
        await session.delete(entry)
        await session.commit()
        
        return {"message": f"已移除 {mac}"}


@router.post("/{maintenance_id}/batch-delete")
async def batch_delete_macs(
    maintenance_id: str,
    mac_ids: list[int],
) -> dict[str, Any]:
    """批量刪除 MAC 位址。"""
    if not mac_ids:
        return {
            "success": True,
            "deleted_count": 0,
            "message": "沒有選中任何項目",
        }

    async with get_session_context() as session:
        stmt = delete(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id,
            MaintenanceMacList.id.in_(mac_ids),
        )
        result = await session.execute(stmt)
        await session.commit()

        return {
            "success": True,
            "deleted_count": result.rowcount,
            "message": f"已刪除 {result.rowcount} 筆 MAC 位址",
        }


@router.delete("/{maintenance_id}")
async def clear_all(maintenance_id: str) -> dict[str, Any]:
    """清空該歲修的所有 MAC。"""
    async with get_session_context() as session:
        stmt = delete(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        result = await session.execute(stmt)
        await session.commit()
        
        return {
            "message": f"已清空 {maintenance_id} 的 MAC 清單",
            "deleted": result.rowcount,
        }


@router.post("/{maintenance_id}/import-csv")
async def import_csv(
    maintenance_id: str,
    file: UploadFile = File(...),
    replace: bool = Query(
        False, description="是否清空現有清單後再導入"
    ),
) -> dict[str, Any]:
    """
    從 CSV 批量導入 MAC。
    
    CSV 格式: mac_address,description,category (description 和 category 可選)
    """
    async with get_session_context() as session:
        # 如果需要清空現有清單
        if replace:
            del_stmt = delete(MaintenanceMacList).where(
                MaintenanceMacList.maintenance_id == maintenance_id
            )
            await session.execute(del_stmt)
        
        # 讀取 CSV
        content = await file.read()
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("utf-8")
        
        reader = csv.DictReader(io.StringIO(text))
        
        imported = 0
        skipped = 0
        errors = []
        categories_created = set()  # 記錄本次建立的分類
        
        for row_num, row in enumerate(reader, start=2):
            raw_mac = row.get("mac_address", "").strip()
            desc = row.get("description", "").strip() or None
            category_name = row.get("category", "").strip() or None
            
            if not raw_mac:
                errors.append(f"Row {row_num}: MAC 為空")
                continue
            
            # 標準化
            mac = normalize_mac(raw_mac)
            
            # 驗證格式
            if not MAC_REGEX.match(mac):
                errors.append(f"Row {row_num}: MAC 格式錯誤 ({raw_mac})")
                continue
            
            # 檢查重複
            existing_stmt = select(MaintenanceMacList).where(
                MaintenanceMacList.maintenance_id == maintenance_id,
                MaintenanceMacList.mac_address == mac,
            )
            existing = await session.execute(existing_stmt)
            if existing.scalar_one_or_none():
                skipped += 1
                continue
            
            # 新增 MAC
            entry = MaintenanceMacList(
                maintenance_id=maintenance_id,
                mac_address=mac,
                description=desc,
            )
            session.add(entry)
            
            # 處理分類
            if category_name:
                try:
                    category = await get_or_create_category(
                        session, maintenance_id, category_name
                    )
                    await add_mac_to_category(session, mac, category.id)
                    categories_created.add(category_name)
                except Exception as e:
                    errors.append(f"Row {row_num}: 分類處理錯誤 ({e})")
            
            imported += 1
        
        await session.commit()
        
        return {
            "imported": imported,
            "skipped": skipped,
            "errors": errors[:10],
            "total_errors": len(errors),
            "categories_created": list(categories_created),
        }


@router.get("/{maintenance_id}/detailed")
async def list_macs_detailed(
    maintenance_id: str,
    search: str | None = Query(None, description="搜尋 MAC 或備註"),
    filter_status: str | None = Query(
        None, description="detected/undetected/all"
    ),
    filter_category: str | None = Query(
        None, description="uncategorized/category_id"
    ),
    limit: int = Query(500, description="返回數量上限"),
    offset: int = Query(0, description="偏移量"),
) -> list[dict[str, Any]]:
    """獲取詳細 MAC 清單（含偵測狀態、分類）。"""
    async with get_session_context() as session:
        # 獲取所有 MAC
        stmt = select(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        
        if search:
            keywords = search.strip().split()
            for keyword in keywords:
                search_pattern = f"%{keyword.upper()}%"
                desc_pattern = f"%{keyword}%"
                stmt = stmt.where(
                    (MaintenanceMacList.mac_address.like(search_pattern)) |
                    (MaintenanceMacList.description.like(desc_pattern))
                )
        
        stmt = stmt.order_by(MaintenanceMacList.mac_address)
        result = await session.execute(stmt)
        macs = result.scalars().all()
        
        mac_addresses = [m.mac_address for m in macs]
        
        # 獲取偵測狀態（從 client_comparisons）
        detected_macs = set()
        if mac_addresses:
            detect_stmt = (
                select(ClientComparison.mac_address)
                .where(
                    ClientComparison.maintenance_id == maintenance_id,
                    ClientComparison.mac_address.in_(mac_addresses),
                )
                .distinct()
            )
            detect_result = await session.execute(detect_stmt)
            detected_macs = {r[0] for r in detect_result.fetchall()}
        
        # 獲取分類資訊
        cat_stmt = select(ClientCategory).where(
            ClientCategory.maintenance_id == maintenance_id,
            ClientCategory.is_active == True,  # noqa: E712
        )
        cat_result = await session.execute(cat_stmt)
        categories = {c.id: c for c in cat_result.scalars().all()}
        cat_ids = list(categories.keys())
        
        # 獲取 MAC 的分類歸屬
        mac_categories = {}
        if cat_ids and mac_addresses:
            member_stmt = select(ClientCategoryMember).where(
                ClientCategoryMember.category_id.in_(cat_ids),
                ClientCategoryMember.mac_address.in_(mac_addresses),
            )
            member_result = await session.execute(member_stmt)
            for member in member_result.scalars().all():
                cat = categories.get(member.category_id)
                if cat:
                    mac_categories[member.mac_address] = {
                        "id": cat.id,
                        "name": cat.name,
                    }
        
        # 組合結果
        results = []
        for m in macs:
            is_detected = m.mac_address in detected_macs
            cat_info = mac_categories.get(m.mac_address)
            
            # 過濾條件
            if filter_status == "detected" and not is_detected:
                continue
            if filter_status == "undetected" and is_detected:
                continue
            if filter_category == "uncategorized" and cat_info:
                continue
            if filter_category and filter_category.isdigit():
                cat_id = int(filter_category)
                if not cat_info or cat_info["id"] != cat_id:
                    continue
            
            results.append({
                "id": m.id,
                "mac_address": m.mac_address,
                "description": m.description,
                "maintenance_id": m.maintenance_id,
                "is_detected": is_detected,
                "category_id": cat_info["id"] if cat_info else None,
                "category_name": cat_info["name"] if cat_info else None,
            })
        
        # 分頁
        return results[offset:offset + limit]


@router.get("/{maintenance_id}/export-csv")
async def export_csv(
    maintenance_id: str,
    search: str | None = Query(None, description="搜尋過濾"),
):
    """匯出 MAC 清單為 CSV（支援搜尋過濾）。"""
    from fastapi.responses import StreamingResponse

    async with get_session_context() as session:
        stmt = (
            select(MaintenanceMacList)
            .where(MaintenanceMacList.maintenance_id == maintenance_id)
        )

        # 多關鍵字搜尋
        if search:
            keywords = search.strip().split()
            for keyword in keywords:
                search_pattern = f"%{keyword.upper()}%"
                desc_pattern = f"%{keyword}%"
                stmt = stmt.where(
                    (MaintenanceMacList.mac_address.like(search_pattern)) |
                    (MaintenanceMacList.description.like(desc_pattern))
                )

        stmt = stmt.order_by(MaintenanceMacList.mac_address)
        result = await session.execute(stmt)
        macs = result.scalars().all()
        
        # 生成 CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["mac_address", "description"])
        
        for m in macs:
            writer.writerow([m.mac_address, m.description or ""])
        
        output.seek(0)
        content = "\ufeff" + output.getvalue()  # BOM for Excel
        
        return StreamingResponse(
            iter([content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{maintenance_id}_mac_list.csv"'
                )
            }
        )
