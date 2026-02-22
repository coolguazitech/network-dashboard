"""
閾值設定 API endpoints（per-maintenance）。

提供 indicator 閾值的動態讀取和更新，每歲修獨立設定。
"""
from __future__ import annotations

from typing import Any, Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import get_async_session
from app.api.endpoints.auth import get_current_user, require_write
from app.services.system_log import write_log
from app.services.threshold_service import (
    load_thresholds,
    update_thresholds,
    reset_thresholds,
    get_threshold,
    get_default,
    THRESHOLD_FIELDS,
    THRESHOLD_GROUPS,
)

router = APIRouter(prefix="/thresholds", tags=["Thresholds"])


class ThresholdUpdateRequest(BaseModel):
    """閾值更新請求。只需包含要修改的欄位，未包含的欄位不受影響。"""

    transceiver_tx_power_min: float | None = None
    transceiver_tx_power_max: float | None = None
    transceiver_rx_power_min: float | None = None
    transceiver_rx_power_max: float | None = None
    transceiver_temperature_min: float | None = None
    transceiver_temperature_max: float | None = None
    transceiver_voltage_min: float | None = None
    transceiver_voltage_max: float | None = None

    @model_validator(mode="after")
    def check_min_less_than_max(self) -> "ThresholdUpdateRequest":
        pairs = [
            ("transceiver_tx_power_min", "transceiver_tx_power_max", "TX Power"),
            ("transceiver_rx_power_min", "transceiver_rx_power_max", "RX Power"),
            ("transceiver_temperature_min", "transceiver_temperature_max", "溫度"),
            ("transceiver_voltage_min", "transceiver_voltage_max", "電壓"),
        ]
        for min_key, max_key, label in pairs:
            min_val = getattr(self, min_key)
            max_val = getattr(self, max_key)
            if min_val is not None and max_val is not None and min_val >= max_val:
                msg = f"{label} 下限 ({min_val}) 必須小於上限 ({max_val})"
                raise ValueError(msg)
        return self


@router.get("/{maintenance_id}")
async def get_thresholds(
    maintenance_id: str,
    _: Annotated[dict[str, Any], Depends(get_current_user)],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    取得指定歲修的所有閾值設定（DB 覆寫值 + .env 預設值合併）。

    回傳格式按指標分組，每個欄位包含 value / default / is_override / unit。
    """
    return await load_thresholds(session, maintenance_id)


@router.put("/{maintenance_id}")
async def put_thresholds(
    maintenance_id: str,
    body: ThresholdUpdateRequest,
    _: Annotated[dict[str, Any], Depends(require_write())],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """
    更新指定歲修的閾值覆寫。

    只需傳要改的欄位。值為 null 表示清除該欄位的覆寫（恢復預設）。
    """
    updates = body.model_dump(exclude_unset=True)

    # 快照變更前的值
    old_values = {
        k: get_threshold(k, maintenance_id)
        for k in updates if k in THRESHOLD_FIELDS
    }

    result = await update_thresholds(session, maintenance_id, updates)

    # 組裝結構化日誌
    groups: set[str] = set()
    lines: list[str] = []
    for key, new_val in updates.items():
        if key not in THRESHOLD_FIELDS:
            continue
        _, unit, desc = THRESHOLD_FIELDS[key]
        for g, g_keys in THRESHOLD_GROUPS.items():
            if key in g_keys:
                groups.add(g)
                break
        old = old_values.get(key)
        if new_val is None:
            lines.append(f"{desc}: 恢復預設 ({get_default(key)}{unit})")
        else:
            lines.append(f"{desc}: {old} → {new_val} {unit}")

    summary = f"更新閾值設定 ({', '.join(sorted(groups))})"
    detail = "\n".join(lines)
    await write_log(
        level="INFO",
        source="api",
        summary=summary,
        detail=detail,
        module="thresholds",
        maintenance_id=maintenance_id,
    )
    return result


@router.post("/{maintenance_id}/reset")
async def post_reset_thresholds(
    maintenance_id: str,
    _: Annotated[dict[str, Any], Depends(require_write())],
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, Any]:
    """清除指定歲修的所有覆寫，恢復 .env 預設值。"""
    result = await reset_thresholds(session, maintenance_id)
    await write_log(
        level="WARNING",
        source="api",
        summary="重置所有閾值為預設值",
        module="thresholds",
        maintenance_id=maintenance_id,
    )
    return result
