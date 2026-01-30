"""
Maintenance Client List API endpoints.

歲修 Client 清單管理 - 負責人先匯入本次歲修涉及的全部 Client（IP + MAC）。
"""
from __future__ import annotations

import csv
import io
import re
from typing import Any

from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from pydantic import BaseModel
from sqlalchemy import select, func, delete

from app.core.enums import ClientDetectionStatus, TenantGroup
from app.db.base import get_session_context
from app.db.models import (
    MaintenanceMacList, ClientCategoryMember, ClientCategory,
)


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
    category: str | None = None  # 分類名稱（若不存在會自動建立）


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
            "ip_address": entry.ip_address,
            "tenant_group": entry.tenant_group,
            "detection_status": entry.detection_status,
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
    從 CSV 批量導入 Client。

    CSV 格式: mac_address,ip_address,tenant_group,description,category
    - mac_address: 必填
    - ip_address: 必填
    - tenant_group: 選填（預設 F18，有效值: F18/F6/AP/F14/F12）
    - description: 選填
    - category: 選填（若不存在會自動建立）
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
        categories_created = set()

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
        for c in clients:
            cat_info = mac_categories.get(c.mac_address)
            if c.detection_status:
                status = c.detection_status.value
            else:
                status = "not_checked"

            # 過濾條件 - 偵測狀態
            if filter_status and filter_status != "all":
                if status != filter_status:
                    continue

            # 過濾條件 - 分類
            if filter_category == "uncategorized" and cat_info:
                continue
            if filter_category and filter_category.isdigit():
                cat_id = int(filter_category)
                if not cat_info or cat_info["id"] != cat_id:
                    continue

            results.append({
                "id": c.id,
                "mac_address": c.mac_address,
                "ip_address": c.ip_address,
                "tenant_group": c.tenant_group,
                "detection_status": c.detection_status,
                "description": c.description,
                "maintenance_id": c.maintenance_id,
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
    """匯出 Client 清單為 CSV（支援搜尋過濾）。"""
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

        # 生成 CSV
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "mac_address", "ip_address", "tenant_group",
            "detection_status", "description"
        ])

        for c in clients:
            tg = c.tenant_group.value if c.tenant_group else "F18"
            ds = c.detection_status.value if c.detection_status else "not_checked"
            writer.writerow([
                c.mac_address,
                c.ip_address,
                tg,
                ds,
                c.description or "",
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
async def download_template():
    """下載 Client 清單 CSV 範本。"""
    from fastapi.responses import StreamingResponse

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "mac_address", "ip_address", "tenant_group", "description", "category"
    ])
    # 範例資料
    writer.writerow([
        "AA:BB:CC:DD:EE:01", "192.168.1.100", "F18", "測試機台1", "生產機台"
    ])
    writer.writerow([
        "AA:BB:CC:DD:EE:02", "192.168.1.101", "F6", "測試機台2", ""
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

    return result
