"""
動態閾值設定服務（per-maintenance）。

提供 indicator 閾值的動態覆寫機制：
- DB 持久化（ThresholdConfig 每歲修一行）
- 記憶體快取（避免每次 evaluate 都查 DB）
- .env 預設值 fallback

使用方式::

    # 在 indicator 中讀取閾值（同步，從快取讀）
    from app.services.threshold_service import get_threshold
    value = get_threshold("transceiver_tx_power_min", "MAINT-001")

    # 確保快取已載入（async，evaluate 前呼叫）
    await ensure_cache(session, "MAINT-001")

    # API 更新閾值（async）
    result = await update_thresholds(session, "MAINT-001", {"transceiver_tx_power_min": -15.0})
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.models import ThresholdConfig

logger = logging.getLogger(__name__)

# ── 閾值定義（key → default 來源 + metadata）──────────────────────

# 所有可動態覆寫的閾值欄位
# key: (settings 屬性名, 單位, 說明)
THRESHOLD_FIELDS: dict[str, tuple[str, str, str]] = {
    "transceiver_tx_power_min": ("transceiver_tx_power_min", "dBm", "TX Power 下限"),
    "transceiver_tx_power_max": ("transceiver_tx_power_max", "dBm", "TX Power 上限"),
    "transceiver_rx_power_min": ("transceiver_rx_power_min", "dBm", "RX Power 下限"),
    "transceiver_rx_power_max": ("transceiver_rx_power_max", "dBm", "RX Power 上限"),
    "transceiver_temperature_min": ("transceiver_temperature_min", "°C", "溫度下限"),
    "transceiver_temperature_max": ("transceiver_temperature_max", "°C", "溫度上限"),
    "transceiver_voltage_min": ("transceiver_voltage_min", "V", "電壓下限"),
    "transceiver_voltage_max": ("transceiver_voltage_max", "V", "電壓上限"),
}

# 按指標分組（前端 UI 用）
THRESHOLD_GROUPS: dict[str, list[str]] = {
    "transceiver": [
        "transceiver_tx_power_min", "transceiver_tx_power_max",
        "transceiver_rx_power_min", "transceiver_rx_power_max",
        "transceiver_temperature_min", "transceiver_temperature_max",
        "transceiver_voltage_min", "transceiver_voltage_max",
    ],
}

# ── 記憶體快取（per-maintenance）─────────────────────────────────

# {maintenance_id: {key: override_value}}
_cache: dict[str, dict[str, float | int]] = {}


def get_default(key: str) -> float | int:
    """從 settings 取得 .env 預設值。"""
    attr_name = THRESHOLD_FIELDS[key][0]
    return getattr(settings, attr_name)


def get_threshold(key: str, maintenance_id: str | None = None) -> float | int:
    """
    同步讀取閾值（供 indicator @property 呼叫）。

    優先順序：per-maintenance 覆寫值 → .env 預設值。
    """
    if maintenance_id and maintenance_id in _cache:
        maint_cache = _cache[maintenance_id]
        if key in maint_cache:
            return maint_cache[key]
    return get_default(key)


# ── DB 操作 ───────────────────────────────────────────────────────

async def ensure_cache(
    session: AsyncSession,
    maintenance_id: str,
) -> None:
    """
    確保指定歲修的閾值快取已載入。

    如果快取中已有該歲修的資料，跳過。
    在 evaluate 前呼叫，確保 get_threshold() 能讀到覆寫值。
    """
    if maintenance_id in _cache:
        return
    await load_thresholds(session, maintenance_id)


async def load_thresholds(
    session: AsyncSession,
    maintenance_id: str,
) -> dict[str, Any]:
    """
    從 DB 載入覆寫值到快取。

    Returns:
        合併後的完整閾值（包含 value / default / is_override）。
    """
    maint_cache: dict[str, float | int] = {}

    stmt = select(ThresholdConfig).where(
        ThresholdConfig.maintenance_id == maintenance_id
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if row is not None:
        for key in THRESHOLD_FIELDS:
            db_value = getattr(row, key, None)
            if db_value is not None:
                maint_cache[key] = db_value

    _cache[maintenance_id] = maint_cache

    logger.info(
        "Loaded %d threshold overrides for %s: %s",
        len(maint_cache),
        maintenance_id,
        list(maint_cache.keys()) if maint_cache else "none",
    )

    return _build_response(maintenance_id)


async def update_thresholds(
    session: AsyncSession,
    maintenance_id: str,
    updates: dict[str, float | int | None],
) -> dict[str, Any]:
    """
    更新閾值覆寫。寫 DB + 刷新快取。

    Args:
        maintenance_id: 歲修 ID
        updates: 要更新的欄位。值為 None 表示清除覆寫（恢復預設）。

    Returns:
        更新後的完整閾值。
    """
    maint_cache = _cache.setdefault(maintenance_id, {})

    # 取得或建立 DB 行
    stmt = select(ThresholdConfig).where(
        ThresholdConfig.maintenance_id == maintenance_id
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if row is None:
        row = ThresholdConfig(maintenance_id=maintenance_id)
        session.add(row)

    # 套用更新
    for key, value in updates.items():
        if key not in THRESHOLD_FIELDS:
            continue
        setattr(row, key, value)
        if value is not None:
            maint_cache[key] = value
        else:
            maint_cache.pop(key, None)

    await session.commit()

    logger.info(
        "Updated thresholds for %s: %s (active overrides: %s)",
        maintenance_id,
        list(updates.keys()),
        list(maint_cache.keys()),
    )

    return _build_response(maintenance_id)


async def reset_thresholds(
    session: AsyncSession,
    maintenance_id: str,
) -> dict[str, Any]:
    """
    清除指定歲修的所有覆寫，恢復 .env 預設值。

    Returns:
        重置後的完整閾值。
    """
    _cache[maintenance_id] = {}

    stmt = select(ThresholdConfig).where(
        ThresholdConfig.maintenance_id == maintenance_id
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if row is not None:
        for key in THRESHOLD_FIELDS:
            setattr(row, key, None)
        await session.commit()

    logger.info(
        "All threshold overrides cleared for %s, using .env defaults",
        maintenance_id,
    )
    return _build_response(maintenance_id)


# ── Response Builder ─────────────────────────────────────────────

def _build_response(maintenance_id: str) -> dict[str, Any]:
    """
    建構完整的閾值回應（按指標分組）。

    格式::

        {
          "maintenance_id": "MAINT-001",
          "transceiver": {
            "tx_power_min": {
              "value": -15.0,
              "default": -12.0,
              "is_override": true,
              "unit": "dBm",
              "description": "TX Power 下限"
            },
            ...
          },
          "error_count": { ... }
        }
    """
    maint_cache = _cache.get(maintenance_id, {})
    response: dict[str, Any] = {"maintenance_id": maintenance_id}

    for group_name, keys in THRESHOLD_GROUPS.items():
        group: dict[str, Any] = {}
        for key in keys:
            _, unit, description = THRESHOLD_FIELDS[key]
            default_value = get_default(key)
            current_value = get_threshold(key, maintenance_id)
            is_override = key in maint_cache

            # 去掉 group prefix（如 transceiver_tx_power_min → tx_power_min）
            short_key = key.replace(f"{group_name}_", "", 1)

            group[short_key] = {
                "value": current_value,
                "default": default_value,
                "is_override": is_override,
                "unit": unit,
                "description": description,
            }

        response[group_name] = group

    return response
