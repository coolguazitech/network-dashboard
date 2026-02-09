"""
Timezone utilities for the application.

Provides centralized timezone management based on settings configuration.
All datetime operations should use these utilities to ensure consistency.
"""
from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.core.config import settings


@lru_cache(maxsize=1)
def get_app_timezone() -> ZoneInfo:
    """
    Get the application timezone from settings.

    Returns:
        ZoneInfo object for the configured timezone.
        Defaults to Asia/Taipei if not configured or invalid.

    Examples:
        >>> tz = get_app_timezone()
        >>> now = datetime.now(tz)
    """
    try:
        return ZoneInfo(settings.timezone)
    except Exception:
        # Fallback to Asia/Taipei if timezone is invalid
        return ZoneInfo("Asia/Taipei")


def now() -> datetime:
    """
    Get current datetime in the application timezone.

    Returns:
        Timezone-aware datetime object in the configured timezone.

    Examples:
        >>> from app.core.timezone import now
        >>> current_time = now()
    """
    return datetime.now(get_app_timezone())


def now_utc() -> datetime:
    """
    Get current datetime in UTC timezone.

    Returns:
        Timezone-aware datetime object in UTC.

    Examples:
        >>> from app.core.timezone import now_utc
        >>> utc_time = now_utc()
    """
    return datetime.now(UTC)


def to_app_timezone(dt: datetime) -> datetime:
    """
    Convert a datetime to the application timezone.

    Args:
        dt: Input datetime (timezone-aware or naive)

    Returns:
        Datetime converted to application timezone.
        If input is naive, assumes it's in UTC.

    Examples:
        >>> utc_time = datetime.now(UTC)
        >>> local_time = to_app_timezone(utc_time)
    """
    if dt.tzinfo is None:
        # Treat naive datetime as UTC
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(get_app_timezone())


def to_utc(dt: datetime) -> datetime:
    """
    Convert a datetime to UTC timezone.

    Args:
        dt: Input datetime (timezone-aware or naive)

    Returns:
        Datetime converted to UTC.
        If input is naive, assumes it's in the application timezone.

    Examples:
        >>> local_time = now()
        >>> utc_time = to_utc(local_time)
    """
    if dt.tzinfo is None:
        # Treat naive datetime as application timezone
        dt = dt.replace(tzinfo=get_app_timezone())
    return dt.astimezone(UTC)


def naive_to_aware(dt: datetime, tz: ZoneInfo | None = None) -> datetime:
    """
    Convert a naive datetime to timezone-aware datetime.

    Args:
        dt: Naive datetime object
        tz: Target timezone (defaults to application timezone)

    Returns:
        Timezone-aware datetime object.

    Examples:
        >>> naive = datetime(2025, 1, 1, 12, 0, 0)
        >>> aware = naive_to_aware(naive)
    """
    if dt.tzinfo is not None:
        return dt

    target_tz = tz or get_app_timezone()
    return dt.replace(tzinfo=target_tz)


def aware_to_naive(dt: datetime) -> datetime:
    """
    Convert a timezone-aware datetime to naive datetime.

    Warning: This removes timezone information and should be used sparingly.
    Prefer keeping datetime objects timezone-aware when possible.

    Args:
        dt: Timezone-aware datetime object

    Returns:
        Naive datetime object in the same timezone.

    Examples:
        >>> aware = now()
        >>> naive = aware_to_naive(aware)
    """
    return dt.replace(tzinfo=None)
