"""
Interface mapping endpoints.

連接埠對應關係的 API 端點。
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
from app.db.models import InterfaceMapping


router = APIRouter(
    prefix="/interface-mappings",
    tags=["interface-mappings"],
)


class InterfaceMappingCreate(BaseModel):
    """創建連接埠對應關係的請求模型。"""
    maintenance_id: str
    old_hostname: str
    old_interface: str
    new_hostname: str
    new_interface: str
    description: str | None = None


class InterfaceMappingUpdate(BaseModel):
    """更新連接埠對應關係的請求模型。"""
    old_hostname: str | None = None
    old_interface: str | None = None
    new_hostname: str | None = None
    new_interface: str | None = None
    description: str | None = None


@router.get("/{maintenance_id}")
async def list_interface_mappings(
    maintenance_id: str,
    old_hostname: str | None = None,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    列出指定歲修 ID 的所有連接埠對應關係。
    可選擇按舊設備 hostname 篩選。
    """
    stmt = (
        select(InterfaceMapping)
        .where(InterfaceMapping.maintenance_id == maintenance_id)
    )
    
    if old_hostname:
        stmt = stmt.where(InterfaceMapping.old_hostname == old_hostname)
    
    stmt = stmt.order_by(
        InterfaceMapping.old_hostname,
        InterfaceMapping.old_interface,
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
                "old_interface": m.old_interface,
                "new_hostname": m.new_hostname,
                "new_interface": m.new_interface,
                "description": m.description,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in mappings
        ],
    }


@router.post("/{maintenance_id}")
async def create_interface_mapping(
    maintenance_id: str,
    data: InterfaceMappingCreate,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    創建新的連接埠對應關係。
    """
    # 檢查是否已存在相同的對應關係
    stmt = select(InterfaceMapping).where(
        InterfaceMapping.maintenance_id == maintenance_id,
        InterfaceMapping.old_hostname == data.old_hostname,
        InterfaceMapping.old_interface == data.old_interface,
    )
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"連接埠 {data.old_hostname}:{data.old_interface} 的對應關係已存在",
        )
    
    mapping = InterfaceMapping(
        maintenance_id=maintenance_id,
        old_hostname=data.old_hostname,
        old_interface=data.old_interface,
        new_hostname=data.new_hostname,
        new_interface=data.new_interface,
        description=data.description,
    )
    session.add(mapping)
    await session.commit()
    await session.refresh(mapping)
    
    return {
        "success": True,
        "message": "連接埠對應關係已創建",
        "mapping": {
            "id": mapping.id,
            "old_hostname": mapping.old_hostname,
            "old_interface": mapping.old_interface,
            "new_hostname": mapping.new_hostname,
            "new_interface": mapping.new_interface,
            "description": mapping.description,
            "created_at": mapping.created_at.isoformat() if mapping.created_at else None,
        },
    }


@router.put("/{maintenance_id}/{mapping_id}")
async def update_interface_mapping(
    maintenance_id: str,
    mapping_id: int,
    data: InterfaceMappingUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    更新連接埠對應關係。
    """
    stmt = select(InterfaceMapping).where(
        InterfaceMapping.id == mapping_id,
        InterfaceMapping.maintenance_id == maintenance_id,
    )
    result = await session.execute(stmt)
    mapping = result.scalar_one_or_none()
    
    if not mapping:
        raise HTTPException(
            status_code=404,
            detail="找不到指定的連接埠對應關係",
        )
    
    if data.old_hostname is not None:
        mapping.old_hostname = data.old_hostname
    if data.old_interface is not None:
        mapping.old_interface = data.old_interface
    if data.new_hostname is not None:
        mapping.new_hostname = data.new_hostname
    if data.new_interface is not None:
        mapping.new_interface = data.new_interface
    if data.description is not None:
        mapping.description = data.description
    
    await session.commit()
    await session.refresh(mapping)
    
    return {
        "success": True,
        "message": "連接埠對應關係已更新",
        "mapping": {
            "id": mapping.id,
            "old_hostname": mapping.old_hostname,
            "old_interface": mapping.old_interface,
            "new_hostname": mapping.new_hostname,
            "new_interface": mapping.new_interface,
            "description": mapping.description,
            "created_at": mapping.created_at.isoformat() if mapping.created_at else None,
        },
    }


@router.delete("/{maintenance_id}/{mapping_id}")
async def delete_interface_mapping(
    maintenance_id: str,
    mapping_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    刪除連接埠對應關係。
    """
    stmt = select(InterfaceMapping).where(
        InterfaceMapping.id == mapping_id,
        InterfaceMapping.maintenance_id == maintenance_id,
    )
    result = await session.execute(stmt)
    mapping = result.scalar_one_or_none()
    
    if not mapping:
        raise HTTPException(
            status_code=404,
            detail="找不到指定的連接埠對應關係",
        )
    
    await session.delete(mapping)
    await session.commit()
    
    return {
        "success": True,
        "message": "連接埠對應關係已刪除",
    }


@router.post("/{maintenance_id}/import-csv")
async def import_interface_mappings_csv(
    maintenance_id: str,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    從 CSV 文件導入連接埠對應關係。
    
    CSV 格式：old_hostname,old_interface,new_hostname,new_interface,description
    """
    if not file.filename or not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=400,
            detail="請上傳 CSV 文件",
        )
    
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
    
    imported = 0
    updated = 0
    errors = []
    
    for row_num, row in enumerate(reader, start=2):
        old_hostname = row.get('old_hostname', '').strip()
        old_interface = row.get('old_interface', '').strip()
        new_hostname = row.get('new_hostname', '').strip()
        new_interface = row.get('new_interface', '').strip()
        description = row.get('description', '').strip() or None
        
        if not old_hostname or not old_interface or not new_hostname or not new_interface:
            errors.append(f"第 {row_num} 行：缺少必要欄位")
            continue
        
        # 檢查是否已存在
        stmt = select(InterfaceMapping).where(
            InterfaceMapping.maintenance_id == maintenance_id,
            InterfaceMapping.old_hostname == old_hostname,
            InterfaceMapping.old_interface == old_interface,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            # 更新現有記錄
            existing.new_hostname = new_hostname
            existing.new_interface = new_interface
            existing.description = description
            updated += 1
        else:
            # 創建新記錄
            mapping = InterfaceMapping(
                maintenance_id=maintenance_id,
                old_hostname=old_hostname,
                old_interface=old_interface,
                new_hostname=new_hostname,
                new_interface=new_interface,
                description=description,
            )
            session.add(mapping)
            imported += 1
    
    await session.commit()
    
    return {
        "success": True,
        "imported": imported,
        "updated": updated,
        "total_errors": len(errors),
        "errors": errors[:10],
    }


@router.delete("/{maintenance_id}")
async def clear_interface_mappings(
    maintenance_id: str,
    old_hostname: str | None = None,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    清除連接埠對應關係。
    如果提供 old_hostname，只清除該設備的對應關係。
    """
    stmt = delete(InterfaceMapping).where(
        InterfaceMapping.maintenance_id == maintenance_id
    )
    
    if old_hostname:
        stmt = stmt.where(InterfaceMapping.old_hostname == old_hostname)
    
    result = await session.execute(stmt)
    await session.commit()
    
    return {
        "success": True,
        "message": f"已刪除 {result.rowcount} 筆連接埠對應關係",
        "deleted_count": result.rowcount,
    }
