"""
Maintenance Client List API endpoints.

歲修 Client 清單管理 - 負責人先匯入本次歲修涉及的全部 Client（IP + MAC）。
"""
from __future__ import annotations

import csv
import io
import re
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel

from app.api.endpoints.auth import get_current_user, require_write
import sqlalchemy as sa
from sqlalchemy import case, select, func, delete

from app.core.enums import ClientDetectionStatus, TenantGroup
from app.db.base import get_session_context
from app.core.enums import UserRole
from app.db.models import (
    MaintenanceDeviceList, MaintenanceMacList,
    ClientCategoryMember, ClientCategory, User,
    PingRecord, LatestCollectionBatch, Case, ClientRecord, ClientComparison,
    SeverityOverride, ReferenceClient, LatestClientRecord,
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
    default_assignee: str | None = None
    category_ids: list[int] | None = None  # 分類 ID 列表（必須是已存在的分類）


class ClientUpdate(BaseModel):
    """更新 Client 請求（不含分類，分類請用「分類」按鈕）。"""
    mac_address: str | None = None
    ip_address: str | None = None
    tenant_group: TenantGroup | None = None
    description: str | None = None
    default_assignee: str | None = None


class ClientResponse(BaseModel):
    """Client 回應。"""
    id: int
    mac_address: str
    ip_address: str
    tenant_group: TenantGroup
    detection_status: ClientDetectionStatus
    description: str | None
    default_assignee: str | None = None
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


async def resolve_default_assignee(
    session, display_name: str | None,
) -> str:
    """
    解析 default_assignee：驗證使用者存在，或回傳系統管理員。

    - 有指定 → 查 User 表驗證 display_name 存在且 is_active
    - 未指定 → 取 ROOT 使用者的 display_name 作為預設
    """
    if display_name and display_name.strip():
        name = display_name.strip()
        stmt = select(User).where(
            User.display_name == name,
            User.is_active == True,  # noqa: E712
        )
        result = await session.execute(stmt)
        if not result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"使用者 '{name}' 不存在或未啟用",
            )
        return name

    # 未指定 → 取第一個 ROOT 使用者
    stmt = select(User.display_name).where(
        User.role == UserRole.ROOT,
        User.is_active == True,  # noqa: E712
    ).limit(1)
    result = await session.execute(stmt)
    row = result.first()
    return row[0] if row else "系統管理員"


@router.get("/tenant-group-options")
async def get_tenant_group_options(
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> list[dict[str, str]]:
    """獲取 TenantGroup 選項列表。"""
    return [
        {"value": t.value, "label": t.value}
        for t in TenantGroup
    ]


@router.get("/detection-status-options")
async def get_detection_status_options(
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> list[dict[str, str]]:
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
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
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

        # 子查詢：從 ping_records 取每個 IP 的最新 ping 結果
        latest_ping_batches = (
            select(LatestCollectionBatch.batch_id)
            .where(
                LatestCollectionBatch.maintenance_id == maintenance_id,
                LatestCollectionBatch.collection_type == "gnms_ping",
            )
        )
        ping_by_ip = (
            select(
                PingRecord.target.label("ip"),
                PingRecord.is_reachable,
            )
            .where(PingRecord.batch_id.in_(latest_ping_batches))
            .subquery()
        )
        stmt = stmt.outerjoin(
            ping_by_ip,
            MaintenanceMacList.ip_address == ping_by_ip.c.ip,
        )
        # 排序：ping 不可達優先
        stmt = stmt.order_by(
            case(
                (ping_by_ip.c.is_reachable == None, 0),   # noqa: E711
                (ping_by_ip.c.is_reachable == False, 1),   # noqa: E712
                else_=2,
            ),
            MaintenanceMacList.mac_address,
        )
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
                "default_assignee": c.default_assignee,
                "maintenance_id": c.maintenance_id,
            }
            for c in clients
        ]


