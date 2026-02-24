"""
Maintenance Device List API endpoints.

歲修設備對應清單的 API 端點。
管理歲修涉及的所有設備及其新舊對應關係。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, model_validator
import csv
import io

from app.db.base import get_async_session
from app.db.models import (
    CollectionError,
    LatestCollectionBatch,
    MaintenanceDeviceList,
    DEVICE_VENDOR_OPTIONS,
)
from app.core.enums import TenantGroup
from app.api.endpoints.auth import get_current_user, require_write
from app.services.system_log import write_log
from typing import Annotated, Any
import ipaddress


router = APIRouter(
    prefix="/maintenance-devices",
    tags=["maintenance-devices"],
)


class DeviceCreate(BaseModel):
    """創建設備對應的請求模型。"""
    # 舊設備資訊（選填，但三者必須同時有或同時無）
    old_hostname: str | None = None
    old_ip_address: str | None = None
    old_vendor: str | None = None
    # 新設備資訊（選填，但三者必須同時有或同時無）
    new_hostname: str | None = None
    new_ip_address: str | None = None
    new_vendor: str | None = None
    # GNMS Ping tenant group
    tenant_group: TenantGroup = TenantGroup.F18
    # 備註（選填）
    description: str | None = None

    @model_validator(mode="after")
    def check_at_least_one_side(self) -> DeviceCreate:
        old_fields = [self.old_hostname, self.old_ip_address, self.old_vendor]
        new_fields = [self.new_hostname, self.new_ip_address, self.new_vendor]
        old_filled = [f for f in old_fields if f and f.strip()]
        new_filled = [f for f in new_fields if f and f.strip()]

        if not old_filled and not new_filled:
            raise ValueError("至少需要填寫舊設備或新設備的完整資訊")

        if 0 < len(old_filled) < 3:
            raise ValueError("舊設備資訊不完整：hostname、IP、廠商必須同時填寫或同時留空")

        if 0 < len(new_filled) < 3:
            raise ValueError("新設備資訊不完整：hostname、IP、廠商必須同時填寫或同時留空")

        return self


class DeviceUpdate(BaseModel):
    """更新設備對應的請求模型。"""
    old_hostname: str | None = None
    old_ip_address: str | None = None
    old_vendor: str | None = None
    new_hostname: str | None = None
    new_ip_address: str | None = None
    new_vendor: str | None = None
    tenant_group: TenantGroup | None = None
    description: str | None = None


def serialize_device(d: MaintenanceDeviceList) -> dict:
    """序列化設備對應為 dict。"""
    return {
        "id": d.id,
        "old_hostname": d.old_hostname,
        "old_ip_address": d.old_ip_address,
        "old_vendor": d.old_vendor,
        "new_hostname": d.new_hostname,
        "new_ip_address": d.new_ip_address,
        "new_vendor": d.new_vendor,
        "is_replaced": bool(d.is_replaced) if d.is_replaced is not None else False,
        "use_same_port": bool(d.use_same_port) if d.use_same_port is not None else None,
        "tenant_group": d.tenant_group.value if d.tenant_group else TenantGroup.F18.value,
        "description": d.description,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }


async def validate_device_mapping(
    session: AsyncSession,
    maintenance_id: str,
    old_hostname: str | None,
    old_ip_address: str | None,
    new_hostname: str | None,
    new_ip_address: str | None,
    existing_device_id: int | None = None,
) -> list[str]:
    """
    驗證設備對應的所有約束條件。

    Args:
        session: 資料庫 session
        maintenance_id: 歲修 ID
        old_hostname: 舊設備 hostname（可為 None）
        old_ip_address: 舊設備 IP（可為 None）
        new_hostname: 新設備 hostname（可為 None）
        new_ip_address: 新設備 IP（可為 None）
        existing_device_id: 如果是更新操作，提供現有設備的 ID（用於排除自己）

    Returns:
        錯誤訊息列表（空列表表示驗證通過）
    """
    errors = []

    # 1. IP 格式驗證（只驗證非 None 的）
    if old_ip_address:
        try:
            ipaddress.ip_address(old_ip_address)
        except ValueError:
            errors.append(f"舊設備 IP 格式錯誤: {old_ip_address}")

    if new_ip_address:
        try:
            ipaddress.ip_address(new_ip_address)
        except ValueError:
            errors.append(f"新設備 IP 格式錯誤: {new_ip_address}")

    # 2. old_hostname 唯一性檢查
    if old_hostname:
        stmt_old_hostname = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id,
            MaintenanceDeviceList.old_hostname == old_hostname,
        )
        if existing_device_id is not None:
            stmt_old_hostname = stmt_old_hostname.where(
                MaintenanceDeviceList.id != existing_device_id
            )

        result = await session.execute(stmt_old_hostname)
        conflict_old = result.scalar_one_or_none()
        if conflict_old:
            errors.append(f"舊設備 {old_hostname} 已存在")

    # 3. new_hostname 唯一性檢查
    if new_hostname:
        stmt_new_hostname = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id,
            MaintenanceDeviceList.new_hostname == new_hostname,
        )
        if existing_device_id is not None:
            stmt_new_hostname = stmt_new_hostname.where(
                MaintenanceDeviceList.id != existing_device_id
            )

        result2 = await session.execute(stmt_new_hostname)
        conflict_new = result2.scalar_one_or_none()
        if conflict_new:
            errors.append(
                f"新設備 {new_hostname} 已存在 "
                f"(在 {conflict_new.old_hostname or '-'} → {conflict_new.new_hostname or '-'} 的對應中)"
            )

    # 4. OLD IP 在所有 OLD 設備中唯一
    if old_ip_address:
        stmt_old_ip = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id,
            MaintenanceDeviceList.old_ip_address == old_ip_address,
        )
        if existing_device_id is not None:
            stmt_old_ip = stmt_old_ip.where(
                MaintenanceDeviceList.id != existing_device_id
            )

        result_old_ip = await session.execute(stmt_old_ip)
        dup_old_ip = result_old_ip.scalar_one_or_none()
        if dup_old_ip:
            errors.append(
                f"舊設備 IP {old_ip_address} 已被其他舊設備使用 "
                f"({dup_old_ip.old_hostname})"
            )

    # 5. NEW IP 在所有 NEW 設備中唯一
    if new_ip_address:
        stmt_new_ip = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id,
            MaintenanceDeviceList.new_ip_address == new_ip_address,
        )
        if existing_device_id is not None:
            stmt_new_ip = stmt_new_ip.where(
                MaintenanceDeviceList.id != existing_device_id
            )

        result_new_ip = await session.execute(stmt_new_ip)
        dup_new_ip = result_new_ip.scalar_one_or_none()
        if dup_new_ip:
            errors.append(
                f"新設備 IP {new_ip_address} 已被其他新設備使用 "
                f"({dup_new_ip.new_hostname})"
            )

    return errors


@router.get("/vendor-options")
async def get_vendor_options(
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    """取得廠商選項列表。"""
    return {
        "success": True,
        "options": DEVICE_VENDOR_OPTIONS,
    }


@router.get("/tenant-group-options")
async def get_tenant_group_options(
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    """取得 Tenant Group 選項列表。"""
    return {
        "success": True,
        "options": [tg.value for tg in TenantGroup],
    }


@router.get("/{maintenance_id}")
async def list_devices(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
    search: str | None = Query(None, description="搜尋 hostname 或 IP（支援多關鍵字，空格分隔）"),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    列出指定歲修的所有設備對應。

    搜尋邏輯：支援多關鍵字搜尋，空格分隔，所有關鍵字都必須匹配
    例如："SW 01 CORE" 會匹配 "SW-OLD-001-CORE"
    """
    from sqlalchemy import or_, and_

    stmt = (
        select(MaintenanceDeviceList)
        .where(MaintenanceDeviceList.maintenance_id == maintenance_id)
    )

    # 多關鍵字搜尋（空格分隔，所有關鍵字都必須在同一個欄位中匹配）
    if search:
        keywords = search.strip().split()

        # 對每個欄位，檢查是否所有關鍵字都在該欄位中
        field_conditions = []
        for field in [
            MaintenanceDeviceList.old_hostname,
            MaintenanceDeviceList.old_ip_address,
            MaintenanceDeviceList.new_hostname,
            MaintenanceDeviceList.new_ip_address,
            MaintenanceDeviceList.description,
        ]:
            # 所有關鍵字都必須在這個欄位中
            field_match = and_(*[field.ilike(f"%{kw}%") for kw in keywords])
            field_conditions.append(field_match)

        # 只要有任何一個欄位滿足所有關鍵字，就匹配
        stmt = stmt.where(or_(*field_conditions))

    stmt = stmt.order_by(
        func.coalesce(MaintenanceDeviceList.old_hostname, MaintenanceDeviceList.new_hostname)
    )

    result = await session.execute(stmt)
    devices = result.scalars().all()

    return {
        "success": True,
        "maintenance_id": maintenance_id,
        "count": len(devices),
        "devices": [serialize_device(d) for d in devices],
    }


