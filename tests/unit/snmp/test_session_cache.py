"""Unit tests for SnmpSessionCache."""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest

# Stub out pysnmp before importing app.snmp.engine, because the real
# pysnmp-lextudio may not be installed in the test environment.
_pysnmp_stub = ModuleType("pysnmp")
_hlapi_stub = ModuleType("pysnmp.hlapi")
_asyncio_stub = ModuleType("pysnmp.hlapi.asyncio")

# Provide the names that engine.py imports at module level.
for _attr in (
    "CommunityData",
    "ContextData",
    "ObjectIdentity",
    "ObjectType",
    "UdpTransportTarget",
    "bulkCmd",
    "getCmd",
):
    setattr(_asyncio_stub, _attr, MagicMock())
_asyncio_stub.SnmpEngine = MagicMock()  # aliased as PySnmpEngine

for _mod_name, _mod in (
    ("pysnmp", _pysnmp_stub),
    ("pysnmp.hlapi", _hlapi_stub),
    ("pysnmp.hlapi.asyncio", _asyncio_stub),
):
    sys.modules.setdefault(_mod_name, _mod)

from app.snmp.engine import AsyncSnmpEngine, SnmpError, SnmpTarget, SnmpTimeoutError  # noqa: E402
from app.snmp.session_cache import SnmpSessionCache  # noqa: E402


def _make_cache(engine_mock, communities=None):
    return SnmpSessionCache(
        engine=engine_mock,
        communities=communities or ["comm1", "comm2"],
        port=161,
        timeout=5.0,
        retries=2,
    )


# ── Community caching ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_target_caches_community():
    """After a successful probe, subsequent calls return cached target."""
    engine = MagicMock(spec=AsyncSnmpEngine)
    engine.get = AsyncMock(return_value={"1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9.1.1"})

    cache = _make_cache(engine)

    target1 = await cache.get_target("10.0.0.1")
    target2 = await cache.get_target("10.0.0.1")

    # engine.get should only have been called once — the second call is cached.
    engine.get.assert_called_once()
    assert target1.community == "comm1"
    assert target2.community == "comm1"
    assert target1.ip == "10.0.0.1"


@pytest.mark.asyncio
async def test_get_target_tries_next_community_on_timeout():
    """If the first community times out, the next one is tried."""
    engine = MagicMock(spec=AsyncSnmpEngine)
    engine.get = AsyncMock(
        side_effect=[
            SnmpTimeoutError("timeout"),
            {"1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9.1.1"},
        ]
    )

    cache = _make_cache(engine)
    target = await cache.get_target("10.0.0.1")

    assert target.community == "comm2"
    assert engine.get.call_count == 2


@pytest.mark.asyncio
async def test_get_target_all_fail():
    """When every community times out, SnmpTimeoutError is raised."""
    engine = MagicMock(spec=AsyncSnmpEngine)
    engine.get = AsyncMock(side_effect=SnmpTimeoutError("timeout"))

    cache = _make_cache(engine)

    with pytest.raises(SnmpTimeoutError, match="All communities failed"):
        await cache.get_target("10.0.0.1")

    assert engine.get.call_count == 2  # tried both communities


@pytest.mark.asyncio
async def test_get_target_skips_snmp_error():
    """A generic SnmpError (not timeout) also causes fallthrough to next community."""
    engine = MagicMock(spec=AsyncSnmpEngine)
    engine.get = AsyncMock(
        side_effect=[
            SnmpError("auth failure"),
            {"1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9.1.1"},
        ]
    )

    cache = _make_cache(engine)
    target = await cache.get_target("10.0.0.1")

    assert target.community == "comm2"
    assert engine.get.call_count == 2


