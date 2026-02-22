"""
Mock Server DB \u5b58\u53d6\u5c64\u3002

\u4f7f\u7528 Sync SQLAlchemy \u8b80\u53d6\u8207\u4e3b\u61c9\u7528\u76f8\u540c\u7684 MariaDB\u3002
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from mock_server.config import settings

logger = logging.getLogger(__name__)

_engine: Engine | None = None


def get_engine() -> Engine:
    """\u53d6\u5f97\u5171\u7528\u7684 Sync Engine\u3002"""
    global _engine
    if _engine is None:
        _engine = create_engine(
            settings.database_url,
            pool_size=5,
            max_overflow=5,
            pool_recycle=300,
        )
    return _engine


def get_active_seconds(maintenance_id: str) -> float:
    """
    \u53d6\u5f97\u6b72\u4fee\u7d2f\u8a08\u6d3b\u8e8d\u79d2\u6578\u3002

    \u8207 app/services/maintenance_time.py \u76f8\u540c\u908f\u8f2f\uff0c
    \u4f46\u4f7f\u7528 sync DB \u5b58\u53d6\u3002
    """
    engine = get_engine()
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT is_active, active_seconds_accumulated, "
                "last_activated_at "
                "FROM maintenance_configs "
                "WHERE maintenance_id = :mid"
            ),
            {"mid": maintenance_id},
        ).fetchone()

    if row is None:
        return 0.0

    is_active = bool(row[0])
    accumulated = float(row[1] or 0)
    last_activated_at = row[2]

    if is_active and last_activated_at is not None:
        last: datetime = last_activated_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        accumulated += (now - last).total_seconds()

    return accumulated


def get_uplink_neighbors(
    maintenance_id: str, switch_ip: str,
) -> list[tuple[str, str, str]]:
    """
    根據 switch_ip 查出 hostname，再從 uplink_expectations 取得期望鄰居。

    Returns:
        [(local_interface, expected_neighbor, expected_interface), ...]
    """
    engine = get_engine()
    with engine.connect() as conn:
        # switch_ip → hostname（查 new_ip 或 old_ip）
        row = conn.execute(
            text(
                "SELECT old_hostname, new_hostname, "
                "old_ip_address, new_ip_address "
                "FROM maintenance_device_list "
                "WHERE maintenance_id = :mid "
                "AND (old_ip_address = :ip OR new_ip_address = :ip) "
                "LIMIT 1"
            ),
            {"mid": maintenance_id, "ip": switch_ip},
        ).fetchone()

        if row is None:
            return []

        old_host, new_host, old_ip, new_ip = row[0], row[1], row[2], row[3]
        # 新設備用 new_hostname，舊設備用 old_hostname
        hostname = new_host if switch_ip == new_ip else old_host
        if not hostname:
            return []

        rows = conn.execute(
            text(
                "SELECT local_interface, expected_neighbor, "
                "expected_interface "
                "FROM uplink_expectations "
                "WHERE maintenance_id = :mid AND hostname = :host"
            ),
            {"mid": maintenance_id, "host": hostname},
        ).fetchall()

    return [(r[0], r[1], r[2]) for r in rows]


def get_mac_list(maintenance_id: str) -> list[dict]:
    """
    \u53d6\u5f97\u6b72\u4fee\u7684 MAC \u6e05\u55ae\uff08\u4f9b MAC table API \u4f7f\u7528\uff09\u3002
    """
    engine = get_engine()
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT mac_address, ip_address, tenant_group "
                "FROM maintenance_mac_list "
                "WHERE maintenance_id = :mid"
            ),
            {"mid": maintenance_id},
        ).fetchall()

    return [
        {
            "mac_address": r[0],
            "ip_address": r[1],
            "tenant_group": r[2],
        }
        for r in rows
    ]