@router.get("/{maintenance_id}/stats", response_model=ClientListStats)
async def get_stats(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, int]:
    """獲取 Client 清單統計（SQL 聚合，不載入全部資料）。"""
    async with get_session_context() as session:
        # 一次 SQL 取得 total 和各 detection_status 計數
        status_stmt = (
            select(
                MaintenanceMacList.detection_status,
                func.count().label("cnt"),
            )
            .where(MaintenanceMacList.maintenance_id == maintenance_id)
            .group_by(MaintenanceMacList.detection_status)
        )
        status_result = await session.execute(status_stmt)
        status_counts = {row[0]: row[1] for row in status_result.fetchall()}

        total = sum(status_counts.values())
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

        detected = status_counts.get(ClientDetectionStatus.DETECTED, 0)
        mismatch = status_counts.get(ClientDetectionStatus.MISMATCH, 0)
        not_detected = status_counts.get(ClientDetectionStatus.NOT_DETECTED, 0)
        not_checked = status_counts.get(ClientDetectionStatus.NOT_CHECKED, 0)

        # 已分類數量：用子查詢避免載入所有 Client
        active_cats = (
            select(ClientCategory.id)
            .where(
                ClientCategory.maintenance_id == maintenance_id,
                ClientCategory.is_active == True,  # noqa: E712
            )
            .subquery()
        )
        client_subq = (
            select(MaintenanceMacList.id)
            .where(MaintenanceMacList.maintenance_id == maintenance_id)
            .subquery()
        )
        cat_count_stmt = (
            select(func.count(func.distinct(ClientCategoryMember.client_id)))
            .where(
                ClientCategoryMember.category_id.in_(select(active_cats.c.id)),
                ClientCategoryMember.client_id.in_(select(client_subq.c.id)),
            )
        )
        cat_result = await session.execute(cat_count_stmt)
        categorized = cat_result.scalar() or 0

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
    session, mac_address: str, category_id: int,
    client_id: int | None = None,
) -> None:
    """將 Client 加入分類（如果不存在的話）。"""
    existing_stmt = select(ClientCategoryMember).where(
        ClientCategoryMember.category_id == category_id,
        ClientCategoryMember.client_id == client_id,
    ) if client_id else select(ClientCategoryMember).where(
        ClientCategoryMember.category_id == category_id,
        ClientCategoryMember.mac_address == mac_address,
    )
    existing = await session.execute(existing_stmt)
    if not existing.scalar_one_or_none():
        member = ClientCategoryMember(
            category_id=category_id,
            mac_address=mac_address,
            client_id=client_id,
        )
        session.add(member)


@router.post("/{maintenance_id}", response_model=ClientResponse)
async def add_client(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(require_write())],
    data: ClientCreate,
) -> dict[str, Any]:
    """新增單一 Client（IP + MAC）。"""
    mac = validate_mac(data.mac_address)
    ip = validate_ip(data.ip_address)

    async with get_session_context() as session:
        # 解析 default_assignee
        assignee = await resolve_default_assignee(
            session, data.default_assignee,
        )

        # 新增 Client
        entry = MaintenanceMacList(
            maintenance_id=maintenance_id,
            mac_address=mac,
            ip_address=ip,
            tenant_group=data.tenant_group,
            detection_status=ClientDetectionStatus.NOT_CHECKED,
            description=data.description,
            default_assignee=assignee,
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

            # 將 Client 加入所有指定的分類
            await session.flush()  # 確保 entry.id 已生成
            for cat_id in data.category_ids:
                cat = valid_categories[cat_id]
                await add_mac_to_category(session, mac, cat_id, client_id=entry.id)
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
            "default_assignee": entry.default_assignee,
            "maintenance_id": entry.maintenance_id,
            "category_id": category_ids[0] if category_ids else None,
            "category_name": ";".join(category_names) if category_names else None,
        }


@router.put("/{maintenance_id}/{client_id}", response_model=ClientResponse)
async def update_client(
    maintenance_id: str,
    client_id: int,
    _user: Annotated[dict[str, Any], Depends(require_write())],
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

        if data.default_assignee is not None:
            assignee = await resolve_default_assignee(
                session, data.default_assignee or None,
            )
            entry.default_assignee = assignee

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
            "default_assignee": entry.default_assignee,
            "maintenance_id": entry.maintenance_id,
            "category_id": None,
            "category_name": None,
        }