# ── ifIndex map ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_ifindex_map_caches():
    """Walk is only called once per IP; second call uses cache."""
    engine = MagicMock(spec=AsyncSnmpEngine)
    engine.get = AsyncMock(return_value={"1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9.1.1"})
    engine.walk = AsyncMock(
        return_value=[
            ("1.3.6.1.2.1.31.1.1.1.1.1", "GigabitEthernet0/1"),
        ]
    )

    cache = _make_cache(engine)

    result1 = await cache.get_ifindex_map("10.0.0.1")
    result2 = await cache.get_ifindex_map("10.0.0.1")

    engine.walk.assert_called_once()
    assert result1 == result2


@pytest.mark.asyncio
async def test_get_ifindex_map_parses_correctly():
    """OID suffix is extracted as ifIndex key, value is ifName."""
    engine = MagicMock(spec=AsyncSnmpEngine)
    engine.get = AsyncMock(return_value={"1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9.1.1"})
    engine.walk = AsyncMock(
        return_value=[
            ("1.3.6.1.2.1.31.1.1.1.1.1", "GigabitEthernet0/1"),
            ("1.3.6.1.2.1.31.1.1.1.1.49", "GigabitEthernet1/0/1"),
        ]
    )

    cache = _make_cache(engine)
    result = await cache.get_ifindex_map("10.0.0.1")

    assert result == {
        1: "GigabitEthernet0/1",
        49: "GigabitEthernet1/0/1",
    }


# ── Bridge port map ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_bridge_port_map_caches():
    """Walk is only called once per IP; second call uses cache."""
    engine = MagicMock(spec=AsyncSnmpEngine)
    engine.get = AsyncMock(return_value={"1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9.1.1"})
    engine.walk = AsyncMock(
        return_value=[
            ("1.3.6.1.2.1.17.1.4.1.2.1", "10001"),
            ("1.3.6.1.2.1.17.1.4.1.2.2", "10002"),
        ]
    )

    cache = _make_cache(engine)

    result1 = await cache.get_bridge_port_map("10.0.0.1")
    result2 = await cache.get_bridge_port_map("10.0.0.1")

    engine.walk.assert_called_once()
    assert result1 == result2


@pytest.mark.asyncio
async def test_get_bridge_port_map_parses_correctly():
    """OID suffix is bridge port, value is ifIndex."""
    engine = MagicMock(spec=AsyncSnmpEngine)
    engine.get = AsyncMock(return_value={"1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9.1.1"})
    engine.walk = AsyncMock(
        return_value=[
            ("1.3.6.1.2.1.17.1.4.1.2.1", "10001"),
            ("1.3.6.1.2.1.17.1.4.1.2.2", "10002"),
            ("1.3.6.1.2.1.17.1.4.1.2.48", "10048"),
        ]
    )

    cache = _make_cache(engine)
    result = await cache.get_bridge_port_map("10.0.0.1")

    assert result == {
        1: 10001,
        2: 10002,
        48: 10048,
    }


# ── clear() ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_clear_resets_all_caches():
    """After clear(), all three caches are empty and probes run again."""
    engine = MagicMock(spec=AsyncSnmpEngine)
    engine.get = AsyncMock(return_value={"1.3.6.1.2.1.1.2.0": "1.3.6.1.4.1.9.1.1"})
    engine.walk = AsyncMock(
        return_value=[
            ("1.3.6.1.2.1.31.1.1.1.1.1", "GigabitEthernet0/1"),
        ]
    )

    cache = _make_cache(engine)
    ip = "10.0.0.1"

    # Populate all three caches
    await cache.get_target(ip)
    await cache.get_ifindex_map(ip)

    # Swap walk mock to return bridge port data for bridge_port_map call
    engine.walk = AsyncMock(
        return_value=[
            ("1.3.6.1.2.1.17.1.4.1.2.1", "10001"),
        ]
    )
    await cache.get_bridge_port_map(ip)

    # Verify caches are populated via internal dicts
    assert ip in cache._community_cache
    assert ip in cache._ifindex_cache
    assert ip in cache._bridge_port_cache

    cache.clear()

    assert cache._community_cache == {}
    assert cache._ifindex_cache == {}
    assert cache._bridge_port_cache == {}
