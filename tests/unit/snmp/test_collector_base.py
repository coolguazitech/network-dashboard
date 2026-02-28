"""Unit tests for BaseSnmpCollector and helper methods."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core.enums import DeviceType
from app.snmp.collector_base import BaseSnmpCollector
from app.snmp.engine import SnmpTarget, SnmpTimeoutError


# ── Concrete test collector ──────────────────────────────────────

class _DummyCollector(BaseSnmpCollector):
    api_name = "test_dummy"

    def __init__(self, side_effect=None):
        self._side_effect = side_effect
        self._call_count = 0

    async def collect(self, target, device_type, session_cache, engine):
        self._call_count += 1
        if self._side_effect:
            raise self._side_effect
        return "raw", [{"dummy": True}]


@pytest.fixture
def target():
    return SnmpTarget(
        ip="10.0.0.1", community="public", port=161,
        timeout=5.0, retries=2,
    )


# ── Tests ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_collect_with_retry_success_first_try(target):
    collector = _DummyCollector()
    raw, items = await collector.collect_with_retry(
        target, DeviceType.HPE, AsyncMock(), AsyncMock(), max_retries=2,
    )
    assert raw == "raw"
    assert len(items) == 1
    assert collector._call_count == 1


@pytest.mark.asyncio
async def test_collect_with_retry_retries_on_timeout(target):
    """Should retry on SnmpTimeoutError up to max_retries."""
    call_count = 0

    class _RetryCollector(BaseSnmpCollector):
        api_name = "test_retry"

        async def collect(self, target, device_type, session_cache, engine):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise SnmpTimeoutError("timeout")
            return "ok", []

    collector = _RetryCollector()
    raw, items = await collector.collect_with_retry(
        target, DeviceType.HPE, AsyncMock(), AsyncMock(), max_retries=2,
    )
    assert raw == "ok"
    assert call_count == 3


@pytest.mark.asyncio
async def test_collect_with_retry_exhausted(target):
    """Should raise after all retries exhausted."""
    collector = _DummyCollector(side_effect=SnmpTimeoutError("timeout"))
    with pytest.raises(SnmpTimeoutError, match="all retries exhausted"):
        await collector.collect_with_retry(
            target, DeviceType.HPE, AsyncMock(), AsyncMock(), max_retries=1,
        )
    assert collector._call_count == 2  # initial + 1 retry


@pytest.mark.asyncio
async def test_collect_with_retry_asyncio_timeout(target):
    """asyncio.TimeoutError should also be retried."""
    call_count = 0

    class _AsyncTimeoutCollector(BaseSnmpCollector):
        api_name = "test_async_timeout"

        async def collect(self, target, device_type, session_cache, engine):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError()
            return "ok", []

    collector = _AsyncTimeoutCollector()
    raw, _ = await collector.collect_with_retry(
        target, DeviceType.HPE, AsyncMock(), AsyncMock(), max_retries=2,
    )
    assert raw == "ok"
    assert call_count == 2


@pytest.mark.asyncio
async def test_collect_with_retry_non_timeout_not_retried(target):
    """Non-timeout errors should propagate immediately."""
    collector = _DummyCollector(side_effect=ValueError("bad data"))
    with pytest.raises(ValueError, match="bad data"):
        await collector.collect_with_retry(
            target, DeviceType.HPE, AsyncMock(), AsyncMock(), max_retries=2,
        )
    assert collector._call_count == 1  # no retry


def test_format_raw():
    varbinds = [
        ("1.3.6.1.2.1.1.1.0", "HPE Comware"),
        ("1.3.6.1.2.1.1.2.0", "1.3.6.1.4.1.25506"),
    ]
    raw = BaseSnmpCollector.format_raw(
        "test_api", "10.0.0.1", DeviceType.HPE, varbinds,
    )
    assert "test_api" in raw
    assert "10.0.0.1" in raw
    assert "HPE" in raw
    assert "OID count: 2" in raw
    assert "1.3.6.1.2.1.1.1.0 = HPE Comware" in raw


def test_extract_index():
    oid = "1.3.6.1.2.1.2.2.1.8.49"
    prefix = "1.3.6.1.2.1.2.2.1.8"
    assert BaseSnmpCollector.extract_index(oid, prefix) == "49"


def test_extract_index_compound():
    oid = "1.3.6.1.4.1.9.9.23.1.2.1.1.6.49.1"
    prefix = "1.3.6.1.4.1.9.9.23.1.2.1.1.6"
    assert BaseSnmpCollector.extract_index(oid, prefix) == "49.1"


def test_safe_int():
    assert BaseSnmpCollector.safe_int("42") == 42
    assert BaseSnmpCollector.safe_int("abc") == 0
    assert BaseSnmpCollector.safe_int("abc", -1) == -1
    assert BaseSnmpCollector.safe_int("0") == 0