@router.delete("/{maintenance_id}/by-id/{client_id}")
async def remove_client(
    maintenance_id: str,
    client_id: int,
    _user: Annotated[dict[str, Any], Depends(require_write())],
) -> dict[str, str]:
    """移除單一 Client（同時從所有分類中移除）。"""
    async with get_session_context() as session:
        stmt = select(MaintenanceMacList).where(
            MaintenanceMacList.maintenance_id == maintenance_id,
            MaintenanceMacList.id == client_id,
        )
        result = await session.execute(stmt)
        entry = result.scalar_one_or_none()

        if not entry:
            raise HTTPException(status_code=404, detail="Client 不存在")

        mac = entry.mac_address

        # 刪除分類成員（by client_id）
        del_member_stmt = delete(ClientCategoryMember).where(
            ClientCategoryMember.client_id == client_id,
        )
        await session.execute(del_member_stmt)

        # 刪除對應的 Case（CaseNote 有 CASCADE 自動刪除）
        # 同時用 client_id 和 mac_address 確保覆蓋新舊資料
        del_case_stmt = delete(Case).where(
            Case.maintenance_id == maintenance_id,
            sa.or_(
                Case.client_id == client_id,
                Case.mac_address == mac,
            ),
        )
        await session.execute(del_case_stmt)

        # 刪除關聯的 SeverityOverride / ReferenceClient / LatestClientRecord
        for model in (SeverityOverride, ReferenceClient, LatestClientRecord):
            await session.execute(
                delete(model).where(
                    model.maintenance_id == maintenance_id,
                    sa.or_(
                        model.client_id == client_id,
                        model.mac_address == mac,
                    ),
                )
            )

        # 刪除 ClientRecord（SET NULL FK，手動清除避免孤兒）
        await session.execute(
            delete(ClientRecord).where(
                ClientRecord.maintenance_id == maintenance_id,
                sa.or_(
                    ClientRecord.client_id == client_id,
                    ClientRecord.mac_address == mac,
                ),
            )
        )

        # 刪除 ClientComparison
        await session.execute(
            delete(ClientComparison).where(
                ClientComparison.maintenance_id == maintenance_id,
                sa.or_(
                    ClientComparison.client_id == client_id,
                    ClientComparison.mac_address == mac,
                ),
            )
        )

        await session.delete(entry)
        await session.commit()

    await write_log(
        level="WARNING",
        source="api",
        summary=f"刪除 Client: {mac} (ID={client_id})",
        module="client_list",
        maintenance_id=maintenance_id,
    )

    # 自動重新生成比較結果（new session context）
    async with get_session_context() as session2:
        await regenerate_comparisons(maintenance_id, session2)

    return {"message": f"已移除 {mac}"}


