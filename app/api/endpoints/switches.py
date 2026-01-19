"""
Switch API endpoints.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.base import get_async_session
from app.db.models import Switch, Interface
from app.schemas.switch import (
    SwitchCreate,
    SwitchUpdate,
    SwitchResponse,
    SwitchDetailResponse,
    SwitchListResponse,
    InterfaceResponse,
)

router = APIRouter()


@router.get("", response_model=SwitchListResponse)
async def list_switches(
    page: int = Query(1, ge=1, description="頁碼"),
    page_size: int = Query(20, ge=1, le=100, description="每頁數量"),
    vendor: Optional[str] = Query(None, description="篩選廠牌"),
    is_active: Optional[bool] = Query(None, description="篩選啟用狀態"),
    session: AsyncSession = Depends(get_async_session),
) -> SwitchListResponse:
    """
    取得 Switch 列表。
    
    支援分頁和篩選。
    """
    # 建立查詢
    query = select(Switch)
    count_query = select(func.count(Switch.id))
    
    # 套用篩選條件
    if vendor:
        query = query.where(Switch.vendor == vendor)
        count_query = count_query.where(Switch.vendor == vendor)
    
    if is_active is not None:
        query = query.where(Switch.is_active == is_active)
        count_query = count_query.where(Switch.is_active == is_active)
    
    # 計算總數
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分頁
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size).order_by(Switch.hostname)
    
    # 執行查詢
    result = await session.execute(query)
    switches = result.scalars().all()
    
    # 取得每個 switch 的 interface 數量
    items = []
    for switch in switches:
        intf_count_query = select(func.count(Interface.id)).where(
            Interface.switch_id == switch.id
        )
        intf_result = await session.execute(intf_count_query)
        intf_count = intf_result.scalar() or 0
        
        item = SwitchResponse.model_validate(switch)
        item.interface_count = intf_count
        items.append(item)
    
    return SwitchListResponse(
        total=total,
        items=items,
        page=page,
        page_size=page_size,
    )


@router.get("/{switch_id}", response_model=SwitchDetailResponse)
async def get_switch(
    switch_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> SwitchDetailResponse:
    """
    取得單一 Switch 詳細資訊（包含介面列表）。
    """
    query = (
        select(Switch)
        .where(Switch.id == switch_id)
        .options(selectinload(Switch.interfaces))
    )
    result = await session.execute(query)
    switch = result.scalar_one_or_none()
    
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")
    
    response = SwitchDetailResponse.model_validate(switch)
    response.interface_count = len(switch.interfaces)
    response.interfaces = [
        InterfaceResponse.model_validate(intf) for intf in switch.interfaces
    ]
    
    return response


@router.post("", response_model=SwitchResponse, status_code=201)
async def create_switch(
    data: SwitchCreate,
    session: AsyncSession = Depends(get_async_session),
) -> SwitchResponse:
    """
    建立新的 Switch。
    """
    # 檢查 hostname 是否重複
    existing = await session.execute(
        select(Switch).where(Switch.hostname == data.hostname)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Switch with hostname '{data.hostname}' already exists"
        )
    
    switch = Switch(**data.model_dump())
    session.add(switch)
    await session.flush()
    await session.refresh(switch)
    
    return SwitchResponse.model_validate(switch)


@router.patch("/{switch_id}", response_model=SwitchResponse)
async def update_switch(
    switch_id: int,
    data: SwitchUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> SwitchResponse:
    """
    更新 Switch 資訊。
    """
    result = await session.execute(
        select(Switch).where(Switch.id == switch_id)
    )
    switch = result.scalar_one_or_none()
    
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")
    
    # 只更新有提供的欄位
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(switch, field, value)
    
    await session.flush()
    await session.refresh(switch)
    
    return SwitchResponse.model_validate(switch)


@router.delete("/{switch_id}", status_code=204)
async def delete_switch(
    switch_id: int,
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """
    刪除 Switch。
    """
    result = await session.execute(
        select(Switch).where(Switch.id == switch_id)
    )
    switch = result.scalar_one_or_none()
    
    if not switch:
        raise HTTPException(status_code=404, detail="Switch not found")
    
    await session.delete(switch)


@router.get("/{switch_id}/interfaces", response_model=list[InterfaceResponse])
async def get_switch_interfaces(
    switch_id: int,
    has_transceiver: Optional[bool] = Query(None),
    session: AsyncSession = Depends(get_async_session),
) -> list[InterfaceResponse]:
    """
    取得 Switch 的所有介面。
    """
    # 確認 Switch 存在
    switch_result = await session.execute(
        select(Switch).where(Switch.id == switch_id)
    )
    if not switch_result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Switch not found")
    
    # 查詢介面
    query = select(Interface).where(Interface.switch_id == switch_id)
    
    if has_transceiver is not None:
        query = query.where(Interface.has_transceiver == has_transceiver)
    
    result = await session.execute(query.order_by(Interface.name))
    interfaces = result.scalars().all()
    
    return [InterfaceResponse.model_validate(intf) for intf in interfaces]
