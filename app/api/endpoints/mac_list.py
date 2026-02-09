"""
Maintenance Client List API endpoints.

歲修 Client 清單管理 - 負責人先匯入本次歲修涉及的全部 Client（IP + MAC）。
"""
from __future__ import annotations

import csv
import io
import re
from typing import Any

from fastapi import APIRouter, Body, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from sqlalchemy import select, func, delete

from app.core.enums import ClientDetectionStatus, TenantGroup
from app.db.base import get_session_context
from app.db.models import (
    MaintenanceMacList, ClientCategoryMember, ClientCategory,
)
from app.services.client_comparison_service import ClientComparisonService
from app.services.system_log import write_log


# MAC 地址格式驗證
MAC_REGEX = re.compile(r'^([0-9A-F]{2}:){5}[0-9A-F]{2}$')
# IP 地址格式驗證
IP_REGEX = re.compile(
    r'^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}'
    r'(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$'
)

router = APIRouter(prefix="/mac-list", tags=["client-list"])


class ClientCreate(BaseModel):
    """新增 Client 請求（IP + MAC）。"""
    mac_address: str
    ip_address: str
    tenant_group: TenantGroup = TenantGroup.F18
    description: str | None = None
    category_ids: list[int] | None = None  # 分類 ID 列表（必須是已存在的分類）


class ClientUpdate(BaseModel):
    """更新 Client 請求（不含分類，分類請用「分類」按鈕）。"""
    mac_address: str | None = None
    ip_address: str | None = None
    tenant_group: TenantGroup | None = None
    description: str | None = None


class ClientResponse(BaseModel):
    """Client 回應。"""
    id: int
    mac_address: str
    ip_address: str
    tenant_group: TenantGroup
    detection_status: ClientDetectionStatus
    description: str | None
    maintenance_id: str
    # 擴充欄位
    category_name: str | None = None  # 所屬分類
    category_id: int | None = None


class ClientListStats(BaseModel):
    """Client 清單統計。"""
    total: int
    categorized: int
    uncategorized: int
    # 偵測狀態統計
    detected: int = 0
    mismatch: int = 0
    not_detected: int = 0
    not_checked: int = 0


# Backward compatibility aliases
MacCreate = ClientCreate
MacResponse = ClientResponse
MacListStats = ClientListStats


async def regenerate_comparisons(maintenance_id: str, session=None) -> None:
    """
    重新生成客戶端比較結果。

    當 Client 清單變更時（新增、更新、刪除），自動更新比較結果
    以確保客戶端比較頁面與 Client 清單保持同步。

    注意：使用獨立的 session 來確保能看到最新的已提交資料。
    """
    import logging
    logger = logging.getLogger(__name__)

    try:
        # 使用新的 session 來確保能看到最新的已提交資料
        async with get_session_context() as new_session:
            service = ClientComparisonService()
            comparisons = await service.generate_comparisons(
                maintenance_id=maintenance_id,
                session=new_session,
            )
            logger.info(
                f"Generated {len(comparisons)} comparisons for {maintenance_id}"
            )
            await service.save_comparisons(
                comparisons=comparisons,
                session=new_session,
            )
            logger.info(
                f"Saved {len(comparisons)} comparisons for {maintenance_id}"
            )
    except Exception as e:
        # 比較生成失敗不應阻擋主要操作，但記錄錯誤
        logger.error(
            f"Failed to regenerate comparisons for {maintenance_id}: {e}"
        )
        import traceback
        logger.error(traceback.format_exc())


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


def validate_ip(ip: str) -> str:
    """驗證 IP 地址格式。"""
    ip = ip.strip()
    if not IP_REGEX.match(ip):
        raise HTTPException(
            status_code=400,
            detail=f"IP 格式錯誤：{ip}"
        )
    return ip


def parse_tenant_group(value: str) -> TenantGroup:
    """解析 tenant_group 字串為 enum。"""
    value = value.strip().upper()
    try:
        return TenantGroup(value)
    except ValueError:
        valid = ", ".join([t.value for t in TenantGroup])
        raise HTTPException(
            status_code=400,
            detail=f"無效的 tenant_group: {value}（有效值: {valid}）"
        )


