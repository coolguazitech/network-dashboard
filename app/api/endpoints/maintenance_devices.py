"""
Maintenance Device List API endpoints.

歲修設備對應清單的 API 端點。
管理歲修涉及的所有設備及其新舊對應關係。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import csv
import io

from app.db.base import get_async_session
from app.db.models import MaintenanceDeviceList, DEVICE_VENDOR_OPTIONS
from app.core.enums import TenantGroup
from app.api.endpoints.auth import require_write
from typing import Annotated, Any
import ipaddress


router = APIRouter(
    prefix="/maintenance-devices",
    tags=["maintenance-devices"],
)


class DeviceCreate(BaseModel):
    """創建設備對應的請求模型。"""
    # 舊設備資訊（必填）
    old_hostname: str
    old_ip_address: str
    old_vendor: str  # HPE, Cisco-IOS, Cisco-NXOS
    # 新設備資訊（必填）
    new_hostname: str
    new_ip_address: str
    new_vendor: str  # HPE, Cisco-IOS, Cisco-NXOS
    # 對應設定
    use_same_port: bool = True
    # GNMS Ping tenant group
    tenant_group: TenantGroup = TenantGroup.F18
    # 備註（選填）
    description: str | None = None


class DeviceUpdate(BaseModel):
    """更新設備對應的請求模型。"""
    old_hostname: str | None = None
    old_ip_address: str | None = None
    old_vendor: str | None = None
    new_hostname: str | None = None
    new_ip_address: str | None = None
    new_vendor: str | None = None
    use_same_port: bool | None = None
    tenant_group: TenantGroup | None = None
    is_reachable: bool | None = None
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
        "use_same_port": d.use_same_port,
        "tenant_group": d.tenant_group.value if d.tenant_group else TenantGroup.F18.value,
        # 舊設備可達性
        "old_is_reachable": d.old_is_reachable,
        "old_last_check_at": (
            d.old_last_check_at.isoformat() if d.old_last_check_at else None
        ),
        # 新設備可達性
        "is_reachable": d.is_reachable,
        "last_check_at": (
            d.last_check_at.isoformat() if d.last_check_at else None
        ),
        "description": d.description,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }


async def validate_device_mapping(
    session: AsyncSession,
    maintenance_id: str,
    old_hostname: str,
    old_ip_address: str,
    new_hostname: str,
    new_ip_address: str,
    existing_device_id: int | None = None,
) -> list[str]:
    """
    驗證設備對應的所有約束條件。

    Args:
        session: 資料庫 session
        maintenance_id: 歲修 ID
        old_hostname: 舊設備 hostname
        old_ip_address: 舊設備 IP
        new_hostname: 新設備 hostname
        new_ip_address: 新設備 IP
        existing_device_id: 如果是更新操作，提供現有設備的 ID（用於排除自己）

    Returns:
        錯誤訊息列表（空列表表示驗證通過）

    驗證規則：
    1. IP 格式驗證
    2. old_hostname 唯一性（只檢查 old 欄位，可以出現在 new 欄位）
    3. new_hostname 唯一性（只檢查 new 欄位，可以出現在 old 欄位）
    4. OLD IP 在所有 OLD 設備中唯一
    5. NEW IP 在所有 NEW 設備中唯一
    6. OLD 和 NEW 之間可以使用相同的 IP（舊 IP 給新設備重用）
    """
    errors = []

    # 1. IP 格式驗證
    try:
        ipaddress.ip_address(old_ip_address)
    except ValueError:
        errors.append(f"舊設備 IP 格式錯誤: {old_ip_address}")

    try:
        ipaddress.ip_address(new_ip_address)
    except ValueError:
        errors.append(f"新設備 IP 格式錯誤: {new_ip_address}")

    # 2. old_hostname 唯一性檢查（只檢查 old 欄位，可以出現在 new 欄位）
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

    # 3. new_hostname 唯一性檢查（只檢查 new 欄位，可以出現在 old 欄位）
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
            f"(在 {conflict_new.old_hostname} → {conflict_new.new_hostname} 的對應中)"
        )

    # 5. OLD IP 在所有 OLD 設備中唯一
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

    # 6. NEW IP 在所有 NEW 設備中唯一
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
async def get_vendor_options() -> dict[str, Any]:
    """取得廠商選項列表。"""
    return {
        "success": True,
        "options": DEVICE_VENDOR_OPTIONS,
    }


@router.get("/tenant-group-options")
async def get_tenant_group_options() -> dict[str, Any]:
    """取得 Tenant Group 選項列表。"""
    return {
        "success": True,
        "options": [tg.value for tg in TenantGroup],
    }


@router.get("/{maintenance_id}")
async def list_devices(
    maintenance_id: str,
    search: str | None = Query(None, description="搜尋 hostname 或 IP（支援多關鍵字，空格分隔）"),
    is_reachable: bool | None = Query(None, description="篩選新設備可達性（舊參數，建議用 reachability）"),
    reachability: str | None = Query(None, description="篩選可達性：old_true/old_false/new_true/new_false/any_true/any_false"),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    列出指定歲修的所有設備對應。

    搜尋邏輯：支援多關鍵字搜尋，空格分隔，所有關鍵字都必須匹配
    例如："SW 01 CORE" 會匹配 "SW-OLD-001-CORE"

    reachability 篩選選項：
    - old_true: 舊設備可達
    - old_false: 舊設備不可達
    - new_true: 新設備可達
    - new_false: 新設備不可達
    - any_true: 任一可達（舊或新）
    - any_false: 任一不可達（舊或新）
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

    # 新的可達性篩選
    if reachability:
        if reachability == "old_true":
            stmt = stmt.where(MaintenanceDeviceList.old_is_reachable == True)  # noqa: E712
        elif reachability == "old_false":
            stmt = stmt.where(MaintenanceDeviceList.old_is_reachable == False)  # noqa: E712
        elif reachability == "new_true":
            stmt = stmt.where(MaintenanceDeviceList.is_reachable == True)  # noqa: E712
        elif reachability == "new_false":
            stmt = stmt.where(MaintenanceDeviceList.is_reachable == False)  # noqa: E712
        elif reachability == "any_true":
            stmt = stmt.where(or_(
                MaintenanceDeviceList.old_is_reachable == True,  # noqa: E712
                MaintenanceDeviceList.is_reachable == True,  # noqa: E712
            ))
        elif reachability == "any_false":
            stmt = stmt.where(or_(
                MaintenanceDeviceList.old_is_reachable == False,  # noqa: E712
                MaintenanceDeviceList.is_reachable == False,  # noqa: E712
            ))
    # 向後相容舊參數
    elif is_reachable is not None:
        stmt = stmt.where(MaintenanceDeviceList.is_reachable == is_reachable)
    
    stmt = stmt.order_by(MaintenanceDeviceList.old_hostname)
    
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
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """獲取設備對應統計。"""
    # 總數
    total_stmt = (
        select(func.count(MaintenanceDeviceList.id))
        .where(MaintenanceDeviceList.maintenance_id == maintenance_id)
    )
    total = (await session.execute(total_stmt)).scalar() or 0
    
    # 已檢查可達數量
    reachable_stmt = (
        select(func.count(MaintenanceDeviceList.id))
        .where(
            MaintenanceDeviceList.maintenance_id == maintenance_id,
            MaintenanceDeviceList.is_reachable == True  # noqa: E712
        )
    )
    reachable = (await session.execute(reachable_stmt)).scalar() or 0
    
    # 已檢查不可達數量
    unreachable_stmt = (
        select(func.count(MaintenanceDeviceList.id))
        .where(
            MaintenanceDeviceList.maintenance_id == maintenance_id,
            MaintenanceDeviceList.is_reachable == False  # noqa: E712
        )
    )
    unreachable = (await session.execute(unreachable_stmt)).scalar() or 0
    
    # 未檢查數量
    unchecked = total - reachable - unreachable
    
    # 相同設備（不更換）數量
    same_device_stmt = (
        select(func.count(MaintenanceDeviceList.id))
        .where(
            MaintenanceDeviceList.maintenance_id == maintenance_id,
            MaintenanceDeviceList.old_hostname
            == MaintenanceDeviceList.new_hostname
        )
    )
    same_device = (await session.execute(same_device_stmt)).scalar() or 0
    
    return {
        "success": True,
        "total": total,
        "reachable": reachable,
        "unreachable": unreachable,
        "unchecked": unchecked,
        "same_device": same_device,
        "replaced": total - same_device,
        "reachable_rate": (
            round(reachable / total * 100, 1) if total > 0 else 0
        ),
    }


@router.post("/{maintenance_id}")
async def create_device(
    maintenance_id: str,
    data: DeviceCreate,
    _: Annotated[dict[str, Any], Depends(require_write())],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """新增設備對應。需要 device:write 權限。"""
    old_hostname = data.old_hostname.strip()
    old_ip_address = data.old_ip_address.strip()
    new_hostname = data.new_hostname.strip()
    new_ip_address = data.new_ip_address.strip()
    old_vendor = data.old_vendor.strip()
    new_vendor = data.new_vendor.strip()

    # 驗證 vendor
    if old_vendor not in DEVICE_VENDOR_OPTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"舊設備廠商必須是 {', '.join(DEVICE_VENDOR_OPTIONS)} 其中之一",
        )
    if new_vendor not in DEVICE_VENDOR_OPTIONS:
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
        use_same_port=data.use_same_port,
        tenant_group=data.tenant_group,
        description=data.description.strip() if data.description else None,
    )
    session.add(device)
    await session.commit()
    await session.refresh(device)

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

    # 計算更新後的值（使用新值或保留舊值）
    new_old_hostname = (
        data.old_hostname.strip()
        if data.old_hostname is not None
        else device.old_hostname
    )
    new_old_ip_address = (
        data.old_ip_address.strip()
        if data.old_ip_address is not None
        else device.old_ip_address
    )
    new_new_hostname = (
        data.new_hostname.strip()
        if data.new_hostname is not None
        else device.new_hostname
    )
    new_new_ip_address = (
        data.new_ip_address.strip()
        if data.new_ip_address is not None
        else device.new_ip_address
    )

    # 驗證 vendor（如果有提供的話）
    if data.old_vendor is not None:
        vendor = data.old_vendor.strip()
        if vendor not in DEVICE_VENDOR_OPTIONS:
            raise HTTPException(
                status_code=400,
                detail=f"廠商必須是 {', '.join(DEVICE_VENDOR_OPTIONS)} 其中之一",
            )
    if data.new_vendor is not None:
        vendor = data.new_vendor.strip()
        if vendor not in DEVICE_VENDOR_OPTIONS:
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
        device.old_vendor = data.old_vendor.strip()
    if data.new_hostname is not None:
        device.new_hostname = new_new_hostname
    if data.new_ip_address is not None:
        device.new_ip_address = new_new_ip_address
    if data.new_vendor is not None:
        device.new_vendor = data.new_vendor.strip()
    if data.use_same_port is not None:
        device.use_same_port = data.use_same_port
    if data.tenant_group is not None:
        device.tenant_group = data.tenant_group
    if data.is_reachable is not None:
        device.is_reachable = data.is_reachable
        device.last_check_at = datetime.utcnow()
    if data.description is not None:
        device.description = (
            data.description.strip() if data.description else None
        )

    await session.commit()
    await session.refresh(device)

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
    
    await session.delete(device)
    await session.commit()
    
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
    old_hostname,old_ip_address,old_vendor,new_hostname,new_ip_address,new_vendor,use_same_port,tenant_group,description

    - vendor: HPE / Cisco-IOS / Cisco-NXOS（必填）
    - use_same_port: true/false（預設 true）
    - tenant_group: F18/F6/AP/F14/F12（預設 F18）
    - description: 選填
    - 若設備不更換，新舊設備填同一台

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
        old_hostname = row.get('old_hostname', '').strip()
        old_ip = row.get('old_ip_address', '').strip()
        old_vendor = row.get('old_vendor', '').strip()
        new_hostname = row.get('new_hostname', '').strip()
        new_ip = row.get('new_ip_address', '').strip()
        new_vendor = row.get('new_vendor', '').strip()

        # 1. 驗證必填欄位
        if not old_hostname:
            errors.append(f"第 {row_num} 行：缺少 old_hostname")
            continue
        if not old_ip:
            errors.append(f"第 {row_num} 行：缺少 old_ip_address")
            continue
        if not old_vendor:
            errors.append(f"第 {row_num} 行：缺少 old_vendor")
            continue
        if not new_hostname:
            errors.append(f"第 {row_num} 行：缺少 new_hostname")
            continue
        if not new_ip:
            errors.append(f"第 {row_num} 行：缺少 new_ip_address")
            continue
        if not new_vendor:
            errors.append(f"第 {row_num} 行：缺少 new_vendor")
            continue

        # 2. 驗證 vendor
        if old_vendor not in DEVICE_VENDOR_OPTIONS:
            errors.append(
                f"第 {row_num} 行：old_vendor 必須是 "
                f"{', '.join(DEVICE_VENDOR_OPTIONS)} 其中之一"
            )
            continue
        if new_vendor not in DEVICE_VENDOR_OPTIONS:
            errors.append(
                f"第 {row_num} 行：new_vendor 必須是 "
                f"{', '.join(DEVICE_VENDOR_OPTIONS)} 其中之一"
            )
            continue

        # 3. 檢查 CSV 內部重複（hostname）
        # old_hostname 只檢查 old 欄位，可以出現在 new 欄位
        if old_hostname in used_old_hostnames_in_csv:
            errors.append(
                f"第 {row_num} 行：舊設備 {old_hostname} 在此 CSV 中重複"
            )
            continue
        # new_hostname 只檢查 new 欄位，可以出現在 old 欄位
        if new_hostname in used_new_hostnames_in_csv:
            errors.append(
                f"第 {row_num} 行：新設備 {new_hostname} 在此 CSV 中重複"
            )
            continue

        # 4. 檢查 CSV 內部 IP 重複
        if old_ip in used_old_ips_in_csv:
            errors.append(
                f"第 {row_num} 行：舊設備 IP {old_ip} 在此 CSV 中重複"
            )
            continue
        if new_ip in used_new_ips_in_csv:
            errors.append(
                f"第 {row_num} 行：新設備 IP {new_ip} 在此 CSV 中重複"
            )
            continue

        # 5. 檢查是否為更新（old_hostname 已存在）
        stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id,
            MaintenanceDeviceList.old_hostname == old_hostname,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        # 6. 檢查是否與現有記錄完全相同（相同則跳過）
        if existing:
            is_identical = (
                existing.old_ip_address == old_ip
                and existing.old_vendor == old_vendor
                and existing.new_hostname == new_hostname
                and existing.new_ip_address == new_ip
                and existing.new_vendor == new_vendor
            )
            if is_identical:
                # 完全相同，跳過不處理
                used_old_hostnames_in_csv.add(old_hostname)
                used_new_hostnames_in_csv.add(new_hostname)
                used_old_ips_in_csv.add(old_ip)
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
        use_same_port_str = row.get('use_same_port', 'true').strip().lower()
        use_same_port = use_same_port_str in ('true', '1', 'yes', 't', '')

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
            'use_same_port': use_same_port,
            'tenant_group': tenant_group,
            'description': row.get('description', '').strip() or None,
            'existing': existing,
        })

        # 追蹤已使用的值
        used_old_hostnames_in_csv.add(old_hostname)
        used_new_hostnames_in_csv.add(new_hostname)
        used_old_ips_in_csv.add(old_ip)
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
            existing.old_ip_address = item['old_ip']  # type: ignore[assignment]
            existing.old_vendor = item['old_vendor']  # type: ignore[assignment]
            existing.new_hostname = item['new_hostname']  # type: ignore[assignment]
            existing.new_ip_address = item['new_ip']  # type: ignore[assignment]
            existing.new_vendor = item['new_vendor']  # type: ignore[assignment]
            existing.use_same_port = item['use_same_port']  # type: ignore[assignment]
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
                use_same_port=item['use_same_port'],
                tenant_group=item['tenant_group'],
                description=item['description'],
            )
            session.add(device)
            imported += 1

    await session.commit()

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
    stmt = delete(MaintenanceDeviceList).where(
        MaintenanceDeviceList.maintenance_id == maintenance_id
    )
    result = await session.execute(stmt)
    await session.commit()
    
    return {
        "success": True,
        "message": f"已刪除 {result.rowcount} 筆設備對應",
        "deleted_count": result.rowcount,
    }


@router.post("/{maintenance_id}/batch-delete")
async def batch_delete_devices(
    maintenance_id: str,
    device_ids: list[int],
    _: Annotated[dict[str, Any], Depends(require_write())],
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

    stmt = delete(MaintenanceDeviceList).where(
        MaintenanceDeviceList.maintenance_id == maintenance_id,
        MaintenanceDeviceList.id.in_(device_ids),
    )
    result = await session.execute(stmt)
    await session.commit()

    return {
        "success": True,
        "deleted_count": result.rowcount,
        "message": f"已刪除 {result.rowcount} 筆設備對應",
    }


@router.get("/{maintenance_id}/export-csv")
async def export_devices_csv(
    maintenance_id: str,
    search: str | None = Query(None, description="搜尋過濾"),
    is_reachable: bool | None = Query(None, description="可達性過濾"),
    session: AsyncSession = Depends(get_async_session),
) -> StreamingResponse:
    """
    匯出設備對應為 CSV 文件。

    使用與列表相同的篩選邏輯（搜尋、可達性）
    """
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

    # 篩選可達性
    if is_reachable is not None:
        stmt = stmt.where(MaintenanceDeviceList.is_reachable == is_reachable)

    stmt = stmt.order_by(MaintenanceDeviceList.old_hostname)

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
        "use_same_port",
        "tenant_group",
        "is_reachable",
        "description",
    ])

    # 寫入數據行
    for d in devices:
        writer.writerow([
            d.old_hostname,
            d.old_ip_address,
            d.old_vendor,
            d.new_hostname,
            d.new_ip_address,
            d.new_vendor,
            str(d.use_same_port).lower(),
            d.tenant_group.value if d.tenant_group else TenantGroup.F18.value,
            str(d.is_reachable) if d.is_reachable is not None else "",
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


@router.post("/{maintenance_id}/batch-update-reachability")
async def batch_update_reachability(
    maintenance_id: str,
    updates: list[dict],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    批量更新設備可達性。

    updates 格式: [{"old_hostname": "xxx", "is_reachable": true/false}, ...]
    """
    updated_count = 0
    now = datetime.utcnow()
    
    for item in updates:
        old_hostname = item.get('old_hostname')
        is_reachable = item.get('is_reachable')
        
        if old_hostname is None or is_reachable is None:
            continue
        
        stmt = select(MaintenanceDeviceList).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id,
            MaintenanceDeviceList.old_hostname == old_hostname,
        )
        result = await session.execute(stmt)
        device = result.scalar_one_or_none()
        
        if device:
            device.is_reachable = is_reachable
            device.last_check_at = now
            updated_count += 1
    
    await session.commit()

    return {
        "success": True,
        "updated_count": updated_count,
    }


