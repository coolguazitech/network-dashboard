"""
Uplink and Version Expectations API endpoints.

提供期望值管理的 CRUD 操作。
"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_async_session as get_session
from app.db.models import (
    UplinkExpectation,
    VersionExpectation,
    ArpSource,
    PortChannelExpectation,
    MaintenanceDeviceList,
)

router = APIRouter(tags=["expectations"])


# ========== Helper Functions ==========

async def validate_hostname_in_device_list(
    maintenance_id: str,
    hostname: str,
    session: AsyncSession,
    field_name: str = "hostname",
) -> None:
    """
    驗證 hostname 是否存在於設備清單的「新設備」中。

    Args:
        maintenance_id: 歲修 ID
        hostname: 要驗證的主機名稱
        session: 資料庫 session
        field_name: 欄位名稱（用於錯誤訊息）

    Raises:
        HTTPException: 如果 hostname 不在設備清單中
    """
    stmt = select(MaintenanceDeviceList).where(
        MaintenanceDeviceList.maintenance_id == maintenance_id,
        MaintenanceDeviceList.new_hostname == hostname,
    )
    result = await session.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} '{hostname}' 不在設備清單的新設備中，"
                   f"請先在設備清單中新增此設備"
        )


async def validate_hostname_in_device_list_any(
    maintenance_id: str,
    hostname: str,
    session: AsyncSession,
    field_name: str = "hostname",
) -> None:
    """
    驗證 hostname 是否存在於設備清單的「新設備」或「舊設備」中。

    用於 Uplink 期望和 ARP 來源，這些可以參照新設備或舊設備。

    Args:
        maintenance_id: 歲修 ID
        hostname: 要驗證的主機名稱
        session: 資料庫 session
        field_name: 欄位名稱（用於錯誤訊息）

    Raises:
        HTTPException: 如果 hostname 不在設備清單中
    """
    from sqlalchemy import or_
    stmt = select(MaintenanceDeviceList).where(
        MaintenanceDeviceList.maintenance_id == maintenance_id,
        or_(
            MaintenanceDeviceList.new_hostname == hostname,
            MaintenanceDeviceList.old_hostname == hostname,
        ),
    )
    result = await session.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} '{hostname}' 不在設備清單中，"
                   f"請先在設備清單中新增此設備"
        )


async def get_valid_new_hostnames(
    maintenance_id: str,
    session: AsyncSession,
) -> set[str]:
    """
    取得設備清單中所有新設備的 hostname。

    用於批量匯入時的驗證。

    Returns:
        新設備 hostname 的集合
    """
    stmt = select(MaintenanceDeviceList.new_hostname).where(
        MaintenanceDeviceList.maintenance_id == maintenance_id
    )
    result = await session.execute(stmt)
    return {row[0] for row in result.fetchall()}


async def get_valid_all_hostnames(
    maintenance_id: str,
    session: AsyncSession,
) -> set[str]:
    """
    取得設備清單中所有設備的 hostname（新設備 + 舊設備）。

    用於 Uplink 期望和 ARP 來源的批量匯入驗證。

    Returns:
        所有設備 hostname 的集合
    """
    stmt = select(
        MaintenanceDeviceList.new_hostname,
        MaintenanceDeviceList.old_hostname,
    ).where(
        MaintenanceDeviceList.maintenance_id == maintenance_id
    )
    result = await session.execute(stmt)
    hostnames = set()
    for row in result.fetchall():
        if row[0]:
            hostnames.add(row[0])
        if row[1]:
            hostnames.add(row[1])
    return hostnames


# ========== Pydantic Models ==========

class UplinkExpectationCreate(BaseModel):
    hostname: str
    local_interface: str
    expected_neighbor: str
    expected_interface: str | None = None
    description: str | None = None


class UplinkExpectationUpdate(BaseModel):
    hostname: str | None = None
    local_interface: str | None = None
    expected_neighbor: str | None = None
    expected_interface: str | None = None
    description: str | None = None


class UplinkExpectationResponse(BaseModel):
    id: int
    maintenance_id: str
    hostname: str
    local_interface: str
    expected_neighbor: str
    expected_interface: str | None
    description: str | None

    class Config:
        from_attributes = True


class VersionExpectationCreate(BaseModel):
    hostname: str
    expected_versions: str  # 分號分隔的版本列表
    description: str | None = None


class VersionExpectationUpdate(BaseModel):
    hostname: str | None = None
    expected_versions: str | None = None
    description: str | None = None


class VersionExpectationResponse(BaseModel):
    id: int
    maintenance_id: str
    hostname: str
    expected_versions: str
    description: str | None

    class Config:
        from_attributes = True


# ========== Uplink Expectations ==========

@router.get("/uplink/{maintenance_id}")
async def list_uplink_expectations(
    maintenance_id: str,
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """列出 Uplink 期望。"""
    stmt = select(UplinkExpectation).where(
        UplinkExpectation.maintenance_id == maintenance_id
    )
    
    if search:
        from sqlalchemy import and_, or_
        keywords = search.strip().split()

        # 只匹配 hostname, expected_neighbor, description（不跨欄匹配）
        field_conditions = []
        for field in [
            UplinkExpectation.hostname,
            UplinkExpectation.expected_neighbor,
            UplinkExpectation.description,
        ]:
            field_match = and_(*[field.ilike(f"%{kw}%") for kw in keywords])
            field_conditions.append(field_match)

        stmt = stmt.where(or_(*field_conditions))
    
    stmt = stmt.order_by(UplinkExpectation.hostname)
    result = await session.execute(stmt)
    items = result.scalars().all()
    
    return {
        "total": len(items),
        "items": [
            {
                "id": item.id,
                "hostname": item.hostname,
                "local_interface": item.local_interface,
                "expected_neighbor": item.expected_neighbor,
                "expected_interface": item.expected_interface,
                "description": item.description,
            }
            for item in items
        ],
    }


@router.post("/uplink/{maintenance_id}")
async def create_uplink_expectation(
    maintenance_id: str,
    data: UplinkExpectationCreate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """新增 Uplink 期望。"""
    hostname = data.hostname.strip()
    local_interface = data.local_interface.strip()
    expected_neighbor = data.expected_neighbor.strip()
    expected_interface = data.expected_interface.strip() if data.expected_interface else None

    # 驗證 hostname 和 expected_neighbor 都存在於設備清單（新設備或舊設備皆可）
    await validate_hostname_in_device_list_any(
        maintenance_id, hostname, session, "本地設備"
    )
    await validate_hostname_in_device_list_any(
        maintenance_id, expected_neighbor, session, "鄰居設備"
    )

    # 當鄰居是自己時，本地介面與鄰居介面必須不同
    if hostname == expected_neighbor:
        if expected_interface and local_interface == expected_interface:
            raise HTTPException(
                status_code=400,
                detail=f"自連接時介面必須不同：{hostname} 的本地介面與鄰居介面都是 {local_interface}"
            )

    # 檢查 hostname + local_interface 是否已存在
    dup_stmt = select(UplinkExpectation).where(
        UplinkExpectation.maintenance_id == maintenance_id,
        UplinkExpectation.hostname == hostname,
        UplinkExpectation.local_interface == local_interface,
    )
    dup_result = await session.execute(dup_stmt)
    if dup_result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"本地介面重複：{hostname}:{local_interface} 已存在"
        )

    # 嚴格拓樸檢查：確保介面未被其他記錄使用（無論作為本地或遠端）
    # 1. 檢查本地介面是否被用作其他記錄的遠端
    stmt1 = select(UplinkExpectation).where(
        UplinkExpectation.maintenance_id == maintenance_id,
        UplinkExpectation.expected_neighbor == hostname,
        UplinkExpectation.expected_interface == local_interface,
    )
    res1 = await session.execute(stmt1)
    if res1.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"介面衝突：{hostname}:{local_interface} 已被其他記錄設為鄰居"
        )

    if expected_interface:
        # 2. 檢查遠端介面是否被用作其他記錄的本地
        stmt2 = select(UplinkExpectation).where(
            UplinkExpectation.maintenance_id == maintenance_id,
            UplinkExpectation.hostname == expected_neighbor,
            UplinkExpectation.local_interface == expected_interface,
        )
        res2 = await session.execute(stmt2)
        if res2.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"介面衝突：鄰居 {expected_neighbor}:{expected_interface} 已經配置為本地介面"
            )
            
        # 3. 檢查遠端介面是否被用作其他記錄的遠端
        stmt3 = select(UplinkExpectation).where(
            UplinkExpectation.maintenance_id == maintenance_id,
            UplinkExpectation.expected_neighbor == expected_neighbor,
            UplinkExpectation.expected_interface == expected_interface,
        )
        res3 = await session.execute(stmt3)
        if res3.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"介面衝突：鄰居 {expected_neighbor}:{expected_interface} 已被其他記錄連接"
            )
    
    item = UplinkExpectation(
        maintenance_id=maintenance_id,
        hostname=data.hostname.strip(),
        local_interface=data.local_interface.strip(),
        expected_neighbor=data.expected_neighbor.strip(),
        expected_interface=data.expected_interface.strip() if data.expected_interface else None,
        description=data.description.strip() if data.description else None,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    
    return {
        "id": item.id,
        "hostname": item.hostname,
        "local_interface": item.local_interface,
        "expected_neighbor": item.expected_neighbor,
        "expected_interface": item.expected_interface,
        "description": item.description,
    }


@router.put("/uplink/{maintenance_id}/{item_id}")
async def update_uplink_expectation(
    maintenance_id: str,
    item_id: int,
    data: UplinkExpectationUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """更新 Uplink 期望。"""
    stmt = select(UplinkExpectation).where(
        UplinkExpectation.id == item_id,
        UplinkExpectation.maintenance_id == maintenance_id,
    )
    result = await session.execute(stmt)
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Uplink 期望不存在")
    
    # 計算更新後的值
    new_hostname = (
        data.hostname.strip()
        if data.hostname is not None
        else item.hostname
    )
    new_local_interface = (
        data.local_interface.strip()
        if data.local_interface is not None
        else item.local_interface
    )
    new_neighbor = (
        data.expected_neighbor.strip()
        if data.expected_neighbor is not None
        else item.expected_neighbor
    )

    # 驗證變更的 hostname 和 expected_neighbor 存在於設備清單（新設備或舊設備皆可）
    if data.hostname is not None and new_hostname != item.hostname:
        await validate_hostname_in_device_list_any(
            maintenance_id, new_hostname, session, "本地設備"
        )
    if data.expected_neighbor is not None and new_neighbor != item.expected_neighbor:
        await validate_hostname_in_device_list_any(
            maintenance_id, new_neighbor, session, "鄰居設備"
        )

    # 計算更新後的鄰居介面
    new_neighbor_int_for_self_check = (
        data.expected_interface.strip()
        if data.expected_interface is not None and data.expected_interface
        else item.expected_interface
    )

    # 當鄰居是自己時，本地介面與鄰居介面必須不同
    if new_hostname == new_neighbor:
        if new_neighbor_int_for_self_check and new_local_interface == new_neighbor_int_for_self_check:
            raise HTTPException(
                status_code=400,
                detail=f"自連接時介面必須不同：{new_hostname} 的本地介面與鄰居介面都是 {new_local_interface}"
            )

    # 檢查更新後是否會與其他記錄重複
    if data.hostname is not None or data.local_interface is not None:
        dup_stmt = select(UplinkExpectation).where(
            UplinkExpectation.maintenance_id == maintenance_id,
            UplinkExpectation.hostname == new_hostname,
            UplinkExpectation.local_interface == new_local_interface,
            UplinkExpectation.id != item_id,
        )
        dup_result = await session.execute(dup_stmt)
        if dup_result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"本地介面重複：{new_hostname}:{new_local_interface} 已存在"
            )
            
    # 嚴格拓樸檢查（排除自己）
    new_neighbor_int = (
        data.expected_interface.strip()
        if data.expected_interface is not None
        else item.expected_interface
    )
    if data.expected_interface is not None and not data.expected_interface:
        new_neighbor_int = None # Handle empty string clearing

    # 1. 檢查本地介面是否被其他記錄（非自己）用作遠端
    stmt1 = select(UplinkExpectation).where(
        UplinkExpectation.maintenance_id == maintenance_id,
        UplinkExpectation.expected_neighbor == new_hostname,
        UplinkExpectation.expected_interface == new_local_interface,
        UplinkExpectation.id != item_id,
    )
    res1 = await session.execute(stmt1)
    if res1.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"介面衝突：{new_hostname}:{new_local_interface} 已被其他記錄設為鄰居"
        )

    if new_neighbor_int:
        # 2. 檢查遠端介面是否被其他記錄（非自己）用作本地
        stmt2 = select(UplinkExpectation).where(
            UplinkExpectation.maintenance_id == maintenance_id,
            UplinkExpectation.hostname == new_neighbor,
            UplinkExpectation.local_interface == new_neighbor_int,
            UplinkExpectation.id != item_id,
        )
        res2 = await session.execute(stmt2)
        if res2.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"介面衝突：鄰居 {new_neighbor}:{new_neighbor_int} 已經配置為本地介面"
            )
            
        # 3. 檢查遠端介面是否被其他記錄（非自己）用作遠端
        stmt3 = select(UplinkExpectation).where(
            UplinkExpectation.maintenance_id == maintenance_id,
            UplinkExpectation.expected_neighbor == new_neighbor,
            UplinkExpectation.expected_interface == new_neighbor_int,
            UplinkExpectation.id != item_id,
        )
        res3 = await session.execute(stmt3)
        if res3.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"介面衝突：鄰居 {new_neighbor}:{new_neighbor_int} 已被其他記錄連接"
            )
    
    if data.hostname is not None:
        item.hostname = data.hostname.strip()
    if data.local_interface is not None:
        item.local_interface = data.local_interface.strip()
    if data.expected_neighbor is not None:
        item.expected_neighbor = data.expected_neighbor.strip()
    if data.expected_interface is not None:
        item.expected_interface = data.expected_interface.strip() if data.expected_interface else None
    if data.description is not None:
        item.description = data.description.strip() if data.description else None
    
    await session.commit()
    await session.refresh(item)
    
    return {
        "id": item.id,
        "hostname": item.hostname,
        "local_interface": item.local_interface,
        "expected_neighbor": item.expected_neighbor,
        "expected_interface": item.expected_interface,
        "description": item.description,
    }


@router.delete("/uplink/{maintenance_id}/{item_id}")
async def delete_uplink_expectation(
    maintenance_id: str,
    item_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """刪除 Uplink 期望。"""
    stmt = select(UplinkExpectation).where(
        UplinkExpectation.id == item_id,
        UplinkExpectation.maintenance_id == maintenance_id,
    )
    result = await session.execute(stmt)
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="Uplink 期望不存在")
    
    await session.delete(item)
    await session.commit()
    
    return {"status": "deleted"}


@router.post("/uplink/{maintenance_id}/batch-delete")
async def batch_delete_uplink_expectations(
    maintenance_id: str,
    item_ids: list[int],
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """批量刪除 Uplink 期望。"""
    if not item_ids:
        return {
            "success": True,
            "deleted_count": 0,
            "message": "沒有選中任何項目",
        }

    stmt = delete(UplinkExpectation).where(
        UplinkExpectation.maintenance_id == maintenance_id,
        UplinkExpectation.id.in_(item_ids),
    )
    result = await session.execute(stmt)
    await session.commit()

    return {
        "success": True,
        "deleted_count": result.rowcount,
        "message": f"已刪除 {result.rowcount} 筆 Uplink 期望",
    }


@router.get("/uplink/{maintenance_id}/export-csv")
async def export_uplink_csv(
    maintenance_id: str,
    search: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """匯出 Uplink 期望為 CSV 文件。"""
    stmt = select(UplinkExpectation).where(
        UplinkExpectation.maintenance_id == maintenance_id
    )

    if search:
        from sqlalchemy import and_, or_
        keywords = search.strip().split()

        # 只匹配 hostname, expected_neighbor, description（不跨欄匹配）
        field_conditions = []
        for field in [
            UplinkExpectation.hostname,
            UplinkExpectation.expected_neighbor,
            UplinkExpectation.description,
        ]:
            field_match = and_(*[field.ilike(f"%{kw}%") for kw in keywords])
            field_conditions.append(field_match)

        stmt = stmt.where(or_(*field_conditions))

    stmt = stmt.order_by(UplinkExpectation.hostname)
    result = await session.execute(stmt)
    items = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "hostname",
        "local_interface",
        "expected_neighbor",
        "expected_interface",
        "description",
    ])

    for item in items:
        writer.writerow([
            item.hostname,
            item.local_interface,
            item.expected_neighbor,
            item.expected_interface or "",
            item.description or "",
        ])

    output.seek(0)
    content = "\ufeff" + output.getvalue()

    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{maintenance_id}_uplink.csv"'
        },
    )


@router.post("/uplink/{maintenance_id}/import-csv")
async def import_uplink_csv(
    maintenance_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """從 CSV 匯入 Uplink 期望。"""
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    # 預先載入有效的設備 hostname（新設備 + 舊設備）
    valid_hostnames = await get_valid_all_hostnames(maintenance_id, session)

    imported = 0
    updated = 0
    errors = []

    for row_num, row in enumerate(reader, start=2):
        try:
            hostname = row.get("hostname", "").strip()
            local_interface = row.get("local_interface", "").strip()
            expected_neighbor = row.get("expected_neighbor", "").strip()
            expected_interface = row.get("expected_interface", "").strip() or None
            description = row.get("description", "").strip() or None

            if not hostname or not local_interface or not expected_neighbor:
                errors.append(f"Row {row_num}: 必填欄位不完整")
                continue

            # 驗證 hostname 和 expected_neighbor 存在於設備清單（新設備或舊設備）
            if hostname not in valid_hostnames:
                errors.append(
                    f"Row {row_num}: 本地設備 '{hostname}' 不在設備清單中"
                )
                continue
            if expected_neighbor not in valid_hostnames:
                errors.append(
                    f"Row {row_num}: 鄰居設備 '{expected_neighbor}' 不在設備清單中"
                )
                continue

            # 檢查是否已存在
            stmt = select(UplinkExpectation).where(
                UplinkExpectation.maintenance_id == maintenance_id,
                UplinkExpectation.hostname == hostname,
                UplinkExpectation.local_interface == local_interface,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                existing.expected_neighbor = expected_neighbor
                existing.expected_interface = expected_interface
                existing.description = description
                updated += 1
            else:
                item = UplinkExpectation(
                    maintenance_id=maintenance_id,
                    hostname=hostname,
                    local_interface=local_interface,
                    expected_neighbor=expected_neighbor,
                    expected_interface=expected_interface,
                    description=description,
                )
                session.add(item)
                imported += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
    
    await session.commit()
    
    return {
        "imported": imported,
        "updated": updated,
        "total_errors": len(errors),
        "errors": errors[:10],  # 只返回前 10 個錯誤
    }


# ========== Version Expectations ==========

@router.get("/version/{maintenance_id}")
async def list_version_expectations(
    maintenance_id: str,
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """列出版本期望。"""
    stmt = select(VersionExpectation).where(
        VersionExpectation.maintenance_id == maintenance_id
    )
    
    if search:
        from sqlalchemy import and_, or_
        keywords = search.strip().split()

        # 只匹配 hostname, expected_versions, description（不跨欄匹配）
        field_conditions = []
        for field in [
            VersionExpectation.hostname,
            VersionExpectation.expected_versions,
            VersionExpectation.description,
        ]:
            field_match = and_(*[field.ilike(f"%{kw}%") for kw in keywords])
            field_conditions.append(field_match)

        stmt = stmt.where(or_(*field_conditions))

    stmt = stmt.order_by(VersionExpectation.hostname)
    result = await session.execute(stmt)
    items = result.scalars().all()
    
    return {
        "total": len(items),
        "items": [
            {
                "id": item.id,
                "hostname": item.hostname,
                "expected_versions": item.expected_versions,
                "expected_versions_list": item.expected_versions.split(";") if item.expected_versions else [],
                "description": item.description,
            }
            for item in items
        ],
    }


@router.post("/version/{maintenance_id}")
async def create_version_expectation(
    maintenance_id: str,
    data: VersionExpectationCreate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """新增版本期望。"""
    hostname = data.hostname.strip()

    # 驗證 hostname 存在於設備清單的新設備中
    await validate_hostname_in_device_list(maintenance_id, hostname, session, "設備")

    # 檢查 hostname 是否已存在（一台設備只能有一筆版本期望）
    dup_stmt = select(VersionExpectation).where(
        VersionExpectation.maintenance_id == maintenance_id,
        VersionExpectation.hostname == hostname,
    )
    dup_result = await session.execute(dup_stmt)
    if dup_result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"版本期望設備 {hostname} 已存在"
        )
    
    # 標準化版本格式（移除空白）
    versions = ";".join(
        v.strip() for v in data.expected_versions.split(";") if v.strip()
    )
    
    item = VersionExpectation(
        maintenance_id=maintenance_id,
        hostname=data.hostname.strip(),
        expected_versions=versions,
        description=data.description.strip() if data.description else None,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    
    return {
        "id": item.id,
        "hostname": item.hostname,
        "expected_versions": item.expected_versions,
        "expected_versions_list": item.expected_versions.split(";"),
        "description": item.description,
    }


@router.put("/version/{maintenance_id}/{item_id}")
async def update_version_expectation(
    maintenance_id: str,
    item_id: int,
    data: VersionExpectationUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """更新版本期望。"""
    stmt = select(VersionExpectation).where(
        VersionExpectation.id == item_id,
        VersionExpectation.maintenance_id == maintenance_id,
    )
    result = await session.execute(stmt)
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="版本期望不存在")
    
    # 檢查更新後的 hostname 是否會與其他記錄重複
    if data.hostname is not None:
        new_hostname = data.hostname.strip()
        if new_hostname != item.hostname:
            # 驗證新 hostname 存在於設備清單的新設備中
            await validate_hostname_in_device_list(
                maintenance_id, new_hostname, session, "設備"
            )

            dup_stmt = select(VersionExpectation).where(
                VersionExpectation.maintenance_id == maintenance_id,
                VersionExpectation.hostname == new_hostname,
                VersionExpectation.id != item_id,
            )
            dup_result = await session.execute(dup_stmt)
            if dup_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=400,
                    detail=f"版本期望設備 {new_hostname} 已存在"
                )

    if data.hostname is not None:
        item.hostname = data.hostname.strip()
    if data.expected_versions is not None:
        versions = ";".join(v.strip() for v in data.expected_versions.split(";") if v.strip())
        item.expected_versions = versions
    if data.description is not None:
        item.description = data.description.strip() if data.description else None
    
    await session.commit()
    await session.refresh(item)
    
    return {
        "id": item.id,
        "hostname": item.hostname,
        "expected_versions": item.expected_versions,
        "expected_versions_list": item.expected_versions.split(";"),
        "description": item.description,
    }


@router.delete("/version/{maintenance_id}/{item_id}")
async def delete_version_expectation(
    maintenance_id: str,
    item_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """刪除版本期望。"""
    stmt = select(VersionExpectation).where(
        VersionExpectation.id == item_id,
        VersionExpectation.maintenance_id == maintenance_id,
    )
    result = await session.execute(stmt)
    item = result.scalar_one_or_none()
    
    if not item:
        raise HTTPException(status_code=404, detail="版本期望不存在")
    
    await session.delete(item)
    await session.commit()
    
    return {"status": "deleted"}


@router.post("/version/{maintenance_id}/batch-delete")
async def batch_delete_version_expectations(
    maintenance_id: str,
    item_ids: list[int],
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """批量刪除版本期望。"""
    if not item_ids:
        return {
            "success": True,
            "deleted_count": 0,
            "message": "沒有選中任何項目",
        }

    stmt = delete(VersionExpectation).where(
        VersionExpectation.maintenance_id == maintenance_id,
        VersionExpectation.id.in_(item_ids),
    )
    result = await session.execute(stmt)
    await session.commit()

    return {
        "success": True,
        "deleted_count": result.rowcount,
        "message": f"已刪除 {result.rowcount} 筆版本期望",
    }


@router.get("/version/{maintenance_id}/export-csv")
async def export_version_csv(
    maintenance_id: str,
    search: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """匯出版本期望為 CSV 文件。"""
    stmt = select(VersionExpectation).where(
        VersionExpectation.maintenance_id == maintenance_id
    )

    if search:
        from sqlalchemy import and_, or_
        keywords = search.strip().split()

        # 只匹配 hostname, expected_versions, description（不跨欄匹配）
        field_conditions = []
        for field in [
            VersionExpectation.hostname,
            VersionExpectation.expected_versions,
            VersionExpectation.description,
        ]:
            field_match = and_(*[field.ilike(f"%{kw}%") for kw in keywords])
            field_conditions.append(field_match)

        stmt = stmt.where(or_(*field_conditions))

    stmt = stmt.order_by(VersionExpectation.hostname)
    result = await session.execute(stmt)
    items = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["hostname", "expected_versions", "description"])

    for item in items:
        writer.writerow([
            item.hostname,
            item.expected_versions,
            item.description or "",
        ])

    output.seek(0)
    content = "\ufeff" + output.getvalue()

    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{maintenance_id}_version.csv"'
        },
    )


@router.post("/version/{maintenance_id}/import-csv")
async def import_version_csv(
    maintenance_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """從 CSV 匯入版本期望。"""
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    # 預先載入有效的新設備 hostname
    valid_hostnames = await get_valid_new_hostnames(maintenance_id, session)

    imported = 0
    updated = 0
    errors = []

    for row_num, row in enumerate(reader, start=2):
        try:
            hostname = row.get("hostname", "").strip()
            expected_versions = row.get("expected_versions", "").strip()
            description = row.get("description", "").strip() or None

            if not hostname or not expected_versions:
                errors.append(f"Row {row_num}: 必填欄位不完整")
                continue

            # 驗證 hostname 存在於設備清單的新設備中
            if hostname not in valid_hostnames:
                errors.append(
                    f"Row {row_num}: 設備 '{hostname}' 不在設備清單的新設備中"
                )
                continue

            # 標準化版本格式
            versions = ";".join(v.strip() for v in expected_versions.split(";") if v.strip())
            
            # 檢查是否已存在（同一台設備只能有一筆）
            stmt = select(VersionExpectation).where(
                VersionExpectation.maintenance_id == maintenance_id,
                VersionExpectation.hostname == hostname,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()
            
            if existing:
                existing.expected_versions = versions
                existing.description = description
                updated += 1
            else:
                item = VersionExpectation(
                    maintenance_id=maintenance_id,
                    hostname=hostname,
                    expected_versions=versions,
                    description=description,
                )
                session.add(item)
                imported += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")
    
    await session.commit()
    
    return {
        "imported": imported,
        "updated": updated,
        "total_errors": len(errors),
        "errors": errors[:10],
    }


# ========== ARP Source Pydantic Models ==========

class ArpSourceCreate(BaseModel):
    hostname: str
    priority: int = 100
    description: str | None = None


class ArpSourceUpdate(BaseModel):
    hostname: str | None = None
    priority: int | None = None
    description: str | None = None


# ========== ARP Sources ==========

@router.get("/arp/{maintenance_id}")
async def list_arp_sources(
    maintenance_id: str,
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """列出 ARP 來源設備。"""
    stmt = select(ArpSource).where(
        ArpSource.maintenance_id == maintenance_id
    )

    if search:
        from sqlalchemy import and_, or_
        keywords = search.strip().split()

        field_conditions = []
        for field in [ArpSource.hostname, ArpSource.description]:
            field_match = and_(*[field.ilike(f"%{kw}%") for kw in keywords])
            field_conditions.append(field_match)

        stmt = stmt.where(or_(*field_conditions))

    stmt = stmt.order_by(ArpSource.priority, ArpSource.hostname)
    result = await session.execute(stmt)
    items = result.scalars().all()

    return {
        "total": len(items),
        "items": [
            {
                "id": item.id,
                "hostname": item.hostname,
                "priority": item.priority,
                "description": item.description,
            }
            for item in items
        ],
    }


@router.post("/arp/{maintenance_id}")
async def create_arp_source(
    maintenance_id: str,
    data: ArpSourceCreate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """新增 ARP 來源設備。"""
    hostname = data.hostname.strip()

    # 驗證 hostname 存在於設備清單（新設備或舊設備皆可）
    await validate_hostname_in_device_list_any(maintenance_id, hostname, session, "設備")

    # 檢查 hostname 是否已存在
    dup_stmt = select(ArpSource).where(
        ArpSource.maintenance_id == maintenance_id,
        ArpSource.hostname == hostname,
    )
    dup_result = await session.execute(dup_stmt)
    if dup_result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"ARP 來源設備 {hostname} 已存在"
        )

    # 檢查 priority 是否已存在
    priority_stmt = select(ArpSource).where(
        ArpSource.maintenance_id == maintenance_id,
        ArpSource.priority == data.priority,
    )
    priority_result = await session.execute(priority_stmt)
    if priority_result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"優先級 {data.priority} 已被使用，請選擇其他優先級"
        )

    item = ArpSource(
        maintenance_id=maintenance_id,
        hostname=hostname,
        priority=data.priority,
        description=data.description.strip() if data.description else None,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)

    return {
        "id": item.id,
        "hostname": item.hostname,
        "priority": item.priority,
        "description": item.description,
    }


@router.put("/arp/{maintenance_id}/{item_id}")
async def update_arp_source(
    maintenance_id: str,
    item_id: int,
    data: ArpSourceUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """更新 ARP 來源設備。"""
    stmt = select(ArpSource).where(
        ArpSource.id == item_id,
        ArpSource.maintenance_id == maintenance_id,
    )
    result = await session.execute(stmt)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="ARP 來源不存在")

    # 檢查更新後的 hostname 是否會與其他記錄重複
    if data.hostname is not None:
        new_hostname = data.hostname.strip()
        if new_hostname != item.hostname:
            # 驗證新 hostname 存在於設備清單（新設備或舊設備皆可）
            await validate_hostname_in_device_list_any(
                maintenance_id, new_hostname, session, "設備"
            )

            dup_stmt = select(ArpSource).where(
                ArpSource.maintenance_id == maintenance_id,
                ArpSource.hostname == new_hostname,
                ArpSource.id != item_id,
            )
            dup_result = await session.execute(dup_stmt)
            if dup_result.scalar_one_or_none():
                raise HTTPException(
                    status_code=400,
                    detail=f"ARP 來源設備 {new_hostname} 已存在"
                )

    # 檢查更新後的 priority 是否會與其他記錄重複
    if data.priority is not None and data.priority != item.priority:
        priority_stmt = select(ArpSource).where(
            ArpSource.maintenance_id == maintenance_id,
            ArpSource.priority == data.priority,
            ArpSource.id != item_id,
        )
        priority_result = await session.execute(priority_stmt)
        if priority_result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"優先級 {data.priority} 已被使用，請選擇其他優先級"
            )

    if data.hostname is not None:
        item.hostname = data.hostname.strip()
    if data.priority is not None:
        item.priority = data.priority
    if data.description is not None:
        item.description = data.description.strip() if data.description else None

    await session.commit()
    await session.refresh(item)

    return {
        "id": item.id,
        "hostname": item.hostname,
        "priority": item.priority,
        "description": item.description,
    }


@router.delete("/arp/{maintenance_id}/{item_id}")
async def delete_arp_source(
    maintenance_id: str,
    item_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """刪除 ARP 來源設備。"""
    stmt = select(ArpSource).where(
        ArpSource.id == item_id,
        ArpSource.maintenance_id == maintenance_id,
    )
    result = await session.execute(stmt)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="ARP 來源不存在")

    await session.delete(item)
    await session.commit()

    return {"status": "deleted"}


@router.post("/arp/{maintenance_id}/batch-delete")
async def batch_delete_arp_sources(
    maintenance_id: str,
    item_ids: list[int],
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """批量刪除 ARP 來源。"""
    if not item_ids:
        return {
            "success": True,
            "deleted_count": 0,
            "message": "沒有選中任何項目",
        }

    stmt = delete(ArpSource).where(
        ArpSource.maintenance_id == maintenance_id,
        ArpSource.id.in_(item_ids),
    )
    result = await session.execute(stmt)
    await session.commit()

    return {
        "success": True,
        "deleted_count": result.rowcount,
        "message": f"已刪除 {result.rowcount} 筆 ARP 來源",
    }


@router.get("/arp/{maintenance_id}/export-csv")
async def export_arp_csv(
    maintenance_id: str,
    search: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """匯出 ARP 來源為 CSV 文件。"""
    stmt = select(ArpSource).where(
        ArpSource.maintenance_id == maintenance_id
    )

    if search:
        from sqlalchemy import and_, or_
        keywords = search.strip().split()

        field_conditions = []
        for field in [ArpSource.hostname, ArpSource.description]:
            field_match = and_(*[field.ilike(f"%{kw}%") for kw in keywords])
            field_conditions.append(field_match)

        stmt = stmt.where(or_(*field_conditions))

    stmt = stmt.order_by(ArpSource.priority, ArpSource.hostname)
    result = await session.execute(stmt)
    items = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["hostname", "priority", "description"])

    for item in items:
        writer.writerow([
            item.hostname,
            str(item.priority),
            item.description or "",
        ])

    output.seek(0)
    content = "\ufeff" + output.getvalue()

    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{maintenance_id}_arp.csv"'
        },
    )


@router.post("/arp/{maintenance_id}/import-csv")
async def import_arp_csv(
    maintenance_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """從 CSV 匯入 ARP 來源設備。"""
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    # 預先載入有效的設備 hostname（新設備 + 舊設備）
    valid_hostnames = await get_valid_all_hostnames(maintenance_id, session)

    imported = 0
    updated = 0
    errors = []

    for row_num, row in enumerate(reader, start=2):
        try:
            hostname = row.get("hostname", "").strip()
            priority_str = row.get("priority", "100").strip()
            description = row.get("description", "").strip() or None

            if not hostname:
                errors.append(f"Row {row_num}: hostname 為必填欄位")
                continue

            # 驗證 hostname 存在於設備清單（新設備或舊設備）
            if hostname not in valid_hostnames:
                errors.append(
                    f"Row {row_num}: 設備 '{hostname}' 不在設備清單中"
                )
                continue

            try:
                priority = int(priority_str) if priority_str else 100
            except ValueError:
                priority = 100

            # 檢查是否已存在（同一台設備只能有一筆）
            stmt = select(ArpSource).where(
                ArpSource.maintenance_id == maintenance_id,
                ArpSource.hostname == hostname,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                # 更新時檢查 priority 是否與其他記錄重複
                if priority != existing.priority:
                    priority_stmt = select(ArpSource).where(
                        ArpSource.maintenance_id == maintenance_id,
                        ArpSource.priority == priority,
                        ArpSource.id != existing.id,
                    )
                    priority_result = await session.execute(priority_stmt)
                    if priority_result.scalar_one_or_none():
                        errors.append(
                            f"Row {row_num}: 優先級 {priority} 已被其他設備使用"
                        )
                        continue

                existing.priority = priority
                existing.description = description
                updated += 1
            else:
                # 新增時檢查 priority 是否已存在
                priority_stmt = select(ArpSource).where(
                    ArpSource.maintenance_id == maintenance_id,
                    ArpSource.priority == priority,
                )
                priority_result = await session.execute(priority_stmt)
                if priority_result.scalar_one_or_none():
                    errors.append(
                        f"Row {row_num}: 優先級 {priority} 已被其他設備使用"
                    )
                    continue

                item = ArpSource(
                    maintenance_id=maintenance_id,
                    hostname=hostname,
                    priority=priority,
                    description=description,
                )
                session.add(item)
                imported += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")

    await session.commit()

    return {
        "imported": imported,
        "updated": updated,
        "total_errors": len(errors),
        "errors": errors[:10],
    }


# ========== Port-Channel Expectation Pydantic Models ==========

class PortChannelExpectationCreate(BaseModel):
    hostname: str
    port_channel: str
    member_interfaces: str  # 分號分隔的實體介面清單
    description: str | None = None


class PortChannelExpectationUpdate(BaseModel):
    hostname: str | None = None
    port_channel: str | None = None
    member_interfaces: str | None = None
    description: str | None = None


# ========== Port-Channel Expectations ==========

@router.get("/port-channel/{maintenance_id}")
async def list_port_channel_expectations(
    maintenance_id: str,
    search: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """列出 Port-Channel 期望。"""
    stmt = select(PortChannelExpectation).where(
        PortChannelExpectation.maintenance_id == maintenance_id
    )

    if search:
        from sqlalchemy import and_, or_
        keywords = search.strip().split()

        # 只匹配 hostname, port_channel, description（不跨欄匹配）
        field_conditions = []
        for field in [
            PortChannelExpectation.hostname,
            PortChannelExpectation.port_channel,
            PortChannelExpectation.description,
        ]:
            field_match = and_(*[field.ilike(f"%{kw}%") for kw in keywords])
            field_conditions.append(field_match)

        stmt = stmt.where(or_(*field_conditions))

    stmt = stmt.order_by(
        PortChannelExpectation.hostname,
        PortChannelExpectation.port_channel,
    )
    result = await session.execute(stmt)
    items = result.scalars().all()

    return {
        "total": len(items),
        "items": [
            {
                "id": item.id,
                "hostname": item.hostname,
                "port_channel": item.port_channel,
                "member_interfaces": item.member_interfaces,
                "member_interfaces_list": [
                    m.strip()
                    for m in item.member_interfaces.split(";")
                    if m.strip()
                ],
                "description": item.description,
            }
            for item in items
        ],
    }


@router.post("/port-channel/{maintenance_id}")
async def create_port_channel_expectation(
    maintenance_id: str,
    data: PortChannelExpectationCreate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """新增 Port-Channel 期望。"""
    hostname = data.hostname.strip()
    port_channel = data.port_channel.strip()

    # 驗證 hostname 存在於設備清單的新設備中
    await validate_hostname_in_device_list(maintenance_id, hostname, session, "設備")

    # 檢查是否已存在相同的 hostname + port_channel
    stmt = select(PortChannelExpectation).where(
        PortChannelExpectation.maintenance_id == maintenance_id,
        PortChannelExpectation.hostname == hostname,
        PortChannelExpectation.port_channel == port_channel,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"已存在相同的 Port-Channel 期望: {hostname}:{port_channel}"
        )
    
    # 標準化成員介面格式（移除空白）
    members = ";".join(
        m.strip()
        for m in data.member_interfaces.split(";")
        if m.strip()
    )

    item = PortChannelExpectation(
        maintenance_id=maintenance_id,
        hostname=hostname,
        port_channel=port_channel,
        member_interfaces=members,
        description=data.description.strip() if data.description else None,
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)

    return {
        "id": item.id,
        "hostname": item.hostname,
        "port_channel": item.port_channel,
        "member_interfaces": item.member_interfaces,
        "member_interfaces_list": item.member_interfaces.split(";"),
        "description": item.description,
    }


@router.put("/port-channel/{maintenance_id}/{item_id}")
async def update_port_channel_expectation(
    maintenance_id: str,
    item_id: int,
    data: PortChannelExpectationUpdate,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """更新 Port-Channel 期望。"""
    stmt = select(PortChannelExpectation).where(
        PortChannelExpectation.id == item_id,
        PortChannelExpectation.maintenance_id == maintenance_id,
    )
    result = await session.execute(stmt)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Port-Channel 期望不存在")

    # 計算更新後的 hostname 和 port_channel
    new_hostname = (
        data.hostname.strip() if data.hostname is not None else item.hostname
    )
    new_port_channel = (
        data.port_channel.strip()
        if data.port_channel is not None
        else item.port_channel
    )

    # 驗證變更的 hostname 存在於設備清單的新設備中
    if data.hostname is not None and new_hostname != item.hostname:
        await validate_hostname_in_device_list(
            maintenance_id, new_hostname, session, "設備"
        )

    # 檢查更新後是否會與其他記錄重複（排除自己）
    if data.hostname is not None or data.port_channel is not None:
        dup_stmt = select(PortChannelExpectation).where(
            PortChannelExpectation.maintenance_id == maintenance_id,
            PortChannelExpectation.hostname == new_hostname,
            PortChannelExpectation.port_channel == new_port_channel,
            PortChannelExpectation.id != item_id,
        )
        dup_result = await session.execute(dup_stmt)
        if dup_result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail=f"已存在相同的 Port-Channel 期望: "
                       f"{new_hostname}:{new_port_channel}"
            )

    if data.hostname is not None:
        item.hostname = data.hostname.strip()
    if data.port_channel is not None:
        item.port_channel = data.port_channel.strip()
    if data.member_interfaces is not None:
        members = ";".join(
            m.strip()
            for m in data.member_interfaces.split(";")
            if m.strip()
        )
        item.member_interfaces = members
    if data.description is not None:
        item.description = data.description.strip() if data.description else None

    await session.commit()
    await session.refresh(item)

    return {
        "id": item.id,
        "hostname": item.hostname,
        "port_channel": item.port_channel,
        "member_interfaces": item.member_interfaces,
        "member_interfaces_list": item.member_interfaces.split(";"),
        "description": item.description,
    }


@router.delete("/port-channel/{maintenance_id}/{item_id}")
async def delete_port_channel_expectation(
    maintenance_id: str,
    item_id: int,
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """刪除 Port-Channel 期望。"""
    stmt = select(PortChannelExpectation).where(
        PortChannelExpectation.id == item_id,
        PortChannelExpectation.maintenance_id == maintenance_id,
    )
    result = await session.execute(stmt)
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="Port-Channel 期望不存在")

    await session.delete(item)
    await session.commit()

    return {"status": "deleted"}


@router.post("/port-channel/{maintenance_id}/batch-delete")
async def batch_delete_port_channel_expectations(
    maintenance_id: str,
    item_ids: list[int],
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """批量刪除 Port Channel 期望。"""
    if not item_ids:
        return {
            "success": True,
            "deleted_count": 0,
            "message": "沒有選中任何項目",
        }

    stmt = delete(PortChannelExpectation).where(
        PortChannelExpectation.maintenance_id == maintenance_id,
        PortChannelExpectation.id.in_(item_ids),
    )
    result = await session.execute(stmt)
    await session.commit()

    return {
        "success": True,
        "deleted_count": result.rowcount,
        "message": f"已刪除 {result.rowcount} 筆 Port Channel 期望",
    }


@router.get("/port-channel/{maintenance_id}/export-csv")
async def export_port_channel_csv(
    maintenance_id: str,
    search: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    """匯出 Port Channel 期望為 CSV 文件。"""
    stmt = select(PortChannelExpectation).where(
        PortChannelExpectation.maintenance_id == maintenance_id
    )

    if search:
        from sqlalchemy import and_, or_
        keywords = search.strip().split()

        # 只匹配 hostname, port_channel, description（不跨欄匹配）
        field_conditions = []
        for field in [
            PortChannelExpectation.hostname,
            PortChannelExpectation.port_channel,
            PortChannelExpectation.description,
        ]:
            field_match = and_(*[field.ilike(f"%{kw}%") for kw in keywords])
            field_conditions.append(field_match)

        stmt = stmt.where(or_(*field_conditions))

    stmt = stmt.order_by(
        PortChannelExpectation.hostname,
        PortChannelExpectation.port_channel,
    )
    result = await session.execute(stmt)
    items = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["hostname", "port_channel", "member_interfaces", "description"])

    for item in items:
        writer.writerow([
            item.hostname,
            item.port_channel,
            item.member_interfaces,
            item.description or "",
        ])

    output.seek(0)
    content = "\ufeff" + output.getvalue()

    return StreamingResponse(
        iter([content.encode("utf-8")]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{maintenance_id}_port_channel.csv"'
        },
    )


@router.post("/port-channel/{maintenance_id}/import-csv")
async def import_port_channel_csv(
    maintenance_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """從 CSV 匯入 Port-Channel 期望。"""
    content = await file.read()
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    # 預先載入有效的新設備 hostname
    valid_hostnames = await get_valid_new_hostnames(maintenance_id, session)

    imported = 0
    updated = 0
    errors = []

    for row_num, row in enumerate(reader, start=2):
        try:
            hostname = row.get("hostname", "").strip()
            port_channel = row.get("port_channel", "").strip()
            member_interfaces = row.get("member_interfaces", "").strip()
            description = row.get("description", "").strip() or None

            if not hostname or not port_channel or not member_interfaces:
                errors.append(f"Row {row_num}: 必填欄位不完整")
                continue

            # 驗證 hostname 存在於設備清單的新設備中
            if hostname not in valid_hostnames:
                errors.append(
                    f"Row {row_num}: 設備 '{hostname}' 不在設備清單的新設備中"
                )
                continue

            # 標準化成員介面格式
            members = ";".join(
                m.strip()
                for m in member_interfaces.split(";")
                if m.strip()
            )

            # 檢查是否已存在
            stmt = select(PortChannelExpectation).where(
                PortChannelExpectation.maintenance_id == maintenance_id,
                PortChannelExpectation.hostname == hostname,
                PortChannelExpectation.port_channel == port_channel,
            )
            result = await session.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                existing.member_interfaces = members
                existing.description = description
                updated += 1
            else:
                item = PortChannelExpectation(
                    maintenance_id=maintenance_id,
                    hostname=hostname,
                    port_channel=port_channel,
                    member_interfaces=members,
                    description=description,
                )
                session.add(item)
                imported += 1
        except Exception as e:
            errors.append(f"Row {row_num}: {str(e)}")

    await session.commit()

    return {
        "imported": imported,
        "updated": updated,
        "total_errors": len(errors),
        "errors": errors[:10],
    }