@router.get("/{maintenance_id}/stats")
async def get_stats(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """獲取設備對應統計（可達性從 PingRecord 取得，按舊/新設備分類）。"""
    from app.repositories.typed_records import PingRecordRepo

    # 取得所有設備對應
    device_stmt = (
        select(MaintenanceDeviceList)
        .where(MaintenanceDeviceList.maintenance_id == maintenance_id)
    )
    result = await session.execute(device_stmt)
    devices = result.scalars().all()

    # 建立 hostname → role 映射（old / new）
    old_hostnames: set[str] = set()
    new_hostnames: set[str] = set()
    for d in devices:
        if d.old_hostname:
            old_hostnames.add(d.old_hostname)
        if d.new_hostname:
            new_hostnames.add(d.new_hostname)

    old_count = len(old_hostnames)
    new_count = len(new_hostnames)
    total = old_count + new_count

    # 從 PingRecord 取得可達性統計
    repo = PingRecordRepo(session)
    records = await repo.get_latest_per_device(maintenance_id)

    # 每台設備取最佳結果（與 PingIndicator 邏輯一致）
    per_device: dict[str, bool] = {}
    for r in records:
        existing = per_device.get(r.switch_hostname)
        if existing is None or (r.is_reachable and not existing):
            per_device[r.switch_hostname] = r.is_reachable

    # 按舊/新設備分類可達性
    old_reachable = sum(1 for h in old_hostnames if per_device.get(h) is True)
    old_unreachable = sum(1 for h in old_hostnames if per_device.get(h) is False)
    old_unchecked = old_count - old_reachable - old_unreachable

    new_reachable = sum(1 for h in new_hostnames if per_device.get(h) is True)
    new_unreachable = sum(1 for h in new_hostnames if per_device.get(h) is False)
    new_unchecked = new_count - new_reachable - new_unreachable

    reachable = old_reachable + new_reachable
    unreachable = old_unreachable + new_unreachable
    unchecked = old_unchecked + new_unchecked

    return {
        "success": True,
        "total": total,
        "old_count": old_count,
        "new_count": new_count,
        "reachable": reachable,
        "unreachable": unreachable,
        "unchecked": unchecked,
        "reachable_rate": (
            round(reachable / total * 100, 1) if total > 0 else 0
        ),
        "old_reachable": old_reachable,
        "old_unreachable": old_unreachable,
        "old_unchecked": old_unchecked,
        "new_reachable": new_reachable,
        "new_unreachable": new_unreachable,
        "new_unchecked": new_unchecked,
    }


@router.post("/{maintenance_id}")
async def create_device(
    maintenance_id: str,
    data: DeviceCreate,
    _: Annotated[dict[str, Any], Depends(require_write())],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """新增設備對應。需要 device:write 權限。"""
    old_hostname = data.old_hostname.strip() if data.old_hostname else None
    old_ip_address = data.old_ip_address.strip() if data.old_ip_address else None
    new_hostname = data.new_hostname.strip() if data.new_hostname else None
    new_ip_address = data.new_ip_address.strip() if data.new_ip_address else None
    old_vendor = data.old_vendor.strip() if data.old_vendor else None
    new_vendor = data.new_vendor.strip() if data.new_vendor else None

    # 驗證 vendor（只驗證非 None 的）
    if old_vendor and old_vendor not in DEVICE_VENDOR_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"舊設備廠商必須是 {', '.join(DEVICE_VENDOR_OPTIONS)} 其中之一",
        )
    if new_vendor and new_vendor not in DEVICE_VENDOR_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"新設備廠商必須是 {', '.join(DEVICE_VENDOR_OPTIONS)} 其中之一",
        )

    # 使用統一的驗證函數
    validation_errors = await validate_device_mapping(
        session=session,
        maintenance_id=maintenance_id,
        old_hostname=old_hostname,
        old_ip_address=old_ip_address,
        new_hostname=new_hostname,
        new_ip_address=new_ip_address,
    )

    if validation_errors:
        raise HTTPException(
            status_code=400,
            detail="; ".join(validation_errors),
        )

    device = MaintenanceDeviceList(
        maintenance_id=maintenance_id,
        old_hostname=old_hostname,
        old_ip_address=old_ip_address,
        old_vendor=old_vendor,
        new_hostname=new_hostname,
        new_ip_address=new_ip_address,
        new_vendor=new_vendor,
        tenant_group=data.tenant_group,
        description=data.description.strip() if data.description else None,
    )
    session.add(device)
    await session.commit()
    await session.refresh(device)

    label = f"{old_hostname or '-'} → {new_hostname or '-'}"
    await write_log(
        level="INFO",
        source="api",
        summary=f"新增設備對應: {label}",
        module="device",
        maintenance_id=maintenance_id,
    )

    return {
        "success": True,
        "message": "設備對應已新增",
        "device": serialize_device(device),
    }


