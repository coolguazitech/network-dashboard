"""
Timezone utilities for the application.

Provides centralized timezone management based on settings configuration.
"""
from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.core.config import settings


@lru_cache(maxsize=1)
def get_app_timezone() -> ZoneInfo:
    """Get the application timezone from settings."""
    try:
        return ZoneInfo(settings.timezone)
    except Exception:
        return ZoneInfo("Asia/Taipei")


def now() -> datetime:
    """Get current datetime in the application timezone."""
    return datetime.now(get_app_timezone())


def now_utc() -> datetime:
    """Get current datetime in UTC timezone."""
    return datetime.now(UTC)
