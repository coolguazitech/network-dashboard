"""
Meal Delivery Status API endpoints.

餐點到達通知功能的 API 端點。
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.api.endpoints.auth import get_current_user
from app.core.enums import MealDeliveryStatus
from app.core.timezone import now_utc
from app.db.base import get_session_context
from app.db.models import MealZone
from app.services.system_log import write_log

router = APIRouter(prefix="/meals", tags=["Meals"])

# 預設區域配置
DEFAULT_ZONES = [
    {"zone_code": "HSP", "zone_name": "竹科", "icon": "&#127843;"},  # 飯糰
    {"zone_code": "CSP", "zone_name": "中科", "icon": "&#127834;"},  # 碗
    {"zone_code": "SSP", "zone_name": "南科", "icon": "&#127835;"},  # 便當
]


class MealStatusUpdate(BaseModel):
    """更新餐點狀態請求。"""

    status: str  # no_meal, pending, arrived
    expected_time: str | None = None  # ISO format
    meal_count: int | None = None
    notes: str | None = None


class MealZoneResponse(BaseModel):
    """區域餐點狀態回應。"""

    zone_code: str
    zone_name: str
    icon: str
    status: str
    status_text: str
    expected_time: str | None
    arrived_time: str | None
    meal_count: int
    notes: str | None
    updated_at: str | None


@router.get("/{maintenance_id}")
async def get_meal_status(
    maintenance_id: str,
    _user: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    """獲取所有區域的餐點狀態。"""
    async with get_session_context() as session:
        stmt = select(MealZone).where(MealZone.maintenance_id == maintenance_id)
        result = await session.execute(stmt)
        zones = {z.zone_code: z for z in result.scalars().all()}

        # 確保所有區域都有記錄
        zones_list = []
        for zone_config in DEFAULT_ZONES:
            zone = zones.get(zone_config["zone_code"])

            if zone:
                status_text = {
                    MealDeliveryStatus.NO_MEAL: "今日無便當",
                    MealDeliveryStatus.PENDING: "等待中...",
                    MealDeliveryStatus.ARRIVED: "已送達!",
                }.get(zone.status, "")

                zones_list.append(
                    {
                        "zone_code": zone.zone_code,
                        "zone_name": zone.zone_name,
                        "icon": zone_config["icon"],
                        "status": zone.status.value,
                        "status_text": status_text,
                        "expected_time": (
                            zone.expected_time.isoformat()
                            if zone.expected_time
                            else None
                        ),
                        "arrived_time": (
                            zone.arrived_time.isoformat()
                            if zone.arrived_time
                            else None
                        ),
                        "meal_count": zone.meal_count,
                        "notes": zone.notes,
                        "updated_at": (
                            zone.updated_at.isoformat() if zone.updated_at else None
                        ),
                    }
                )
            else:
                # 預設狀態
                zones_list.append(
                    {
                        "zone_code": zone_config["zone_code"],
                        "zone_name": zone_config["zone_name"],
                        "icon": zone_config["icon"],
                        "status": "no_meal",
                        "status_text": "今日無便當",
                        "expected_time": None,
                        "arrived_time": None,
                        "meal_count": 0,
                        "notes": None,
                        "updated_at": None,
                    }
                )

        return {"zones": zones_list}


@router.put("/{maintenance_id}/{zone_code}", response_model=MealZoneResponse)
async def update_meal_status(
    maintenance_id: str,
    zone_code: str,
    data: MealStatusUpdate,
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    """更新區域餐點狀態。"""
    # 驗證區域代碼
    zone_config = next(
        (z for z in DEFAULT_ZONES if z["zone_code"] == zone_code), None
    )
    if not zone_config:
        raise HTTPException(status_code=400, detail=f"無效的區域代碼: {zone_code}")

    async with get_session_context() as session:
        stmt = select(MealZone).where(
            MealZone.maintenance_id == maintenance_id,
            MealZone.zone_code == zone_code,
        )
        result = await session.execute(stmt)
        zone = result.scalar_one_or_none()

        # 如果不存在則創建
        if not zone:
            zone = MealZone(
                maintenance_id=maintenance_id,
                zone_code=zone_code,
                zone_name=zone_config["zone_name"],
                meal_count=0,
            )
            session.add(zone)

        # 更新狀態（接受大小寫：前端送 lowercase，enum 為 uppercase）
        try:
            new_status = MealDeliveryStatus(data.status.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"無效的狀態: {data.status}")
        zone.status = new_status

        # 更新到達時間
        if new_status == MealDeliveryStatus.ARRIVED:
            zone.arrived_time = now_utc()
        elif new_status == MealDeliveryStatus.PENDING:
            zone.arrived_time = None

        # 更新其他欄位
        if data.expected_time:
            zone.expected_time = datetime.fromisoformat(
                data.expected_time.replace("Z", "+00:00")
            )
        if data.meal_count is not None:
            zone.meal_count = data.meal_count
        if data.notes is not None:
            zone.notes = data.notes

        await session.commit()
        await session.refresh(zone)

        await write_log(
            level="INFO",
            source="api",
            summary=f"更新餐點狀態: {zone_code} → {data.status}",
            module="meals",
            maintenance_id=maintenance_id,
        )

        status_text = {
            MealDeliveryStatus.NO_MEAL: "今日無便當",
            MealDeliveryStatus.PENDING: "等待中...",
            MealDeliveryStatus.ARRIVED: "已送達!",
        }.get(zone.status, "")

        return {
            "zone_code": zone.zone_code,
            "zone_name": zone.zone_name,
            "icon": zone_config["icon"],
            "status": zone.status.value,
            "status_text": status_text,
            "expected_time": (
                zone.expected_time.isoformat() if zone.expected_time else None
            ),
            "arrived_time": (
                zone.arrived_time.isoformat() if zone.arrived_time else None
            ),
            "meal_count": zone.meal_count,
            "notes": zone.notes,
            "updated_at": zone.updated_at.isoformat() if zone.updated_at else None,
        }


@router.post("/{maintenance_id}/reset")
async def reset_meal_status(
    maintenance_id: str,
    _: Annotated[dict[str, Any], Depends(get_current_user)],
) -> dict[str, Any]:
    """重置所有區域的餐點狀態（用於新的一天）。"""
    async with get_session_context() as session:
        stmt = select(MealZone).where(MealZone.maintenance_id == maintenance_id)
        result = await session.execute(stmt)
        zones = result.scalars().all()

        for zone in zones:
            zone.status = MealDeliveryStatus.NO_MEAL
            zone.expected_time = None
            zone.arrived_time = None
            zone.meal_count = 0
            zone.notes = None

        await session.commit()

        await write_log(
            level="WARNING",
            source="api",
            summary="重置所有餐點狀態",
            module="meals",
            maintenance_id=maintenance_id,
        )

        # 回傳重置後的狀態
        zones_list = []
        for zone_config in DEFAULT_ZONES:
            zones_list.append(
                {
                    "zone_code": zone_config["zone_code"],
                    "zone_name": zone_config["zone_name"],
                    "icon": zone_config["icon"],
                    "status": "no_meal",
                    "status_text": "今日無便當",
                    "expected_time": None,
                    "arrived_time": None,
                    "meal_count": 0,
                    "notes": None,
                    "updated_at": None,
                }
            )

        return {"message": "所有區域餐點狀態已重置", "zones": zones_list}