@router.post("/{maintenance_id}/batch-delete")
async def batch_delete_macs(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(require_write())],
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
        # 從分類中移除這些 client
        del_member_stmt = delete(ClientCategoryMember).where(
            ClientCategoryMember.client_id.in_(mac_ids),
        )
        await session.execute(del_member_stmt)

        # 刪除對應的 Case（CaseNote 有 CASCADE 自動刪除）
        del_case_stmt = delete(Case).where(
            Case.maintenance_id == maintenance_id,
            Case.client_id.in_(mac_ids),
        )
        await session.execute(del_case_stmt)

        # 刪除關聯的 SeverityOverride / ReferenceClient / LatestClientRecord
        for model in (SeverityOverride, ReferenceClient, LatestClientRecord):
            await session.execute(
                delete(model).where(
                    model.maintenance_id == maintenance_id,
                    model.client_id.in_(mac_ids),
                )
            )

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
async def clear_all(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(require_write())],
) -> dict[str, Any]:
    """清空該歲修的所有 MAC。"""
    async with get_session_context() as session:
        # 刪除所有 Case（CaseNote 有 CASCADE 自動刪除）
        del_case_stmt = delete(Case).where(
            Case.maintenance_id == maintenance_id,
        )
        await session.execute(del_case_stmt)

        # 刪除所有 SeverityOverride / ReferenceClient / LatestClientRecord
        for model in (SeverityOverride, ReferenceClient, LatestClientRecord):
            await session.execute(
                delete(model).where(
                    model.maintenance_id == maintenance_id,
                )
            )

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
    _user: Annotated[dict[str, Any], Depends(require_write())],
    file: UploadFile = File(...),
    replace: bool = Query(
        False, description="是否清空現有清單後再導入"
    ),
) -> dict[str, Any]:
    """
    從 CSV 批量導入 Client。

    CSV 格式: mac_address,ip_address,tenant_group,description,default_assignee
    - mac_address: 必填
    - ip_address: 必填
    - tenant_group: 選填（預設 F18，有效值: F18/F6/AP/F14/F12）
    - description: 選填
    - default_assignee: 選填（必須是已存在的使用者顯示名稱，未指定則預設為系統管理員）
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

        valid_tenant_groups = {t.value for t in TenantGroup}

        for row_num, row in enumerate(reader, start=2):
            raw_mac = row.get("mac_address", "").strip()
            raw_ip = row.get("ip_address", "").strip()
            raw_tg = row.get("tenant_group", "F18").strip().upper()
            desc = row.get("description", "").strip() or None
            raw_assignee = row.get("default_assignee", "").strip() or None

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

            # 驗證 default_assignee
            try:
                assignee = await resolve_default_assignee(
                    session, raw_assignee,
                )
            except HTTPException as exc:
                errors.append(f"Row {row_num}: {exc.detail}")
                continue

            # 新增 Client
            entry = MaintenanceMacList(
                maintenance_id=maintenance_id,
                mac_address=mac,
                ip_address=raw_ip,
                tenant_group=tenant_group,
                detection_status=ClientDetectionStatus.NOT_CHECKED,
                description=desc,
                default_assignee=assignee,
            )
            session.add(entry)
            imported += 1

        await session.commit()

        # 自動重新生成比較結果 + 同步案件
        if imported > 0:
            await write_log(
                level="INFO",
                source="api",
                summary=f"CSV 匯入 Client: 新增 {imported}, 跳過 {skipped}",
                module="client_list",
                maintenance_id=maintenance_id,
            )
            await regenerate_comparisons(maintenance_id, session)

            # 自動同步案件（為新匯入的 MAC 建立 Case 記錄）
            from app.services.case_service import CaseService
            case_svc = CaseService()
            await case_svc.sync_cases(maintenance_id, session)

        return {
            "imported": imported,
            "skipped": skipped,
            "errors": errors,  # 返回所有錯誤，讓前端顯示完整錯誤清單
            "total_errors": len(errors),
        }


@router.get("/{maintenance_id}/detailed")
async def list_clients_detailed(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
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

        # ── 在 SQL 層套用 filter_status ──
        if filter_status and filter_status != "all":
            from app.core.enums import ClientDetectionStatus as CDS
            _status_map = {s.value: s for s in CDS}
            status_enum = _status_map.get(filter_status)
            if status_enum:
                stmt = stmt.where(
                    MaintenanceMacList.detection_status == status_enum
                )
            elif filter_status == "not_checked":
                stmt = stmt.where(
                    MaintenanceMacList.detection_status.is_(None)
                )

        # ── 在 SQL 層套用 filter_category ──
        # 需要先查分類再 join，以便在 DB 層做過濾
        cat_stmt = select(ClientCategory).where(
            ClientCategory.maintenance_id == maintenance_id,
            ClientCategory.is_active == True,  # noqa: E712
        )
        cat_result = await session.execute(cat_stmt)
        categories = {c.id: c for c in cat_result.scalars().all()}
        cat_ids = list(categories.keys())

        if filter_category == "uncategorized" and cat_ids:
            # 找出所有有分類的 client，然後排除
            categorized_clients = (
                select(ClientCategoryMember.client_id)
                .where(ClientCategoryMember.category_id.in_(cat_ids))
                .distinct()
                .subquery()
            )
            stmt = stmt.where(
                MaintenanceMacList.id.notin_(
                    select(categorized_clients.c.client_id)
                )
            )
        elif filter_category and filter_category.isdigit():
            cat_id = int(filter_category)
            target_clients = (
                select(ClientCategoryMember.client_id)
                .where(ClientCategoryMember.category_id == cat_id)
                .subquery()
            )
            stmt = stmt.where(
                MaintenanceMacList.id.in_(
                    select(target_clients.c.client_id)
                )
            )

        # ── SQL 層分頁（ping 不可達優先，直接讀 ping_records）──
        latest_ping_batches_d = (
            select(LatestCollectionBatch.batch_id)
            .where(
                LatestCollectionBatch.maintenance_id == maintenance_id,
                LatestCollectionBatch.collection_type == "gnms_ping",
            )
        )
        ping_by_ip_d = (
            select(
                PingRecord.target.label("ip"),
                PingRecord.is_reachable,
            )
            .where(PingRecord.batch_id.in_(latest_ping_batches_d))
            .subquery()
        )
        stmt = stmt.outerjoin(
            ping_by_ip_d,
            MaintenanceMacList.ip_address == ping_by_ip_d.c.ip,
        )
        stmt = stmt.order_by(
            case(
                (ping_by_ip_d.c.is_reachable == None, 0),   # noqa: E711
                (ping_by_ip_d.c.is_reachable == False, 1),   # noqa: E712
                else_=2,
            ),
            MaintenanceMacList.mac_address,
        )
        stmt = stmt.offset(offset).limit(limit)
        result = await session.execute(stmt)
        clients = result.scalars().all()

        client_ids = [c.id for c in clients]

        # 獲取 Client 的分類歸屬（只查本頁的 Client）
        client_categories: dict[int, list[dict]] = {}
        if cat_ids and client_ids:
            member_stmt = select(ClientCategoryMember).where(
                ClientCategoryMember.category_id.in_(cat_ids),
                ClientCategoryMember.client_id.in_(client_ids),
            )
            member_result = await session.execute(member_stmt)
            for member in member_result.scalars().all():
                cat = categories.get(member.category_id)
                if cat and member.client_id:
                    if member.client_id not in client_categories:
                        client_categories[member.client_id] = []
                    client_categories[member.client_id].append({
                        "id": cat.id,
                        "name": cat.name,
                    })

        # 從 ping_records 直接取 ping 狀態（by IP → 映射回 MAC）
        ping_status: dict[str, bool | None] = {}
        ip_addresses = [c.ip_address for c in clients if c.ip_address]
        if ip_addresses:
            latest_ping_batches_s = (
                select(LatestCollectionBatch.batch_id)
                .where(
                    LatestCollectionBatch.maintenance_id == maintenance_id,
                    LatestCollectionBatch.collection_type == "gnms_ping",
                )
            )
            ping_stmt = (
                select(PingRecord.target, PingRecord.is_reachable)
                .where(
                    PingRecord.batch_id.in_(latest_ping_batches_s),
                    PingRecord.target.in_(ip_addresses),
                )
            )
            ping_result = await session.execute(ping_stmt)
            ip_to_reachable = {
                row.target: row.is_reachable for row in ping_result
            }
            for c in clients:
                if c.ip_address and c.ip_address in ip_to_reachable:
                    ping_status[c.mac_address] = ip_to_reachable[c.ip_address]

        # 組合結果
        results = []
        for c in clients:
            cat_list = client_categories.get(c.id, [])
            category_names = ";".join([ct["name"] for ct in cat_list])
            cat_id_list = [ct["id"] for ct in cat_list]

            results.append({
                "id": c.id,
                "mac_address": c.mac_address,
                "ip_address": c.ip_address,
                "tenant_group": c.tenant_group,
                "detection_status": c.detection_status,
                "description": c.description,
                "default_assignee": c.default_assignee,
                "maintenance_id": c.maintenance_id,
                "last_ping_reachable": ping_status.get(c.mac_address),
                "category_id": cat_list[0]["id"] if cat_list else None,
                "category_name": category_names if category_names else None,
                "category_ids": cat_id_list,
            })

        return results


@router.get("/{maintenance_id}/export-csv")
async def export_csv(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
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

        # 在 SQL 層套用 filter_status
        if filter_status and filter_status != "all":
            from app.core.enums import ClientDetectionStatus as CDS
            _status_map = {s.value: s for s in CDS}
            status_enum = _status_map.get(filter_status)
            if status_enum:
                stmt = stmt.where(
                    MaintenanceMacList.detection_status == status_enum
                )
            elif filter_status == "not_checked":
                stmt = stmt.where(
                    MaintenanceMacList.detection_status.is_(None)
                )

        # 在 SQL 層套用 filter_category
        if filter_category:
            cat_stmt = select(ClientCategory).where(
                ClientCategory.maintenance_id == maintenance_id,
                ClientCategory.is_active == True,  # noqa: E712
            )
            cat_result_q = await session.execute(cat_stmt)
            all_cat_ids = [c.id for c in cat_result_q.scalars().all()]

            if filter_category == "uncategorized" and all_cat_ids:
                categorized_clients = (
                    select(ClientCategoryMember.client_id)
                    .where(ClientCategoryMember.category_id.in_(all_cat_ids))
                    .distinct()
                    .subquery()
                )
                stmt = stmt.where(
                    MaintenanceMacList.id.notin_(
                        select(categorized_clients.c.client_id)
                    )
                )
            elif filter_category.isdigit():
                target_clients = (
                    select(ClientCategoryMember.client_id)
                    .where(ClientCategoryMember.category_id == int(filter_category))
                    .subquery()
                )
                stmt = stmt.where(
                    MaintenanceMacList.id.in_(
                        select(target_clients.c.client_id)
                    )
                )

        # ping 不可達優先排序（直接讀 ping_records）
        latest_ping_batches_c = (
            select(LatestCollectionBatch.batch_id)
            .where(
                LatestCollectionBatch.maintenance_id == maintenance_id,
                LatestCollectionBatch.collection_type == "gnms_ping",
            )
        )
        ping_by_ip_c = (
            select(
                PingRecord.target.label("ip"),
                PingRecord.is_reachable,
            )
            .where(PingRecord.batch_id.in_(latest_ping_batches_c))
            .subquery()
        )
        stmt = stmt.outerjoin(
            ping_by_ip_c,
            MaintenanceMacList.ip_address == ping_by_ip_c.c.ip,
        )
        stmt = stmt.order_by(
            case(
                (ping_by_ip_c.c.is_reachable == None, 0),   # noqa: E711
                (ping_by_ip_c.c.is_reachable == False, 1),   # noqa: E712
                else_=2,
            ),
            MaintenanceMacList.mac_address,
        )
        # Add is_reachable to selected columns
        stmt = stmt.add_columns(ping_by_ip_c.c.is_reachable)
        result = await session.execute(stmt)
        rows = result.all()

        # 生成 CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "mac_address", "ip_address", "ping_reachable",
            "tenant_group", "description", "default_assignee",
        ])

        def _reach(v):
            if v is None:
                return "未檢測"
            return "可達" if v else "不可達"

        for row in rows:
            c = row[0]  # MaintenanceMacList entity
            reachable = row[1]  # is_reachable from ping join
            tg = c.tenant_group.value if c.tenant_group else "F18"
            writer.writerow([
                c.mac_address,
                c.ip_address,
                _reach(reachable),
                tg,
                c.description or "",
                c.default_assignee or "",
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
async def download_template(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
):
    """下載 Client 清單 CSV 範本。"""
    from fastapi.responses import StreamingResponse

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "mac_address", "ip_address", "tenant_group",
        "description", "default_assignee",
    ])
    # 範例資料
    writer.writerow([
        "AA:BB:CC:DD:EE:01", "192.168.1.100", "F18",
        "1號機台", "系統管理員",
    ])
    writer.writerow([
        "AA:BB:CC:DD:EE:02", "192.168.1.101", "F6",
        "2號機台", "",
    ])
    writer.writerow([
        "AA:BB:CC:DD:EE:03", "192.168.1.102", "AP",
        "", "",
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


# ── GNMS MacARP 自動匯入 ─────────────────────────────────────��───────


class GnmsMacArpClient(BaseModel):
    """GNMS MacARP API 回傳���單筆 client。"""
    device_name: str = ""
    device_ip: str = ""
    interface_name: str = ""
    user_ip: str = ""
    user_mac: str = ""
    owner: str = ""
    tenant_group: str = ""
    area: str = ""
    effective_acl_name: str = ""
    last_seen: str = ""


class GnmsMacArpDeviceSummary(BaseModel):
    """每台設���的摘要（供前端 wizard 顯示）。"""
    device_name: str
    tenant_group: str
    client_count: int


class GnmsMacArpFetchResponse(BaseModel):
    """fetch 端點的回應。"""
    batch_index: int
    total_batches: int
    devices: list[GnmsMacArpDeviceSummary]
    raw_data: dict[str, list[dict]]  # device_name → client list


class GnmsMacArpDeviceMeta(BaseModel):
    """每台設備的匯入設定。"""
    description: str | None = None
    default_assignee: str | None = None


class GnmsMacArpImportRequest(BaseModel):
    """import 端點的請求。"""
    raw_data: dict[str, list[dict]]
    device_meta: dict[str, GnmsMacArpDeviceMeta] = {}  # device_name → meta
    # fallback（未在 device_meta 中的設備）
    description: str | None = None
    default_assignee: str | None = None


@router.get("/{maintenance_id}/gnms-macarp-fetch")
async def gnms_macarp_fetch(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
    batch_index: int = Query(0, ge=0, description="第幾批 (0-based)"),
) -> GnmsMacArpFetchResponse:
    """
    從 GNMS MacARP API 取��一��設備的 client 資料。

    流程：
    1. 讀取歲修設備清���，取 hostname
    2. 按 batch_size (預設 100) 分批
    3. 呼叫 GNMS MacARP API
    4. 回傳設備摘要 + 原始���料供下一步匯入
    """
    import logging
    import httpx
    from app.core.config import settings

    logger = logging.getLogger(__name__)
    cfg = settings.gnms_macarp

    if not cfg.base_url:
        raise HTTPException(
            status_code=400,
            detail="GNMS MacARP API 尚未設定（GNMS_MACARP__BASE_URL）",
        )

    # 1. 讀取設備清單
    async with get_session_context() as session:
        stmt = select(
            MaintenanceDeviceList.new_hostname,
        ).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id,
            MaintenanceDeviceList.new_hostname.isnot(None),
            MaintenanceDeviceList.new_hostname != "",
        )
        result = await session.execute(stmt)
        all_hostnames = [r[0] for r in result.all()]

    if not all_hostnames:
        raise HTTPException(
            status_code=400,
            detail="設備清��為空，請先匯入設備",
        )

    # 2. 分批
    batch_size = cfg.batch_size or 100
    total_batches = (len(all_hostnames) + batch_size - 1) // batch_size

    if batch_index >= total_batches:
        raise HTTPException(
            status_code=400,
            detail=f"batch_index {batch_index} 超出範圍（共 {total_batches} 批）",
        )

    start = batch_index * batch_size
    batch_names = all_hostnames[start:start + batch_size]

    # 3. 呼叫 GNMS MacARP API
    url = f"{cfg.base_url.rstrip('/')}/api/v1/macarp/batch"
    params = [("name", n) for n in batch_names]
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {cfg.token}",
    }

    try:
        async with httpx.AsyncClient(timeout=cfg.timeout) as client:
            resp = await client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPStatusError as e:
        logger.error("GNMS MacARP API HTTP error: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"GNMS MacARP API 回應錯誤: {e.response.status_code}",
        )
    except Exception as e:
        logger.error("GNMS MacARP API error: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"GNMS MacARP API 連線失敗: {e}",
        )

    # 4. ��析回應
    data: dict[str, list[dict]] = body.get("data", {})
    devices: list[GnmsMacArpDeviceSummary] = []

    for device_name, clients in data.items():
        # 取第一個 client 的 tenant_group 作為該設備的���表
        tg = ""
        if clients:
            tg = clients[0].get("tenant_group", "")
        devices.append(GnmsMacArpDeviceSummary(
            device_name=device_name,
            tenant_group=tg,
            client_count=len(clients),
        ))

    return GnmsMacArpFetchResponse(
        batch_index=batch_index,
        total_batches=total_batches,
        devices=devices,
        raw_data=data,
    )


@router.post("/{maintenance_id}/gnms-macarp-import")
async def gnms_macarp_import(
    maintenance_id: str,
    body: GnmsMacArpImportRequest,
    _user: Annotated[dict[str, Any], Depends(require_write())],
) -> dict[str, Any]:
    """
    將 GNMS MacARP fetch 結果匯入 Client 清單。

    接收前端傳回的 raw_data + 用戶填入的 description / default_assignee。
    自動去重（同 maintenance_id + mac_address 不重複新增）。
    """
    import logging
    logger = logging.getLogger(__name__)

    async with get_session_context() as session:
        # 查現有 MAC 避免重複
        existing_stmt = select(MaintenanceMacList.mac_address).where(
            MaintenanceMacList.maintenance_id == maintenance_id,
        )
        result = await session.execute(existing_stmt)
        existing_macs = {r[0] for r in result.all()}

        # 預先解析所有 assignee（per-device + fallback）
        assignee_cache: dict[str, str] = {}

        async def get_assignee(name: str | None) -> str:
            key = name or ""
            if key not in assignee_cache:
                try:
                    assignee_cache[key] = await resolve_default_assignee(
                        session, name,
                    )
                except HTTPException:
                    assignee_cache[key] = "系統管理員"
            return assignee_cache[key]

        imported = 0
        skipped = 0
        errors: list[str] = []

        for device_name, clients in body.raw_data.items():
            # 取 per-device meta，沒有就用 fallback
            meta = body.device_meta.get(device_name)
            desc = meta.description if meta else body.description
            assignee_name = (
                meta.default_assignee if meta
                else body.default_assignee
            )
            assignee = await get_assignee(assignee_name)

            for client in clients:
                raw_mac = client.get("user_mac", "").strip()
                raw_ip = client.get("user_ip", "").strip()
                raw_tg = client.get(
                    "tenant_group", "",
                ).strip().upper()

                if not raw_mac or not raw_ip:
                    continue

                # 標準化 MAC
                mac = normalize_mac(raw_mac)
                if not MAC_REGEX.match(mac):
                    errors.append(
                        f"{device_name}: MAC 格式錯誤 ({raw_mac})"
                    )
                    continue

                if not IP_REGEX.match(raw_ip):
                    errors.append(
                        f"{device_name}: IP 格式錯誤 ({raw_ip})"
                    )
                    continue

                # 去重
                if mac in existing_macs:
                    skipped += 1
                    continue

                # tenant_group
                try:
                    tg = (TenantGroup(raw_tg)
                          if raw_tg else TenantGroup.F18)
                except ValueError:
                    tg = TenantGroup.F18

                session.add(MaintenanceMacList(
                    maintenance_id=maintenance_id,
                    mac_address=mac,
                    ip_address=raw_ip,
                    tenant_group=tg,
                    detection_status=ClientDetectionStatus.NOT_CHECKED,
                    description=desc,
                    default_assignee=assignee,
                ))
                existing_macs.add(mac)
                imported += 1

        await session.commit()

        # 同步���件 + 比較結果
        if imported > 0:
            await write_log(
                level="INFO",
                source="api",
                summary=f"GNMS MacARP 匯入: 新增 {imported}, 跳過 {skipped} (重複)",
                module="client_list",
                maintenance_id=maintenance_id,
            )
            await regenerate_comparisons(maintenance_id, session)

            from app.services.case_service import CaseService
            case_svc = CaseService()
            await case_svc.sync_cases(maintenance_id, session)

        logger.info(
            "GNMS MacARP import for %s: imported=%d, skipped=%d, errors=%d",
            maintenance_id, imported, skipped, len(errors),
        )

        return {
            "imported": imported,
            "skipped": skipped,
            "errors": errors,
            "total_errors": len(errors),
        }


@router.post("/{maintenance_id}/detect")
async def detect_clients(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(require_write())],
) -> dict[str, Any]:
    """
    觸發客戶端偵測。

    流程：
    1. 從 Client 清單載入所有 IP + MAC + tenant_group
    2. 按 tenant_group 分組呼叫 GNMS Ping 檢查可達性
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