@router.put("/{maintenance_id}/{device_id}")
async def update_device(
    maintenance_id: str,
    device_id: int,
    data: DeviceUpdate,
    _: Annotated[dict[str, Any], Depends(require_write())],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """更新設備對應。需要 device:write 權限。"""
    stmt = select(MaintenanceDeviceList).where(
        MaintenanceDeviceList.id == device_id,
        MaintenanceDeviceList.maintenance_id == maintenance_id,
    )
    result = await session.execute(stmt)
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="找不到指定的設備對應")

    # 計算更新後的值（使用新值或保留舊值；空字串 → None）
    new_old_hostname = (
        data.old_hostname.strip() or None
        if data.old_hostname is not None
        else device.old_hostname
    )
    new_old_ip_address = (
        data.old_ip_address.strip() or None
        if data.old_ip_address is not None
        else device.old_ip_address
    )
    new_new_hostname = (
        data.new_hostname.strip() or None
        if data.new_hostname is not None
        else device.new_hostname
    )
    new_new_ip_address = (
        data.new_ip_address.strip() or None
        if data.new_ip_address is not None
        else device.new_ip_address
    )

    # 驗證 vendor（如果有提供的話）
    if data.old_vendor is not None:
        vendor = data.old_vendor.strip()
        if vendor and vendor not in DEVICE_VENDOR_OPTIONS:
            raise HTTPException(
                status_code=400,
                detail=f"廠商必須是 {', '.join(DEVICE_VENDOR_OPTIONS)} 其中之一",
            )
    if data.new_vendor is not None:
        vendor = data.new_vendor.strip()
        if vendor and vendor not in DEVICE_VENDOR_OPTIONS:
            raise HTTPException(
                status_code=400,
                detail=f"廠商必須是 {', '.join(DEVICE_VENDOR_OPTIONS)} 其中之一",
            )

    # 使用統一的驗證函數（只在關鍵欄位有變更時才驗證）
    needs_validation = (
        data.old_hostname is not None
        or data.old_ip_address is not None
        or data.new_hostname is not None
        or data.new_ip_address is not None
    )

    if needs_validation:
        validation_errors = await validate_device_mapping(
            session=session,
            maintenance_id=maintenance_id,
            old_hostname=new_old_hostname,
            old_ip_address=new_old_ip_address,
            new_hostname=new_new_hostname,
            new_ip_address=new_new_ip_address,
            existing_device_id=device_id,
        )

        if validation_errors:
            raise HTTPException(
                status_code=400,
                detail="; ".join(validation_errors),
            )

    # 更新欄位
    if data.old_hostname is not None:
        device.old_hostname = new_old_hostname
    if data.old_ip_address is not None:
        device.old_ip_address = new_old_ip_address
    if data.old_vendor is not None:
        device.old_vendor = data.old_vendor.strip() or None
    if data.new_hostname is not None:
        device.new_hostname = new_new_hostname
    if data.new_ip_address is not None:
        device.new_ip_address = new_new_ip_address
    if data.new_vendor is not None:
        device.new_vendor = data.new_vendor.strip() or None
    if data.tenant_group is not None:
        device.tenant_group = data.tenant_group
    if data.description is not None:
        device.description = (
            data.description.strip() if data.description else None
        )

    await session.commit()
    await session.refresh(device)

    label = f"{device.old_hostname or '-'} → {device.new_hostname or '-'}"
    await write_log(
        level="INFO",
        source="api",
        summary=f"更新設備對應: {label}",
        module="device",
        maintenance_id=maintenance_id,
    )

    return {
        "success": True,
        "message": "設備對應已更新",
        "device": serialize_device(device),
    }