@router.get("/tenant-group-options")
async def get_tenant_group_options() -> list[dict[str, str]]:
    """獲取 TenantGroup 選項列表。"""
    return [
        {"value": t.value, "label": t.value}
        for t in TenantGroup
    ]


@router.get("/detection-status-options")
async def get_detection_status_options() -> list[dict[str, str]]:
    """獲取偵測狀態選項列表。"""
    labels = {
        ClientDetectionStatus.NOT_CHECKED: "未檢查",
        ClientDetectionStatus.DETECTED: "已偵測",
        ClientDetectionStatus.MISMATCH: "不匹配",
        ClientDetectionStatus.NOT_DETECTED: "未偵測",
    }
    return [
        {"value": s.value, "label": labels[s]}
        for s in ClientDetectionStatus
    ]


@router.get("/{maintenance_id}", response_model=list[ClientResponse])
async def list_clients(
    maintenance_id: str,
    search: str | None = Query(None, description="搜尋 MAC、IP 或備註"),
    limit: int = Query(1000, description="返回數量上限"),
    offset: int = Query(0, description="偏移量"),
) -> list[dict[str, Any]]:
    """獲取歲修的 Client 清單。"""
    async with get_session_context() as session:
        stmt = (
            select(MaintenanceMacList)
            .where(MaintenanceMacList.maintenance_id == maintenance_id)
        )

        if search:
            from sqlalchemy import and_, or_
            keywords = search.strip().split()

            # 空關鍵字列表時跳過搜尋條件（返回全部結果）
            if keywords:
                field_conditions = []
                # MAC address field (需要轉大寫)
                mac_match = and_(*[
                    MaintenanceMacList.mac_address.like(f"%{kw.upper()}%")
                    for kw in keywords
                ])
                field_conditions.append(mac_match)

                # IP address field
                ip_match = and_(*[
                    MaintenanceMacList.ip_address.like(f"%{kw}%")
                    for kw in keywords
                ])
                field_conditions.append(ip_match)

                # Description field
                desc_match = and_(*[
                    MaintenanceMacList.description.like(f"%{kw}%")
                    for kw in keywords
                ])
                field_conditions.append(desc_match)

                stmt = stmt.where(or_(*field_conditions))

        stmt = stmt.order_by(MaintenanceMacList.mac_address)
        stmt = stmt.offset(offset).limit(limit)

        result = await session.execute(stmt)
        clients = result.scalars().all()

        return [
            {
                "id": c.id,
                "mac_address": c.mac_address,
                "ip_address": c.ip_address,
                "tenant_group": c.tenant_group,
                "detection_status": c.detection_status,
                "description": c.description,
                "maintenance_id": c.maintenance_id,
            }
            for c in clients
        ]


