"""
Switches API endpoints.

提供交換機設備的 CRUD 管理功能（需要寫入權限）。
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.endpoints.auth import get_current_user, require_root, require_write
from app.db.base import get_async_session
from app.db.models import Switch
from app.services.system_log import write_log

router = APIRouter(prefix="/switches", tags=["Switches"])


# ── Request Models ──────────────────────────────────────────


class SwitchCreate(BaseModel):
    """新增交換機請求。"""

    hostname: str
    ip_address: str
    vendor: str
    platform: str
    site: str | None = None
    model: str | None = None
    location: str | None = None
    description: str | None = None
    is_active: bool = True


class SwitchUpdate(BaseModel):
    """更新交換機請求。"""

    hostname: str | None = None
    ip_address: str | None = None
    vendor: str | None = None
    platform: str | None = None
    site: str | None = None
    model: str | None = None
    location: str | None = None
    description: str | None = None
    is_active: bool | None = None


# ── Serialization ───────────────────────────────────────────


def _serialize_switch(sw: Switch) -> dict[str, Any]:
    """序列化交換機為 dict。"""
    return {
        "id": sw.id,
        "hostname": sw.hostname,
        "ip_address": sw.ip_address,
        "vendor": sw.vendor,
        "platform": sw.platform,
        "site": sw.site,
        "model": sw.model,
        "location": sw.location,
        "description": sw.description,
        "is_active": bool(sw.is_active),
        "created_at": sw.created_at.isoformat() if sw.created_at else None,
        "updated_at": sw.updated_at.isoformat() if sw.updated_at else None,
    }


# ── Endpoints ───────────────────────────────────────────────


@router.get("")
async def list_switches(
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """列出所有交換機。"""
    stmt = select(Switch).order_by(Switch.hostname)
    result = await session.execute(stmt)
    switches = result.scalars().all()

    return {
        "data": [_serialize_switch(sw) for sw in switches],
        "total": len(switches),
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_switch(
    data: SwitchCreate,
    user: Annotated[dict[str, Any], Depends(require_write())],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """新增交換機。需要寫入權限。"""
    # 檢查 hostname 唯一性
    existing = await session.execute(
        select(Switch).where(Switch.hostname == data.hostname)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"主機名稱 {data.hostname} 已存在",
        )

    # 檢查 IP 唯一性
    existing_ip = await session.execute(
        select(Switch).where(Switch.ip_address == data.ip_address)
    )
    if existing_ip.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"IP 位址 {data.ip_address} 已存在",
        )

    switch = Switch(
        hostname=data.hostname.strip(),
        ip_address=data.ip_address.strip(),
        vendor=data.vendor.strip(),
        platform=data.platform.strip(),
        site=data.site.strip() if data.site else None,
        model=data.model.strip() if data.model else None,
        location=data.location.strip() if data.location else None,
        description=data.description.strip() if data.description else None,
        is_active=data.is_active,
    )
    session.add(switch)
    await session.commit()
    await session.refresh(switch)

    await write_log(
        level="INFO",
        source="api",
        summary=f"新增交換機: {switch.hostname}",
        module="switches",
        user_id=user.get("user_id"),
        username=user.get("username"),
    )

    return {
        "success": True,
        "message": "交換機已新增",
        "data": _serialize_switch(switch),
    }


@router.put("/{switch_id}")
async def update_switch(
    switch_id: int,
    data: SwitchUpdate,
    user: Annotated[dict[str, Any], Depends(require_write())],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """更新交換機。需要寫入權限。"""
    result = await session.execute(
        select(Switch).where(Switch.id == switch_id)
    )
    switch = result.scalar_one_or_none()
    if not switch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到指定的交換機",
        )

    # 更新欄位
    if data.hostname is not None:
        # 檢查 hostname 唯一性
        dup = await session.execute(
            select(Switch).where(
                Switch.hostname == data.hostname,
                Switch.id != switch_id,
            )
        )
        if dup.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"主機名稱 {data.hostname} 已存在",
            )
        switch.hostname = data.hostname.strip()

    if data.ip_address is not None:
        dup_ip = await session.execute(
            select(Switch).where(
                Switch.ip_address == data.ip_address,
                Switch.id != switch_id,
            )
        )
        if dup_ip.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"IP 位址 {data.ip_address} 已存在",
            )
        switch.ip_address = data.ip_address.strip()

    if data.vendor is not None:
        switch.vendor = data.vendor.strip()
    if data.platform is not None:
        switch.platform = data.platform.strip()
    if data.site is not None:
        switch.site = data.site.strip() if data.site else None
    if data.model is not None:
        switch.model = data.model.strip() if data.model else None
    if data.location is not None:
        switch.location = data.location.strip() if data.location else None
    if data.description is not None:
        switch.description = data.description.strip() if data.description else None
    if data.is_active is not None:
        switch.is_active = data.is_active

    await session.commit()
    await session.refresh(switch)

    await write_log(
        level="INFO",
        source="api",
        summary=f"更新交換機: {switch.hostname}",
        module="switches",
        user_id=user.get("user_id"),
        username=user.get("username"),
    )

    return {
        "success": True,
        "message": "交換機已更新",
        "data": _serialize_switch(switch),
    }


@router.delete("/{switch_id}")
async def delete_switch(
    switch_id: int,
    user: Annotated[dict[str, Any], Depends(require_write())],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """刪除交換機。需要寫入權限。"""
    result = await session.execute(
        select(Switch).where(Switch.id == switch_id)
    )
    switch = result.scalar_one_or_none()
    if not switch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到指定的交換機",
        )

    hostname = switch.hostname
    await session.delete(switch)
    await session.commit()

    await write_log(
        level="WARNING",
        source="api",
        summary=f"刪除交換機: {hostname}",
        module="switches",
        user_id=user.get("user_id"),
        username=user.get("username"),
    )

    return {
        "success": True,
        "message": "交換機已刪除",
    }