@router.delete("/{maintenance_id}/{device_id}")
async def delete_device(
    maintenance_id: str,
    device_id: int,
    _: Annotated[dict[str, Any], Depends(require_write())],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """刪除設備對應。需要 device:write 權限。"""
    stmt = select(MaintenanceDeviceList).where(
        MaintenanceDeviceList.id == device_id,
        MaintenanceDeviceList.maintenance_id == maintenance_id,
    )
    result = await session.execute(stmt)
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="找不到指定的設備對應")

    old_hostname = device.old_hostname or "-"
    new_hostname = device.new_hostname or "-"

    # 清理該設備的採集快取（LatestCollectionBatch、CollectionError）
    hostnames_to_clean = [
        h for h in (device.new_hostname, device.old_hostname) if h
    ]
    if hostnames_to_clean:
        await session.execute(
            delete(LatestCollectionBatch).where(
                LatestCollectionBatch.maintenance_id == maintenance_id,
                LatestCollectionBatch.switch_hostname.in_(hostnames_to_clean),
            )
        )
        await session.execute(
            delete(CollectionError).where(
                CollectionError.maintenance_id == maintenance_id,
                CollectionError.switch_hostname.in_(hostnames_to_clean),
            )
        )

    await session.delete(device)
    await session.commit()

    await write_log(
        level="WARNING",
        source="api",
        summary=f"刪除設備對應: {old_hostname} → {new_hostname}",
        module="device",
        maintenance_id=maintenance_id,
    )

    return {
        "success": True,
        "message": "設備對應已刪除",
    }