@router.get("/{maintenance_id}/stats", response_model=ClientListStats)
async def get_stats(maintenance_id: str) -> dict[str, int]:
    """獲取 Client 清單統計。"""
    async with get_session_context() as session:
        # 獲取已導入的 Client 清單
        client_stmt = select(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )
        client_result = await session.execute(client_stmt)
        clients = client_result.scalars().all()

        total = len(clients)

        if total == 0:
            return {
                "total": 0,
                "categorized": 0,
                "uncategorized": 0,
                "detected": 0,
                "mismatch": 0,
                "not_detected": 0,
                "not_checked": 0,
            }

        imported_macs = {c.mac_address for c in clients}

        # 統計偵測狀態
        detected = sum(
            1 for c in clients
            if c.detection_status == ClientDetectionStatus.DETECTED
        )
        mismatch = sum(
            1 for c in clients
            if c.detection_status == ClientDetectionStatus.MISMATCH
        )
        not_detected = sum(
            1 for c in clients
            if c.detection_status == ClientDetectionStatus.NOT_DETECTED
        )
        not_checked = sum(
            1 for c in clients
            if c.detection_status == ClientDetectionStatus.NOT_CHECKED
        )

        # 獲取該歲修的活躍分類 ID
        cat_stmt = select(ClientCategory.id).where(
            ClientCategory.maintenance_id == maintenance_id,
            ClientCategory.is_active == True,  # noqa: E712
        )
        cat_result = await session.execute(cat_stmt)
        cat_ids = [r[0] for r in cat_result.fetchall()]

        # 已分類數量
        categorized = 0
        if cat_ids and imported_macs:
            count_distinct = func.count(func.distinct(
                ClientCategoryMember.mac_address
            ))
            member_stmt = (
                select(count_distinct)
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
            "detected": detected,
            "mismatch": mismatch,
            "not_detected": not_detected,
            "not_checked": not_checked,
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


@router.post("/{maintenance_id}", response_model=ClientResponse)
async def add_client(
    maintenance_id: str,
    data: ClientCreate,
) -> dict[str, Any]:
    """新增單一 Client（IP + MAC）。"""
    mac = validate_mac(data.mac_address)
    ip = validate_ip(data.ip_address)

    async with get_session_context() as session:
        # 檢查 MAC 是否已存在
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

        # 新增 Client
        entry = MaintenanceMacList(
            maintenance_id=maintenance_id,
            mac_address=mac,
            ip_address=ip,
            tenant_group=data.tenant_group,
            detection_status=ClientDetectionStatus.NOT_CHECKED,
            description=data.description,
        )
        session.add(entry)

        # 如果指定了分類 ID，驗證分類存在後加入（支援多選）
        category_ids = []
        category_names = []
        if data.category_ids:
            # 驗證所有分類 ID 都存在且屬於此歲修
            cat_stmt = select(ClientCategory).where(
                ClientCategory.maintenance_id == maintenance_id,
                ClientCategory.id.in_(data.category_ids),
                ClientCategory.is_active == True,  # noqa: E712
            )
            cat_result = await session.execute(cat_stmt)
            valid_categories = {c.id: c for c in cat_result.scalars().all()}

            # 檢查是否有無效的分類 ID
            invalid_ids = set(data.category_ids) - set(valid_categories.keys())
            if invalid_ids:
                raise HTTPException(
                    status_code=400,
                    detail=f"分類 ID {list(invalid_ids)} 不存在或不屬於此歲修"
                )

            # 將 MAC 加入所有指定的分類
            for cat_id in data.category_ids:
                cat = valid_categories[cat_id]
                await add_mac_to_category(session, mac, cat_id)
                category_ids.append(cat_id)
                category_names.append(cat.name)

        await session.commit()
        await session.refresh(entry)

        await write_log(
            level="INFO",
            source="api",
            summary=f"新增 Client: {mac} ({ip})",
            module="client_list",
            maintenance_id=maintenance_id,
        )

        # 自動重新生成比較結果
        await regenerate_comparisons(maintenance_id, session)

        return {
            "id": entry.id,
            "mac_address": entry.mac_address,
            "ip_address": entry.ip_address,
            "tenant_group": entry.tenant_group,
            "detection_status": entry.detection_status,
            "description": entry.description,
            "maintenance_id": entry.maintenance_id,
            "category_id": category_ids[0] if category_ids else None,
            "category_name": ";".join(category_names) if category_names else None,
        }


@router.put("/{maintenance_id}/{client_id}", response_model=ClientResponse)
async def update_client(
    maintenance_id: str,
    client_id: int,
    data: ClientUpdate,
) -> dict[str, Any]:
    """
    更新單一 Client（IP + MAC）。

    驗證邏輯：
    - MAC 格式驗證（若提供）
    - IP 格式驗證（若提供）
    - MAC 唯一性檢查（若變更 MAC，確保新 MAC 不與其他 Client 重複）
    """
    async with get_session_context() as session:
        # 查詢現有 Client
        stmt = select(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id,
            MaintenanceMacList.id == client_id,
        )
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()

        if not entry:
            raise HTTPException(
                status_code=404,
                detail=f"Client ID {client_id} 不存在"
            )

        # 驗證並更新 MAC（若提供）
        if data.mac_address is not None:
            new_mac = validate_mac(data.mac_address)

            # 檢查 MAC 唯一性（若變更了 MAC）
            if new_mac != entry.mac_address:
                existing_stmt = select(MaintenanceMacList).where(
                    MaintenanceMacList.maintenance_id == maintenance_id,
                    MaintenanceMacList.mac_address == new_mac,
                    MaintenanceMacList.id != client_id,  # 排除自己
                )
                existing = await session.execute(existing_stmt)
                if existing.scalar_one_or_none():
                    raise HTTPException(
                        status_code=400,
                        detail=f"MAC {new_mac} 已存在於此歲修清單中"
                    )
                entry.mac_address = new_mac

        # 驗證並更新 IP（若提供）
        if data.ip_address is not None:
            new_ip = validate_ip(data.ip_address)
            entry.ip_address = new_ip

        # 更新其他欄位（若提供）
        if data.tenant_group is not None:
            entry.tenant_group = data.tenant_group

        if data.description is not None:
            entry.description = data.description if data.description else None

        # 注意：編輯功能不處理分類，請使用「分類」按鈕修改分類

        await session.commit()
        await session.refresh(entry)

        await write_log(
            level="INFO",
            source="api",
            summary=f"更新 Client: {entry.mac_address}",
            module="client_list",
            maintenance_id=maintenance_id,
        )

        # 自動重新生成比較結果（MAC 變更可能影響比較）
        await regenerate_comparisons(maintenance_id, session)

        return {
            "id": entry.id,
            "mac_address": entry.mac_address,
            "ip_address": entry.ip_address,
            "tenant_group": entry.tenant_group,
            "detection_status": entry.detection_status,
            "description": entry.description,
            "maintenance_id": entry.maintenance_id,
            "category_id": None,
            "category_name": None,
        }


@router.delete("/{maintenance_id}/{mac_address}")
async def remove_mac(
    maintenance_id: str,
    mac_address: str,
) -> dict[str, str]:
    """移除單一 MAC（同時從所有分類中移除）。"""
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

        # 先從所有分類中移除此 MAC
        cat_stmt = select(ClientCategory.id).where(
            ClientCategory.maintenance_id == maintenance_id,
            ClientCategory.is_active == True,  # noqa: E712
        )
        cat_result = await session.execute(cat_stmt)
        cat_ids = [r[0] for r in cat_result.fetchall()]

        if cat_ids:
            del_member_stmt = delete(ClientCategoryMember).where(
                ClientCategoryMember.category_id.in_(cat_ids),
                ClientCategoryMember.mac_address == mac,
            )
            await session.execute(del_member_stmt)

        await session.delete(entry)
        await session.commit()

        await write_log(
            level="WARNING",
            source="api",
            summary=f"刪除 Client: {mac}",
            module="client_list",
            maintenance_id=maintenance_id,
        )

        # 自動重新生成比較結果
        await regenerate_comparisons(maintenance_id, session)

        return {"message": f"已移除 {mac}"}


@router.post("/{maintenance_id}/batch-delete")
async def batch_delete_macs(
    maintenance_id: str,
    mac_ids: list[int] = Body(..., embed=True),
) -> dict[str, Any]:
    """批量刪除 MAC 位址（同時從所有分類中移除）。"""
    if not mac_ids:
        return {
            "success": True,
            "deleted_count": 0,
            "message": "沒有選中任何項目",
        }

    async with get_session_context() as session:
        # 先查詢要刪除的 MAC 地址
        mac_stmt = select(MaintenanceMacList.mac_address).where(
            MaintenanceMacList.maintenance_id == maintenance_id,
            MaintenanceMacList.id.in_(mac_ids),
        )
        mac_result = await session.execute(mac_stmt)
        macs_to_delete = [r[0] for r in mac_result.fetchall()]

        # 從分類中移除這些 MAC
        if macs_to_delete:
            cat_stmt = select(ClientCategory.id).where(
                ClientCategory.maintenance_id == maintenance_id,
                ClientCategory.is_active == True,  # noqa: E712
            )
            cat_result = await session.execute(cat_stmt)
            cat_ids = [r[0] for r in cat_result.fetchall()]

            if cat_ids:
                del_member_stmt = delete(ClientCategoryMember).where(
                    ClientCategoryMember.category_id.in_(cat_ids),
                    ClientCategoryMember.mac_address.in_(macs_to_delete),
                )
                await session.execute(del_member_stmt)

        # 刪除 MAC 記錄
        stmt = delete(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id,
            MaintenanceMacList.id.in_(mac_ids),
        )
        result = await session.execute(stmt)
        await session.commit()

        # 自動重新生成比較結果
        if result.rowcount > 0:
            await write_log(
                level="WARNING",
                source="api",
                summary=f"批量刪除 Client: {result.rowcount} 筆",
                module="client_list",
                maintenance_id=maintenance_id,
            )
            await regenerate_comparisons(maintenance_id, session)

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

        await write_log(
            level="WARNING",
            source="api",
            summary=f"清空 Client 清單: {result.rowcount} 筆",
            module="client_list",
            maintenance_id=maintenance_id,
        )

        # 自動重新生成比較結果（清空後會是空的）
        await regenerate_comparisons(maintenance_id, session)

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
    從 CSV 批量導入 Client。

    CSV 格式: mac_address,ip_address,tenant_group,description,category
    - mac_address: 必填
    - ip_address: 必填
    - tenant_group: 選填（預設 F18，有效值: F18/F6/AP/F14/F12）
    - description: 選填
    - category: 選填（必須是已存在的分類名稱，可用分號分隔多個分類，如 "EQP;AMHS"）
    """
    async with get_session_context() as session:
        # 如果需要清空現有清單
        if replace:
            del_stmt = delete(MaintenanceMacList).where(
                MaintenanceMacList.maintenance_id == maintenance_id
            )
            await session.execute(del_stmt)

        # 先載入所有現有分類（用於驗證）
        cat_stmt = select(ClientCategory).where(
            ClientCategory.maintenance_id == maintenance_id,
            ClientCategory.is_active == True,  # noqa: E712
        )
        cat_result = await session.execute(cat_stmt)
        existing_categories = {c.name: c for c in cat_result.scalars().all()}

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
        categories_used = set()

        valid_tenant_groups = {t.value for t in TenantGroup}

        for row_num, row in enumerate(reader, start=2):
            raw_mac = row.get("mac_address", "").strip()
            raw_ip = row.get("ip_address", "").strip()
            raw_tg = row.get("tenant_group", "F18").strip().upper()
            desc = row.get("description", "").strip() or None
            category_name = row.get("category", "").strip() or None

            # 驗證 MAC
            if not raw_mac:
                errors.append(f"Row {row_num}: MAC 為空")
                continue
            mac = normalize_mac(raw_mac)
            if not MAC_REGEX.match(mac):
                errors.append(f"Row {row_num}: MAC 格式錯誤 ({raw_mac})")
                continue

            # 驗證 IP
            if not raw_ip:
                errors.append(f"Row {row_num}: IP 為空")
                continue
            if not IP_REGEX.match(raw_ip):
                errors.append(f"Row {row_num}: IP 格式錯誤 ({raw_ip})")
                continue

            # 驗證 tenant_group
            if raw_tg and raw_tg not in valid_tenant_groups:
                errors.append(
                    f"Row {row_num}: 無效的 tenant_group ({raw_tg})"
                )
                continue
            tenant_group = TenantGroup(raw_tg) if raw_tg else TenantGroup.F18

            # 檢查重複
            existing_stmt = select(MaintenanceMacList).where(
                MaintenanceMacList.maintenance_id == maintenance_id,
                MaintenanceMacList.mac_address == mac,
            )
            existing = await session.execute(existing_stmt)
            if existing.scalar_one_or_none():
                skipped += 1
                continue

            # 先驗證所有分類（必須全部存在才能匯入）
            valid_cat_list = []
            invalid_cats = []
            if category_name:
                cat_names = [
                    name.strip() for name in category_name.split(";")
                    if name.strip()
                ]
                for cat_name in cat_names:
                    if cat_name in existing_categories:
                        valid_cat_list.append(existing_categories[cat_name])
                    else:
                        invalid_cats.append(cat_name)

            # 如果有任何無效分類，跳過整行
            if invalid_cats:
                errors.append(
                    f"Row {row_num}: 分類 {invalid_cats} 不存在，整行已跳過"
                )
                continue

            # 新增 Client
            entry = MaintenanceMacList(
                maintenance_id=maintenance_id,
                mac_address=mac,
                ip_address=raw_ip,
                tenant_group=tenant_group,
                detection_status=ClientDetectionStatus.NOT_CHECKED,
                description=desc,
            )
            session.add(entry)

            # 將 MAC 加入所有有效分類
            for category in valid_cat_list:
                await add_mac_to_category(session, mac, category.id)
                categories_used.add(category.name)

            imported += 1

        await session.commit()

        # 自動重新生成比較結果
        if imported > 0:
            await write_log(
                level="INFO",
                source="api",
                summary=f"CSV 匯入 Client: 新增 {imported}, 跳過 {skipped}",
                module="client_list",
                maintenance_id=maintenance_id,
            )
            await regenerate_comparisons(maintenance_id, session)

        return {
            "imported": imported,
            "skipped": skipped,
            "errors": errors,  # 返回所有錯誤，讓前端顯示完整錯誤清單
            "total_errors": len(errors),
            "categories_used": list(categories_used),
        }


@router.get("/{maintenance_id}/detailed")
async def list_clients_detailed(
    maintenance_id: str,
    search: str | None = Query(None, description="搜尋 MAC、IP 或備註"),
    filter_status: str | None = Query(
        None, description="detected/mismatch/not_detected/not_checked/all"
    ),
    filter_category: str | None = Query(
        None, description="uncategorized/category_id"
    ),
    limit: int = Query(500, description="返回數量上限"),
    offset: int = Query(0, description="偏移量"),
) -> list[dict[str, Any]]:
    """獲取詳細 Client 清單（含偵測狀態、分類）。"""
    async with get_session_context() as session:
        # 獲取所有 Client
        stmt = select(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id
        )

        if search:
            from sqlalchemy import and_, or_
            keywords = search.strip().split()

            # 空關鍵字列表時跳過搜尋條件（返回全部結果）
            if keywords:
                field_conditions = []
                mac_match = and_(*[
                    MaintenanceMacList.mac_address.like(f"%{kw.upper()}%")
                    for kw in keywords
                ])
                field_conditions.append(mac_match)

                ip_match = and_(*[
                    MaintenanceMacList.ip_address.like(f"%{kw}%")
                    for kw in keywords
                ])
                field_conditions.append(ip_match)

                desc_match = and_(*[
                    MaintenanceMacList.description.like(f"%{kw}%")
                    for kw in keywords
                ])
                field_conditions.append(desc_match)

                stmt = stmt.where(or_(*field_conditions))

        stmt = stmt.order_by(MaintenanceMacList.mac_address)
        result = await session.execute(stmt)
        clients = result.scalars().all()

        mac_addresses = [c.mac_address for c in clients]

        # 獲取分類資訊
        cat_stmt = select(ClientCategory).where(
            ClientCategory.maintenance_id == maintenance_id,
            ClientCategory.is_active == True,  # noqa: E712
        )
        cat_result = await session.execute(cat_stmt)
        categories = {c.id: c for c in cat_result.scalars().all()}
        cat_ids = list(categories.keys())

        # 獲取 MAC 的分類歸屬（支援多分類）
        mac_categories: dict[str, list[dict]] = {}
        if cat_ids and mac_addresses:
            member_stmt = select(ClientCategoryMember).where(
                ClientCategoryMember.category_id.in_(cat_ids),
                ClientCategoryMember.mac_address.in_(mac_addresses),
            )
            member_result = await session.execute(member_stmt)
            for member in member_result.scalars().all():
                cat = categories.get(member.category_id)
                if cat:
                    if member.mac_address not in mac_categories:
                        mac_categories[member.mac_address] = []
                    mac_categories[member.mac_address].append({
                        "id": cat.id,
                        "name": cat.name,
                    })

        # 組合結果
        results = []
        for c in clients:
            cat_list = mac_categories.get(c.mac_address, [])
            if c.detection_status:
                status = c.detection_status.value
            else:
                status = "not_checked"

            # 過濾條件 - 偵測狀態
            if filter_status and filter_status != "all":
                if status != filter_status:
                    continue

            # 過濾條件 - 分類
            if filter_category == "uncategorized" and cat_list:
                continue
            if filter_category and filter_category.isdigit():
                cat_id = int(filter_category)
                cat_ids_in_list = [c["id"] for c in cat_list]
                if cat_id not in cat_ids_in_list:
                    continue

            # 多分類：用分號連接分類名稱
            category_names = ";".join([c["name"] for c in cat_list])
            category_ids = [c["id"] for c in cat_list]

            results.append({
                "id": c.id,
                "mac_address": c.mac_address,
                "ip_address": c.ip_address,
                "tenant_group": c.tenant_group,
                "detection_status": c.detection_status,
                "description": c.description,
                "maintenance_id": c.maintenance_id,
                # 保留舊欄位（第一個分類）供相容
                "category_id": cat_list[0]["id"] if cat_list else None,
                "category_name": category_names if category_names else None,
                # 新增多分類欄位
                "category_ids": category_ids,
            })

        # 分頁
        return results[offset:offset + limit]


@router.get("/{maintenance_id}/export-csv")
async def export_csv(
    maintenance_id: str,
    search: str | None = Query(None, description="搜尋過濾"),
    filter_status: str | None = Query(
        None, description="detected/mismatch/not_detected/not_checked/all"
    ),
    filter_category: str | None = Query(
        None, description="uncategorized/category_id"
    ),
):
    """匯出 Client 清單為 CSV（支援搜尋及篩選）。"""
    from fastapi.responses import StreamingResponse

    async with get_session_context() as session:
        stmt = (
            select(MaintenanceMacList)
            .where(MaintenanceMacList.maintenance_id == maintenance_id)
        )

        # 多關鍵字搜尋
        if search:
            from sqlalchemy import and_, or_
            keywords = search.strip().split()

            # 空關鍵字列表時跳過搜尋條件（返回全部結果）
            if keywords:
                field_conditions = []
                mac_match = and_(*[
                    MaintenanceMacList.mac_address.like(f"%{kw.upper()}%")
                    for kw in keywords
                ])
                field_conditions.append(mac_match)

                ip_match = and_(*[
                    MaintenanceMacList.ip_address.like(f"%{kw}%")
                    for kw in keywords
                ])
                field_conditions.append(ip_match)

                desc_match = and_(*[
                    MaintenanceMacList.description.like(f"%{kw}%")
                    for kw in keywords
                ])
                field_conditions.append(desc_match)

                stmt = stmt.where(or_(*field_conditions))

        stmt = stmt.order_by(MaintenanceMacList.mac_address)
        result = await session.execute(stmt)
        clients = result.scalars().all()

        # 獲取分類資訊（支援多分類）
        cat_stmt = select(ClientCategory).where(
            ClientCategory.maintenance_id == maintenance_id,
            ClientCategory.is_active == True,  # noqa: E712
        )
        cat_result = await session.execute(cat_stmt)
        categories = {c.id: c for c in cat_result.scalars().all()}
        cat_ids = list(categories.keys())

        # 獲取 MAC 的分類歸屬（支援多分類）
        mac_categories: dict[str, list[str]] = {}
        mac_cat_ids: dict[str, list[int]] = {}
        if cat_ids:
            mac_addresses = [c.mac_address for c in clients]
            if mac_addresses:
                member_stmt = select(ClientCategoryMember).where(
                    ClientCategoryMember.category_id.in_(cat_ids),
                    ClientCategoryMember.mac_address.in_(mac_addresses),
                )
                member_result = await session.execute(member_stmt)
                for member in member_result.scalars().all():
                    cat = categories.get(member.category_id)
                    if cat:
                        if member.mac_address not in mac_categories:
                            mac_categories[member.mac_address] = []
                            mac_cat_ids[member.mac_address] = []
                        mac_categories[member.mac_address].append(cat.name)
                        mac_cat_ids[member.mac_address].append(cat.id)

        # 過濾並生成 CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "mac_address", "ip_address", "tenant_group",
            "description", "category"
        ])

        for c in clients:
            # 偵測狀態過濾
            status = c.detection_status.value if c.detection_status else "not_checked"
            if filter_status and filter_status != "all":
                if status != filter_status:
                    continue

            # 分類過濾
            cat_names = mac_categories.get(c.mac_address, [])
            cat_id_list = mac_cat_ids.get(c.mac_address, [])
            if filter_category == "uncategorized" and cat_names:
                continue
            if filter_category and filter_category.isdigit():
                target_cat_id = int(filter_category)
                if target_cat_id not in cat_id_list:
                    continue

            tg = c.tenant_group.value if c.tenant_group else "F18"
            # 多分類用分號連接
            category_str = ";".join(cat_names) if cat_names else ""
            writer.writerow([
                c.mac_address,
                c.ip_address,
                tg,
                c.description or "",
                category_str,
            ])

        output.seek(0)
        content = "\ufeff" + output.getvalue()  # BOM for Excel

        return StreamingResponse(
            iter([content]),
            media_type="text/csv",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{maintenance_id}_client_list.csv"'
                )
            }
        )


@router.get("/{maintenance_id}/template-csv")
async def download_template(maintenance_id: str):
    """下載 Client 清單 CSV 範本。"""
    from fastapi.responses import StreamingResponse

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "mac_address", "ip_address", "tenant_group", "description", "category"
    ])
    # 範例資料
    writer.writerow([
        "AA:BB:CC:DD:EE:01", "192.168.1.100", "F18", "單一分類範例", "生產機台"
    ])
    writer.writerow([
        "AA:BB:CC:DD:EE:02", "192.168.1.101", "F6", "多分類範例(用分號分隔)", "EQP;AMHS"
    ])
    writer.writerow([
        "AA:BB:CC:DD:EE:03", "192.168.1.102", "AP", "無分類範例", ""
    ])

    output.seek(0)
    content = "\ufeff" + output.getvalue()

    return StreamingResponse(
        iter([content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                'attachment; filename="client_list_template.csv"'
            )
        }
    )


@router.post("/{maintenance_id}/detect")
async def detect_clients(maintenance_id: str) -> dict[str, Any]:
    """
    觸發客戶端偵測。

    流程：
    1. 從 Client 清單載入所有 IP + MAC + tenant_group
    2. 從 ARP 資料檢查 IP-MAC 是否匹配
    3. 按 tenant_group 分組呼叫 GNMS Ping 檢查可達性
    4. 更新偵測狀態：DETECTED / MISMATCH / NOT_DETECTED

    Returns:
        偵測統計
    """
    from app.services.client_collection_service import (
        get_client_collection_service,
    )

    service = get_client_collection_service()
    result = await service.detect_clients(maintenance_id)

    await write_log(
        level="INFO",
        source="api",
        summary="觸發客戶端偵測",
        module="client_list",
        maintenance_id=maintenance_id,
    )

    # 偵測完成後自動重新生成比較結果
    async with get_session_context() as session:
        await regenerate_comparisons(maintenance_id, session)

    return result
