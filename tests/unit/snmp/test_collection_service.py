"""Tests for SnmpCollectionService and scheduler mode switch."""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub out pysnmp before importing any app.snmp modules, because the real
# pysnmp-lextudio may not be installed in the test environment.
# (Same approach as test_session_cache.py)
# ---------------------------------------------------------------------------
_pysnmp_stub = ModuleType("pysnmp")
_hlapi_stub = ModuleType("pysnmp.hlapi")
_asyncio_stub = ModuleType("pysnmp.hlapi.asyncio")

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

from app.snmp.collection_service import (  # noqa: E402
    SnmpCollectionService,
    _API_PASSTHROUGH,
    _build_collector_map,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service(api_fallback_mock: MagicMock | None = None) -> SnmpCollectionService:
    """Create a SnmpCollectionService with the API fallback pre-injected."""
    svc = SnmpCollectionService()
    if api_fallback_mock is not None:
        svc._api_fallback = api_fallback_mock
    return svc


# =========================================================================
# 1. Passthrough: ACL delegates to ApiCollectionService
# =========================================================================


@pytest.mark.asyncio
async def test_passthrough_acl_delegates_to_api():
    """get_static_acl is in _API_PASSTHROUGH and must delegate to API."""
    fallback = MagicMock()
    fallback.collect = AsyncMock(return_value={"api_name": "get_static_acl", "total": 1, "success": 1, "failed": 0})

    svc = _make_service(api_fallback_mock=fallback)
    result = await svc.collect(
        api_name="get_static_acl",
        source="test",
        maintenance_id="M-001",
    )

    fallback.collect.assert_awaited_once_with(
        api_name="get_static_acl",
        source="test",
        maintenance_id="M-001",
    )
    assert result["api_name"] == "get_static_acl"


# =========================================================================
# 2. Passthrough: ping delegates to ApiCollectionService
# =========================================================================


@pytest.mark.asyncio
async def test_passthrough_ping_delegates_to_api():
    """gnms_ping is in _API_PASSTHROUGH and must delegate to API."""
    fallback = MagicMock()
    fallback.collect = AsyncMock(return_value={"api_name": "gnms_ping", "total": 5, "success": 5, "failed": 0})

    svc = _make_service(api_fallback_mock=fallback)
    result = await svc.collect(
        api_name="gnms_ping",
        source="test",
        maintenance_id="M-002",
    )

    fallback.collect.assert_awaited_once_with(
        api_name="gnms_ping",
        source="test",
        maintenance_id="M-002",
    )
    assert result["api_name"] == "gnms_ping"


# =========================================================================
# 3. Unknown api_name falls back to ApiCollectionService
# =========================================================================


@pytest.mark.asyncio
async def test_unknown_api_name_falls_back_to_api():
    """An api_name with no SNMP collector should fall back to API."""
    fallback = MagicMock()
    fallback.collect = AsyncMock(return_value={"api_name": "unknown_api", "total": 0, "success": 0, "failed": 0})

    svc = _make_service(api_fallback_mock=fallback)

    # Verify that "unknown_api" is indeed not in the collector map.
    assert "unknown_api" not in svc._collectors

    result = await svc.collect(
        api_name="unknown_api",
        source="test",
        maintenance_id="M-003",
    )

    fallback.collect.assert_awaited_once_with(
        api_name="unknown_api",
        source="test",
        maintenance_id="M-003",
    )
    assert result["api_name"] == "unknown_api"


# =========================================================================
# 4. Known SNMP api_name uses collector (not API fallback)
# =========================================================================


@pytest.mark.asyncio
async def test_known_snmp_api_uses_collector():
    """A known SNMP api_name like 'get_fan' must go through _do_collect."""
    fallback = MagicMock()
    fallback.collect = AsyncMock()

    svc = _make_service(api_fallback_mock=fallback)

    # Verify get_fan is in the collector map.
    assert "get_fan" in svc._collectors

    expected_result = {
        "api_name": "get_fan",
        "total": 3,
        "success": 3,
        "failed": 0,
        "errors": [],
    }

    with patch.object(svc, "_do_collect", new_callable=AsyncMock, return_value=expected_result) as mock_do:
        result = await svc.collect(
            api_name="get_fan",
            source="test",
            maintenance_id="M-004",
        )

    # _do_collect was called
    mock_do.assert_awaited_once()
    call_kwargs = mock_do.call_args
    assert call_kwargs.kwargs["api_name"] == "get_fan" or call_kwargs[1]["api_name"] == "get_fan"

    # API fallback was NOT called
    fallback.collect.assert_not_awaited()

    assert result["api_name"] == "get_fan"


# =========================================================================
# 5. Scheduler: API mode creates ApiCollectionService
# =========================================================================


def test_scheduler_api_mode():
    """When collection_mode='api', SchedulerService uses ApiCollectionService."""
    from app.services.data_collection import ApiCollectionService
    from app.services.scheduler import SchedulerService

    with patch("app.core.config.settings") as mock_settings, \
         patch("app.services.scheduler.ApiCollectionService") as MockApiSvc:
        mock_settings.collection_mode = "api"
        MockApiSvc.return_value = MagicMock(spec=ApiCollectionService)

        svc = SchedulerService()

        # The collection_service should be the ApiCollectionService instance
        MockApiSvc.assert_called_once()
        assert svc.collection_service is MockApiSvc.return_value


# =========================================================================
# 6. Scheduler: SNMP mode creates SnmpCollectionService
# =========================================================================


def test_scheduler_snmp_mode():
    """When collection_mode='snmp', SchedulerService uses SnmpCollectionService."""
    from app.services.scheduler import SchedulerService

    with patch("app.core.config.settings") as mock_settings, \
         patch("app.snmp.collection_service.SnmpCollectionService.__init__", return_value=None):
        mock_settings.collection_mode = "snmp"

        svc = SchedulerService()

        assert isinstance(svc.collection_service, SnmpCollectionService)


# =========================================================================
# 7. _build_collector_map has exactly the 10 expected API names
# =========================================================================


def test_collector_map_has_all_10_apis():
    """_build_collector_map() must return exactly 10 known SNMP API collectors."""
    collector_map = _build_collector_map()

    expected_keys = {
        "get_fan",
        "get_power",
        "get_version",
        "get_gbic_details",
        "get_error_count",
        "get_channel_group",
        "get_uplink_lldp",
        "get_uplink_cdp",
        "get_mac_table",
        "get_interface_status",
    }

    assert set(collector_map.keys()) == expected_keys
    assert len(collector_map) == 10


# =========================================================================
# Extra: _API_PASSTHROUGH contains the expected set
# =========================================================================


def test_api_passthrough_set():
    """_API_PASSTHROUGH should contain exactly the 4 non-SNMP API names."""
    expected = {"get_static_acl", "get_dynamic_acl", "gnms_ping", "ping_batch"}
    assert _API_PASSTHROUGH == expected