async def _ping_ip(api_client, site: str, ip_address: str, hostname: str = "") -> bool:
    """執行單一 IP 的 ping 測試。"""
    try:
        raw_output = await api_client.fetch(
            site=site,
            function="ping",
            switch_ip=ip_address,
            switch_hostname=hostname,
        )

        if raw_output:
            lower_output = raw_output.lower()

            # Mock API 返回 CSV 格式: "IP,Reachable\n192.168.1.1,true"
            if ",true" in lower_output:
                return True
            if ",false" in lower_output:
                return False

            # Real API 返回真實 ping 輸出
            if "100% packet loss" in lower_output or "0 packets received" in lower_output:
                return False
            elif "bytes from" in lower_output or "ttl=" in lower_output:
                return True
            elif "packets received" in lower_output:
                return "0 packets received" not in lower_output
        return False
    except Exception:
        return False


@router.post("/{maintenance_id}/{device_id}/test-reachability")
async def test_device_reachability(
    maintenance_id: str,
    device_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    測試單一設備的可達性。

    使用 GNMS Ping API 測試新舊設備 IP 是否可達，並更新資料庫中的狀態。
    """
    import asyncio
    from app.services.api_client import get_api_client

    # 查詢設備
    stmt = select(MaintenanceDeviceList).where(
        MaintenanceDeviceList.maintenance_id == maintenance_id,
        MaintenanceDeviceList.id == device_id,
    )
    result = await session.execute(stmt)
    device = result.scalar_one_or_none()

    if not device:
        raise HTTPException(status_code=404, detail="找不到指定的設備")

    # 使用 API client 進行 ping 測試
    api_client = get_api_client()
    site = f"{device.tenant_group.value.lower()}_site"

    # 並行測試新舊設備
    old_reachable, new_reachable = await asyncio.gather(
        _ping_ip(api_client, site, device.old_ip_address),
        _ping_ip(api_client, site, device.new_ip_address),
    )

    # 更新資料庫
    now = datetime.now()
    device.old_is_reachable = old_reachable
    device.old_last_check_at = now
    device.is_reachable = new_reachable
    device.last_check_at = now
    await session.commit()
    await session.refresh(device)

    return {
        "success": True,
        "device_id": device_id,
        "old_ip_address": device.old_ip_address,
        "old_is_reachable": old_reachable,
        "new_ip_address": device.new_ip_address,
        "is_reachable": new_reachable,
        "last_check_at": device.last_check_at.isoformat() if device.last_check_at else None,
    }


@router.post("/{maintenance_id}/batch-test-reachability")
async def batch_test_reachability(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    批量測試所有設備的可達性。

    對該歲修 ID 下的所有設備進行 GNMS Ping 測試（新舊設備都測試），
    並更新資料庫中的狀態。使用 asyncio.gather 並行執行 ping 以加速測試。
    """
    import asyncio
    from app.services.api_client import get_api_client

    # 查詢所有設備
    stmt = select(MaintenanceDeviceList).where(
        MaintenanceDeviceList.maintenance_id == maintenance_id,
    )
    result = await session.execute(stmt)
    devices = result.scalars().all()

    if not devices:
        return {
            "success": True,
            "total": 0,
            "old_reachable": 0,
            "old_unreachable": 0,
            "new_reachable": 0,
            "new_unreachable": 0,
            "results": [],
        }

    api_client = get_api_client()
    now = datetime.now()

    # 先提取需要的資料，避免 SQLAlchemy session 問題
    device_info = [
        {
            "id": d.id,
            "old_hostname": d.old_hostname,
            "old_ip_address": d.old_ip_address,
            "new_hostname": d.new_hostname,
            "new_ip_address": d.new_ip_address,
            "tenant_group": d.tenant_group.value.lower() if d.tenant_group else "f18",
        }
        for d in devices
    ]

    # 建立 ID 到 device 的映射
    device_map = {d.id: d for d in devices}

    async def ping_device(info: dict) -> dict:
        """測試單一設備的新舊 IP 可達性。"""
        site = f"{info['tenant_group']}_site"

        # 並行測試新舊設備（傳遞 hostname 讓 mock 判斷設備類型）
        old_reachable, new_reachable = await asyncio.gather(
            _ping_ip(api_client, site, info["old_ip_address"], info["old_hostname"]),
            _ping_ip(api_client, site, info["new_ip_address"], info["new_hostname"]),
        )

        return {
            "device_id": info["id"],
            "old_hostname": info["old_hostname"],
            "old_ip_address": info["old_ip_address"],
            "old_is_reachable": old_reachable,
            "new_hostname": info["new_hostname"],
            "new_ip_address": info["new_ip_address"],
            "is_reachable": new_reachable,
        }

    # 並行執行所有 ping 測試
    ping_results = await asyncio.gather(
        *[ping_device(info) for info in device_info],
        return_exceptions=True,
    )

    # 處理結果並更新資料庫
    results = []
    old_reachable_count = 0
    old_unreachable_count = 0
    new_reachable_count = 0
    new_unreachable_count = 0

    for ping_result in ping_results:
        if isinstance(ping_result, Exception):
            continue

        device_id = ping_result["device_id"]
        old_is_reachable = ping_result["old_is_reachable"]
        new_is_reachable = ping_result["is_reachable"]

        # 更新資料庫中的設備
        device = device_map.get(device_id)
        if device:
            device.old_is_reachable = old_is_reachable
            device.old_last_check_at = now
            device.is_reachable = new_is_reachable
            device.last_check_at = now

        if old_is_reachable:
            old_reachable_count += 1
        else:
            old_unreachable_count += 1

        if new_is_reachable:
            new_reachable_count += 1
        else:
            new_unreachable_count += 1

        results.append(ping_result)

    await session.commit()

    return {
        "success": True,
        "total": len(devices),
        "old_reachable": old_reachable_count,
        "old_unreachable": old_unreachable_count,
        "new_reachable": new_reachable_count,
        "new_unreachable": new_unreachable_count,
        "results": results,
    }