@router.post("/{maintenance_id}/import-csv")
async def import_csv(
    maintenance_id: str,
    _: Annotated[dict[str, Any], Depends(require_write())],
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    從 CSV 匯入設備對應。

    CSV 格式：
    old_hostname,old_ip_address,old_vendor,new_hostname,new_ip_address,new_vendor,tenant_group,description

    - 舊設備三欄位（hostname, IP, vendor）必須同時填寫或同時留空
    - 新設備三欄位（hostname, IP, vendor）必須同時填寫或同時留空
    - 至少需要填寫一側（舊設備或新設備）
    - vendor: HPE / Cisco-IOS / Cisco-NXOS
    - tenant_group: F18/F6/AP/F14/F12（預設 F18）
    - description: 選填

    **重要**：使用兩階段驗證（全部驗證通過才提交）
    - 階段 1：驗證所有行並收集錯誤
    - 階段 2：只有完全沒有錯誤時才一次性提交
    - 任何一筆錯誤，整份 CSV 匯入失敗
    """
    if not file.filename or not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="請上傳 CSV 文件")

    content = await file.read()

    # 嘗試解碼
    try:
        text = content.decode('utf-8-sig')
    except UnicodeDecodeError:
        try:
            text = content.decode('gbk')
        except UnicodeDecodeError:
            text = content.decode('utf-8', errors='ignore')

    reader = csv.DictReader(io.StringIO(text))

    # ===== 階段 1: 驗證所有行並收集錯誤 =====
    errors = []
    rows_to_process = []  # 存儲待處理的行數據
    used_old_hostnames_in_csv: set[str] = set()  # CSV 內部 OLD hostname 唯一性
    used_new_hostnames_in_csv: set[str] = set()  # CSV 內部 NEW hostname 唯一性
    used_old_ips_in_csv: set[str] = set()  # CSV 內部 OLD IP 唯一性
    used_new_ips_in_csv: set[str] = set()  # CSV 內部 NEW IP 唯一性

    for row_num, row in enumerate(reader, start=2):
        old_hostname = row.get('old_hostname', '').strip() or None
        old_ip = row.get('old_ip_address', '').strip() or None
        old_vendor = row.get('old_vendor', '').strip() or None
        new_hostname = row.get('new_hostname', '').strip() or None
        new_ip = row.get('new_ip_address', '').strip() or None
        new_vendor = row.get('new_vendor', '').strip() or None

        # 1. 驗證各側完整性（all-or-nothing）
        old_fields = [old_hostname, old_ip, old_vendor]
        new_fields = [new_hostname, new_ip, new_vendor]
        old_count = sum(1 for f in old_fields if f)
        new_count = sum(1 for f in new_fields if f)

        if old_count == 0 and new_count == 0:
            errors.append(f"第 {row_num} 行：至少需要填寫舊設備或新設備的完整資訊")
            continue
        if 0 < old_count < 3:
            errors.append(
                f"第 {row_num} 行：舊設備資訊不完整（hostname、IP、廠商必須同時填寫或同時留空）"
            )
            continue
        if 0 < new_count < 3:
            errors.append(
                f"第 {row_num} 行：新設備資訊不完整（hostname、IP、廠商必須同時填寫或同時留空）"
            )
            continue

        # 2. 驗證 vendor
        if old_vendor and old_vendor not in DEVICE_VENDOR_OPTIONS:
            errors.append(
                f"第 {row_num} 行：old_vendor 必須是 "
                f"{', '.join(DEVICE_VENDOR_OPTIONS)} 其中之一"
            )
            continue
        if new_vendor and new_vendor not in DEVICE_VENDOR_OPTIONS:
            errors.append(
                f"第 {row_num} 行：new_vendor 必須是 "
                f"{', '.join(DEVICE_VENDOR_OPTIONS)} 其中之一"
            )
            continue

        # 3. 檢查 CSV 內部重複（hostname）
        if old_hostname and old_hostname in used_old_hostnames_in_csv:
            errors.append(
                f"第 {row_num} 行：舊設備 {old_hostname} 在此 CSV 中重複"
            )
            continue
        if new_hostname and new_hostname in used_new_hostnames_in_csv:
            errors.append(
                f"第 {row_num} 行：新設備 {new_hostname} 在此 CSV 中重複"
            )
            continue

        # 4. 檢查 CSV 內部 IP 重複
        if old_ip and old_ip in used_old_ips_in_csv:
            errors.append(
                f"第 {row_num} 行：舊設備 IP {old_ip} 在此 CSV 中重複"
            )
            continue
        if new_ip and new_ip in used_new_ips_in_csv:
            errors.append(
                f"第 {row_num} 行：新設備 IP {new_ip} 在此 CSV 中重複"
            )
            continue

        # 5. 檢查是否為更新（先用 old_hostname 匹配，再用 new_hostname 匹配無舊設備的）
        existing = None
        if old_hostname:
            stmt = select(MaintenanceDeviceList).where(
                MaintenanceDeviceList.maintenance_id == maintenance_id,
                MaintenanceDeviceList.old_hostname == old_hostname,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

        if not existing and new_hostname:
            stmt = select(MaintenanceDeviceList).where(
                MaintenanceDeviceList.maintenance_id == maintenance_id,
                MaintenanceDeviceList.new_hostname == new_hostname,
                MaintenanceDeviceList.old_hostname == None,  # noqa: E711
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

        # 6. 檢查是否與現有記錄完全相同（相同則跳過）
        if existing:
            is_identical = (
                existing.old_hostname == old_hostname
                and existing.old_ip_address == old_ip
                and existing.old_vendor == old_vendor
                and existing.new_hostname == new_hostname
                and existing.new_ip_address == new_ip
                and existing.new_vendor == new_vendor
            )
            if is_identical:
                # 完全相同，跳過不處理
                if old_hostname:
                    used_old_hostnames_in_csv.add(old_hostname)
                if new_hostname:
                    used_new_hostnames_in_csv.add(new_hostname)
                if old_ip:
                    used_old_ips_in_csv.add(old_ip)
                if new_ip:
                    used_new_ips_in_csv.add(new_ip)
                continue

        # 7. 使用統一的驗證函數（檢查所有約束）
        validation_errors = await validate_device_mapping(
            session=session,
            maintenance_id=maintenance_id,
            old_hostname=old_hostname,
            old_ip_address=old_ip,
            new_hostname=new_hostname,
            new_ip_address=new_ip,
            existing_device_id=existing.id if existing else None,
        )

        if validation_errors:
            for err in validation_errors:
                errors.append(f"第 {row_num} 行：{err}")
            continue

        # 8. 所有驗證通過，加入待處理列表
        # 解析 tenant_group
        tenant_group_str = row.get('tenant_group', 'F18').strip().upper()
        try:
            tenant_group = TenantGroup(tenant_group_str) if tenant_group_str else TenantGroup.F18
        except ValueError:
            tenant_group = TenantGroup.F18

        rows_to_process.append({
            'row_num': row_num,
            'old_hostname': old_hostname,
            'old_ip': old_ip,
            'old_vendor': old_vendor,
            'new_hostname': new_hostname,
            'new_ip': new_ip,
            'new_vendor': new_vendor,
            'tenant_group': tenant_group,
            'description': row.get('description', '').strip() or None,
            'existing': existing,
        })

        # 追蹤已使用的值
        if old_hostname:
            used_old_hostnames_in_csv.add(old_hostname)
        if new_hostname:
            used_new_hostnames_in_csv.add(new_hostname)
        if old_ip:
            used_old_ips_in_csv.add(old_ip)
        if new_ip:
            used_new_ips_in_csv.add(new_ip)

    # ===== 如果有任何錯誤，整份失敗 =====
    if errors:
        return {
            "success": False,
            "message": "CSV 匯入失敗：發現錯誤",
            "imported": 0,
            "updated": 0,
            "total_errors": len(errors),
            "errors": errors,
        }

    # ===== 階段 2: 所有驗證通過，執行導入 =====
    imported = 0
    updated = 0

    for item in rows_to_process:
        if item['existing']:
            # 更新現有記錄
            existing = item['existing']
            existing.old_hostname = item['old_hostname']  # type: ignore[assignment]
            existing.old_ip_address = item['old_ip']  # type: ignore[assignment]
            existing.old_vendor = item['old_vendor']  # type: ignore[assignment]
            existing.new_hostname = item['new_hostname']  # type: ignore[assignment]
            existing.new_ip_address = item['new_ip']  # type: ignore[assignment]
            existing.new_vendor = item['new_vendor']  # type: ignore[assignment]
            existing.tenant_group = item['tenant_group']  # type: ignore[assignment]
            existing.description = item['description']  # type: ignore[assignment]
            updated += 1
        else:
            # 新增記錄
            device = MaintenanceDeviceList(
                maintenance_id=maintenance_id,
                old_hostname=item['old_hostname'],
                old_ip_address=item['old_ip'],
                old_vendor=item['old_vendor'],
                new_hostname=item['new_hostname'],
                new_ip_address=item['new_ip'],
                new_vendor=item['new_vendor'],
                tenant_group=item['tenant_group'],
                description=item['description'],
            )
            session.add(device)
            imported += 1

    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        return {
            "success": False,
            "message": "CSV 匯入失敗：資料庫約束衝突（可能有重複的 hostname 或 IP）",
            "imported": 0,
            "updated": 0,
            "total_errors": 1,
            "errors": [f"資料庫寫入失敗: {exc.orig}"],
        }

    if imported + updated > 0:
        await write_log(
            level="INFO",
            source="api",
            summary=f"CSV 匯入設備: 新增 {imported} 筆, 更新 {updated} 筆",
            module="device",
            maintenance_id=maintenance_id,
        )

    return {
        "success": True,
        "message": "CSV 匯入成功",
        "imported": imported,
        "updated": updated,
        "total_errors": 0,
        "errors": [],
    }


@router.delete("/{maintenance_id}")
async def clear_all(
    maintenance_id: str,
    _: Annotated[dict[str, Any], Depends(require_write())],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """清除該歲修的所有設備對應。需要 device:write 權限。"""
    # 先清理所有關聯的採集快取
    await session.execute(
        delete(LatestCollectionBatch).where(
            LatestCollectionBatch.maintenance_id == maintenance_id,
        )
    )
    await session.execute(
        delete(CollectionError).where(
            CollectionError.maintenance_id == maintenance_id,
        )
    )

    stmt = delete(MaintenanceDeviceList).where(
        MaintenanceDeviceList.maintenance_id == maintenance_id
    )
    result = await session.execute(stmt)
    await session.commit()

    await write_log(
        level="WARNING",
        source="api",
        summary=f"清空設備對應: 共 {result.rowcount} 筆",
        module="device",
        maintenance_id=maintenance_id,
    )

    return {
        "success": True,
        "message": f"已刪除 {result.rowcount} 筆設備對應",
        "deleted_count": result.rowcount,
    }


@router.post("/{maintenance_id}/batch-delete")
async def batch_delete_devices(
    maintenance_id: str,
    _: Annotated[dict[str, Any], Depends(require_write())],
    device_ids: list[int] = Body(..., embed=True),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    批量刪除設備對應。

    Args:
        maintenance_id: 歲修 ID
        device_ids: 要刪除的設備 ID 列表

    Returns:
        刪除結果
    """
    if not device_ids:
        return {
            "success": True,
            "deleted_count": 0,
            "message": "沒有選中任何設備",
        }

    # 先查出要刪除的設備 hostname，用於清理採集快取
    hostname_stmt = select(
        MaintenanceDeviceList.new_hostname,
        MaintenanceDeviceList.old_hostname,
    ).where(
        MaintenanceDeviceList.maintenance_id == maintenance_id,
        MaintenanceDeviceList.id.in_(device_ids),
    )
    hostname_rows = (await session.execute(hostname_stmt)).all()
    hostnames_to_clean = list({
        h for row in hostname_rows
        for h in (row.new_hostname, row.old_hostname) if h
    })

    if hostnames_to_clean:
        await session.execute(
            delete(LatestCollectionBatch).where(
                LatestCollectionBatch.maintenance_id == maintenance_id,
                LatestCollectionBatch.switch_hostname.in_(hostnames_to_clean),
            )
        )
        await session.execute(
            delete(CollectionError).where(
                CollectionError.maintenance_id == maintenance_id,
                CollectionError.switch_hostname.in_(hostnames_to_clean),
            )
        )

    stmt = delete(MaintenanceDeviceList).where(
        MaintenanceDeviceList.maintenance_id == maintenance_id,
        MaintenanceDeviceList.id.in_(device_ids),
    )
    result = await session.execute(stmt)
    await session.commit()

    if result.rowcount > 0:
        await write_log(
            level="WARNING",
            source="api",
            summary=f"批量刪除設備對應: {result.rowcount} 筆",
            module="device",
            maintenance_id=maintenance_id,
        )

    return {
        "success": True,
        "deleted_count": result.rowcount,
        "message": f"已刪除 {result.rowcount} 筆設備對應",
    }


@router.get("/{maintenance_id}/export-csv")
async def export_devices_csv(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
    search: str | None = Query(None, description="搜尋過濾"),
    session: AsyncSession = Depends(get_async_session),
) -> StreamingResponse:
    """匯出設備對應為 CSV 文件。"""
    # 使用與 list_devices 相同的查詢邏輯
    stmt = (
        select(MaintenanceDeviceList)
        .where(MaintenanceDeviceList.maintenance_id == maintenance_id)
    )

    # 多關鍵字搜尋（所有關鍵字都必須在同一個欄位中匹配）
    if search:
        from sqlalchemy import or_, and_
        keywords = search.strip().split()

        field_conditions = []
        for field in [
            MaintenanceDeviceList.old_hostname,
            MaintenanceDeviceList.old_ip_address,
            MaintenanceDeviceList.new_hostname,
            MaintenanceDeviceList.new_ip_address,
            MaintenanceDeviceList.description,
        ]:
            field_match = and_(*[field.ilike(f"%{kw}%") for kw in keywords])
            field_conditions.append(field_match)

        stmt = stmt.where(or_(*field_conditions))

    stmt = stmt.order_by(
        func.coalesce(MaintenanceDeviceList.old_hostname, MaintenanceDeviceList.new_hostname)
    )

    result = await session.execute(stmt)
    devices = result.scalars().all()

    # 生成 CSV
    output = io.StringIO()
    writer = csv.writer(output)

    # 寫入標題行
    writer.writerow([
        "old_hostname",
        "old_ip_address",
        "old_vendor",
        "new_hostname",
        "new_ip_address",
        "new_vendor",
        "tenant_group",
        "description",
    ])

    # 寫入數據行
    for d in devices:
        writer.writerow([
            d.old_hostname or "",
            d.old_ip_address or "",
            d.old_vendor or "",
            d.new_hostname or "",
            d.new_ip_address or "",
            d.new_vendor or "",
            d.tenant_group.value if d.tenant_group else TenantGroup.F18.value,
            d.description or "",
        ])

    output.seek(0)
    # 添加 BOM 以便 Excel 正確識別 UTF-8
    content = "\ufeff" + output.getvalue()

    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{maintenance_id}_devices.csv"'
        },
    )


@router.get("/{maintenance_id}/reachability-status")
async def reachability_status(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    取得各設備最新 Ping 可達性狀態（從 PingRecord 讀取）。

    回傳格式：{ hostname: { is_reachable, last_check_at } }
    """
    from app.repositories.typed_records import PingRecordRepo

    repo = PingRecordRepo(session)
    records = await repo.get_latest_per_device(maintenance_id)

    # 每台設備取最佳結果（與 PingIndicator 邏輯一致）
    status: dict[str, dict] = {}
    for r in records:
        hostname = r.switch_hostname
        existing = status.get(hostname)
        if existing is None or (r.is_reachable and not existing["is_reachable"]):
            status[hostname] = {
                "is_reachable": r.is_reachable,
                "last_check_at": r.collected_at.isoformat() if r.collected_at else None,
            }

    return {
        "success": True,
        "maintenance_id": maintenance_id,
        "devices": status,
    }
