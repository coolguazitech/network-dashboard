"""
Device mapping endpoints.

Switch 新舊設備對應關係的 API 端點。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
import csv
import io

from app.db.base import get_async_session
from app.db.models import DeviceMapping


router = APIRouter(
    prefix="/device-mappings",
    tags=["device-mappings"],
)


# 廠商選項常數
VENDOR_OPTIONS = ["HPE", "Cisco-IOS", "Cisco-NXOS"]


class DeviceMappingCreate(BaseModel):
    """創建設備對應關係的請求模型。"""
    maintenance_id: str
    old_hostname: str
    new_hostname: str
    vendor: str  # 必填：HPE, Cisco-IOS, Cisco-NXOS
    use_same_port: bool = True  # 預設啟用同名port對應
    mapping_config: dict[str, Any] | None = None


class DeviceMappingUpdate(BaseModel):
    """更新設備對應關係的請求模型。"""
    old_hostname: str | None = None
    new_hostname: str | None = None
    vendor: str | None = None  # HPE, Cisco-IOS, Cisco-NXOS
    use_same_port: bool | None = None
    mapping_config: dict[str, Any] | None = None


@router.get("/vendor-options")
async def get_vendor_options() -> dict[str, Any]:
    """
    取得廠商選項列表。
    """
    return {
        "success": True,
        "options": VENDOR_OPTIONS,
    }


@router.get("/{maintenance_id}")
async def list_device_mappings(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    列出指定歲修 ID 的所有設備對應關係。
    """
    stmt = (
        select(DeviceMapping)
        .where(DeviceMapping.maintenance_id == maintenance_id)
        .order_by(DeviceMapping.old_hostname)
    )
    result = await session.execute(stmt)
    mappings = result.scalars().all()
    
    return {
        "success": True,
        "maintenance_id": maintenance_id,
        "count": len(mappings),
        "mappings": [
            {
                "id": m.id,
                "old_hostname": m.old_hostname,
                "new_hostname": m.new_hostname,
                "vendor": m.vendor,
                "use_same_port": m.use_same_port,
                "mapping_config": m.mapping_config,
                "created_at": (m.created_at.isoformat()
                              if m.created_at else None),
            }
            for m in mappings
        ],
    }


