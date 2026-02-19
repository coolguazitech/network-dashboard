"""
歲修累計活躍時間 Public Utility。

提供統一的 API 讓任何服務取得某歲修目前的累計活躍秒數。
暫停期間計時器凍結，只計算 is_active=True 期間的累計時間。

公式:
    if is_active and last_activated_at:
        total = active_seconds_accumulated + (now - last_activated_at)
    else:
        total = active_seconds_accumulated
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MaintenanceConfig


async def get_active_seconds(
    maintenance_id: str, session: AsyncSession
) -> float:
    """
    取得歲修目前的累計活躍秒數（async 版本）。

    Args:
        maintenance_id: 歲修 ID
        session: AsyncSession

    Returns:
        累計活躍秒數。找不到歲修時回傳 0.0。
    """
    stmt = select(MaintenanceConfig).where(
        MaintenanceConfig.maintenance_id == maintenance_id
    )
    result = await session.execute(stmt)
    config = result.scalar_one_or_none()
    if config is None:
        return 0.0

    return _compute(
        is_active=config.is_active,
        accumulated=config.active_seconds_accumulated,
        last_activated_at=config.last_activated_at,
    )


def get_active_seconds_sync(
    maintenance_id: str, engine: Engine
) -> float:
    """
    取得歲修目前的累計活躍秒數（sync 版本，供 Mock Server 使用）。

    Args:
        maintenance_id: 歲修 ID
        engine: Sync SQLAlchemy Engine

    Returns:
        累計活躍秒數。找不到歲修時回傳 0.0。
    """
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT is_active, active_seconds_accumulated, last_activated_at "
                "FROM maintenance_configs "
                "WHERE maintenance_id = :mid"
            ),
            {"mid": maintenance_id},
        ).fetchone()

    if row is None:
        return 0.0

    return _compute(
        is_active=bool(row[0]),
        accumulated=row[1],
        last_activated_at=row[2],
    )


def _compute(
    *,
    is_active: bool,
    accumulated: int | None,
    last_activated_at: datetime | None,
) -> float:
    """計算累計活躍秒數的共用邏輯。"""
    total = float(accumulated or 0)

    if is_active and last_activated_at is not None:
        last = last_activated_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        total += (now - last).total_seconds()

    return total