@router.post("/{maintenance_id}")
async def create_device_mapping(
    maintenance_id: str,
    data: DeviceMappingCreate,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    創建新的設備對應關係。
    
    設備對應必須是一對一：
    - 同一個 old_hostname 不能對應到多個 new_hostname
    - 同一個 new_hostname 不能被多個 old_hostname 對應
    """
    from sqlalchemy import or_
    
    # 檢查是否已存在相同的對應關係（雙向檢查）
    stmt = select(DeviceMapping).where(
        DeviceMapping.maintenance_id == maintenance_id,
        or_(
            DeviceMapping.old_hostname == data.old_hostname,
            DeviceMapping.new_hostname == data.new_hostname,
            # 也檢查是否互相引用（例如 A→B 後又新增 B→A）
            DeviceMapping.old_hostname == data.new_hostname,
            DeviceMapping.new_hostname == data.old_hostname,
        )
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    
    if existing:
        if existing.old_hostname == data.old_hostname:
            raise HTTPException(
                status_code=400,
                detail=f"舊設備 {data.old_hostname} 已有對應關係",
            )
        elif existing.new_hostname == data.new_hostname:
            raise HTTPException(
                status_code=400,
                detail=f"新設備 {data.new_hostname} 已被其他設備對應",
            )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"設備 {data.old_hostname} 或 {data.new_hostname} "
                       f"已存在於其他對應關係中",
            )
    
    mapping = DeviceMapping(
        maintenance_id=maintenance_id,
        old_hostname=data.old_hostname,
        new_hostname=data.new_hostname,
        vendor=data.vendor,
        use_same_port=data.use_same_port,
        mapping_config=data.mapping_config,
    )
    session.add(mapping)
    await session.commit()
    await session.refresh(mapping)
    
    return {
        "success": True,
        "message": "設備對應關係已創建",
        "mapping": {
            "id": mapping.id,
            "old_hostname": mapping.old_hostname,
            "new_hostname": mapping.new_hostname,
            "vendor": mapping.vendor,
            "use_same_port": mapping.use_same_port,
            "mapping_config": mapping.mapping_config,
            "created_at": (mapping.created_at.isoformat()
                           if mapping.created_at else None),
        },
    }


@router.put("/{maintenance_id}/{mapping_id}")
async def update_device_mapping(
    maintenance_id: str,
    mapping_id: int,
    data: DeviceMappingUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    更新設備對應關係。
    """
    stmt = select(DeviceMapping).where(
        DeviceMapping.id == mapping_id,
        DeviceMapping.maintenance_id == maintenance_id,
    )
    result = await session.execute(stmt)
    mapping = result.scalar_one_or_none()
    
    if not mapping:
        raise HTTPException(
            status_code=404,
            detail="找不到指定的設備對應關係",
        )
    
    from sqlalchemy import or_
    
    # 檢查唯一性（一對一對應）
    check_conditions = []
    if data.old_hostname and data.old_hostname != mapping.old_hostname:
        check_conditions.append(
            DeviceMapping.old_hostname == data.old_hostname
        )
        check_conditions.append(
            DeviceMapping.new_hostname == data.old_hostname
        )
    if data.new_hostname and data.new_hostname != mapping.new_hostname:
        check_conditions.append(
            DeviceMapping.new_hostname == data.new_hostname
        )
        check_conditions.append(
            DeviceMapping.old_hostname == data.new_hostname
        )
    
    if check_conditions:
        check_stmt = select(DeviceMapping).where(
            DeviceMapping.maintenance_id == maintenance_id,
            DeviceMapping.id != mapping_id,
            or_(*check_conditions),
        )
        check_result = await session.execute(check_stmt)
        conflict = check_result.scalar_one_or_none()
        if conflict:
            raise HTTPException(
                status_code=400,
                detail="更新後的設備名稱與其他對應關係衝突",
            )
    
    if data.old_hostname is not None:
        mapping.old_hostname = data.old_hostname
    if data.new_hostname is not None:
        mapping.new_hostname = data.new_hostname
    if data.vendor is not None:
        mapping.vendor = data.vendor
    if data.use_same_port is not None:
        mapping.use_same_port = data.use_same_port
    if data.mapping_config is not None:
        mapping.mapping_config = data.mapping_config
    
    await session.commit()
    await session.refresh(mapping)
    
    return {
        "success": True,
        "message": "設備對應關係已更新",
        "mapping": {
            "id": mapping.id,
            "old_hostname": mapping.old_hostname,
            "new_hostname": mapping.new_hostname,
            "vendor": mapping.vendor,
            "use_same_port": mapping.use_same_port,
            "mapping_config": mapping.mapping_config,
            "created_at": (mapping.created_at.isoformat()
                           if mapping.created_at else None),
        },
    }


@router.delete("/{maintenance_id}/{mapping_id}")
async def delete_device_mapping(
    maintenance_id: str,
    mapping_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    刪除設備對應關係。
    """
    stmt = select(DeviceMapping).where(
        DeviceMapping.id == mapping_id,
        DeviceMapping.maintenance_id == maintenance_id,
    )
    result = await session.execute(stmt)
    mapping = result.scalar_one_or_none()
    
    if not mapping:
        raise HTTPException(
            status_code=404,
            detail="找不到指定的設備對應關係",
        )
    
    await session.delete(mapping)
    await session.commit()
    
    return {
        "success": True,
        "message": "設備對應關係已刪除",
    }


@router.post("/{maintenance_id}/import-csv")
async def import_device_mappings_csv(
    maintenance_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    從 CSV 文件導入設備對應關係。
    
    CSV 格式：old_hostname,new_hostname,vendor,use_same_port
    - vendor: 必填，HPE / Cisco-IOS / Cisco-NXOS
    - use_same_port: 選填，true/false（預設 true）
    """
    if not file.filename or not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=400,
            detail="請上傳 CSV 文件",
        )
    
    content = await file.read()
    
    # 嘗試解碼
    try:
        text = content.decode('utf-8-sig')  # 支持 BOM
    except UnicodeDecodeError:
        try:
            text = content.decode('gbk')
        except UnicodeDecodeError:
            text = content.decode('utf-8', errors='ignore')
    
    reader = csv.DictReader(io.StringIO(text))
    
    imported = 0
    updated = 0
    errors = []
    
    for row_num, row in enumerate(reader, start=2):
        old_hostname = row.get('old_hostname', '').strip()
        new_hostname = row.get('new_hostname', '').strip()
        vendor = row.get('vendor', '').strip()
        use_same_port_str = row.get('use_same_port', 'true').strip().lower()
        
        # 驗證必填欄位
        if not old_hostname or not new_hostname:
            errors.append(f"第 {row_num} 行：缺少 hostname 欄位")
            continue
        
        if not vendor:
            errors.append(f"第 {row_num} 行：缺少 vendor 欄位")
            continue
        
        if vendor not in VENDOR_OPTIONS:
            errors.append(
                f"第 {row_num} 行：vendor 必須是 "
                f"{', '.join(VENDOR_OPTIONS)} 其中之一"
            )
            continue
        
        # 解析 use_same_port
        use_same_port = use_same_port_str in ('true', '1', 'yes', 't')
        
        # 檢查是否已存在
        stmt = select(DeviceMapping).where(
            DeviceMapping.maintenance_id == maintenance_id,
            DeviceMapping.old_hostname == old_hostname,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            # 更新現有記錄
            existing.new_hostname = new_hostname
            existing.vendor = vendor
            existing.use_same_port = use_same_port
            updated += 1
        else:
            # 創建新記錄
            mapping = DeviceMapping(
                maintenance_id=maintenance_id,
                old_hostname=old_hostname,
                new_hostname=new_hostname,
                vendor=vendor,
                use_same_port=use_same_port,
            )
            session.add(mapping)
            imported += 1
    
    await session.commit()
    
    return {
        "success": True,
        "imported": imported,
        "updated": updated,
        "total_errors": len(errors),
        "errors": errors[:10],  # 只返回前 10 個錯誤
    }


@router.delete("/{maintenance_id}")
async def clear_device_mappings(
    maintenance_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    清除指定歲修 ID 的所有設備對應關係。
    """
    stmt = delete(DeviceMapping).where(
        DeviceMapping.maintenance_id == maintenance_id
    )
    result = await session.execute(stmt)
    await session.commit()
    
    return {
        "success": True,
        "message": f"已刪除 {result.rowcount} 筆設備對應關係",
        "deleted_count": result.rowcount,
    }
