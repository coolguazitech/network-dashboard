"""
Unit tests for Indicator API endpoints.

Tests:
- list_indicators (GET /indicators)
- get_indicator (GET /indicators/{name})
- get_indicator_timeseries (GET /indicators/{maint}/{name}/timeseries)
- get_indicator_raw_data (GET /indicators/{maint}/{name}/rawdata)
- trigger_collection (POST /indicators/{maint}/{name}/collect)
- Access control (check_maintenance_access)
- Pagination edge cases
- Invalid indicator names
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.endpoints.auth import get_current_user, require_write
from app.api.endpoints.indicators import router
from app.db.base import get_async_session
from app.indicators.base import (
    DisplayConfig,
    IndicatorMetadata,
    ObservedField,
    RawDataRow,
    TimeSeriesPoint,
)


# ── Helpers ──────────────────────────────────────────────────────

ROOT_USER = {
    "user_id": 1, "username": "root", "role": "ROOT",
    "maintenance_id": None, "display_name": "Root", "is_root": True,
}
PM_USER = {
    "user_id": 2, "username": "pm1", "role": "PM",
    "maintenance_id": "MAINT-001", "display_name": "PM", "is_root": False,
}
GUEST_USER = {
    "user_id": 3, "username": "guest1", "role": "GUEST",
    "maintenance_id": "MAINT-001", "display_name": "Guest", "is_root": False,
}
GUEST_OTHER = {
    "user_id": 4, "username": "guest2", "role": "GUEST",
    "maintenance_id": "MAINT-002", "display_name": "Guest2", "is_root": False,
}


def _mock_session():
    s = AsyncMock()
    s.execute = AsyncMock()
    s.commit = AsyncMock()
    return s


def _build_app(user, session=None):
    app = FastAPI()
    app.include_router(router, prefix="/indicators")
    app.dependency_overrides[get_current_user] = lambda: user

    async def _write_override():
        return user

    app.dependency_overrides[require_write()] = _write_override
    if session is not None:
        app.dependency_overrides[get_async_session] = lambda: session
    return app


def _fake_metadata(name="test_indicator"):
    return IndicatorMetadata(
        name=name,
        title="Test Indicator",
        description="Test desc",
        object_type="switch",
        data_type="float",
        observed_fields=[
            ObservedField(
                name="test_rate",
                display_name="Test Rate",
                metric_name="test_rate",
                unit="%",
            )
        ],
        display_config=DisplayConfig(
            chart_type="line",
            x_axis_label="時間",
            y_axis_label="Pass Rate (%)",
            y_axis_min=0.0,
            y_axis_max=100.0,
            line_colors=["#5470c6"],
        ),
    )


def _fake_indicator(name="test_indicator"):
    indicator = MagicMock()
    indicator.get_metadata.return_value = _fake_metadata(name)
    indicator.indicator_type = name
    return indicator


NOW = datetime(2026, 1, 15, 10, 0, 0, tzinfo=timezone.utc)


# ══════════════════════════════════════════════════════════════════
# ListIndicators
# ══════════════════════════════════════════════════════════════════


class TestListIndicators:
    """GET /indicators"""

    @pytest.mark.asyncio
    async def test_returns_all_indicators(self):
        app = _build_app(ROOT_USER)
        indicators = [_fake_indicator("transceiver"), _fake_indicator("version")]

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr:
            mock_mgr.get_all_indicators.return_value = indicators
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/indicators")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["name"] == "transceiver"
        assert data[1]["name"] == "version"

    @pytest.mark.asyncio
    async def test_empty_indicator_list(self):
        app = _build_app(ROOT_USER)

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr:
            mock_mgr.get_all_indicators.return_value = []
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/indicators")

        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_guest_can_list(self):
        """Any authenticated user can list indicators."""
        app = _build_app(GUEST_USER)

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr:
            mock_mgr.get_all_indicators.return_value = []
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/indicators")

        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════
# GetIndicator
# ══════════════════════════════════════════════════════════════════


class TestGetIndicator:
    """GET /indicators/{indicator_name}"""

    @pytest.mark.asyncio
    async def test_found(self):
        app = _build_app(ROOT_USER)

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr:
            mock_mgr.get_indicator.return_value = _fake_indicator("transceiver")
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/indicators/transceiver")

        assert resp.status_code == 200
        assert resp.json()["name"] == "transceiver"

    @pytest.mark.asyncio
    async def test_not_found(self):
        app = _build_app(ROOT_USER)

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr:
            mock_mgr.get_indicator.return_value = None
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/indicators/nonexistent")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.parametrize("name", [
        "transceiver", "version", "uplink", "port_channel",
        "fan", "power", "ping", "error_count",
    ])
    async def test_valid_indicator_names(self, name):
        app = _build_app(ROOT_USER)

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr:
            mock_mgr.get_indicator.return_value = _fake_indicator(name)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(f"/indicators/{name}")

        assert resp.status_code == 200
        assert resp.json()["name"] == name


# ══════════════════════════════════════════════════════════════════
# GetIndicatorTimeseries — Access Control
# ══════════════════════════════════════════════════════════════════


class TestTimeseriesAccessControl:
    """Access control on GET /indicators/{maint}/{name}/timeseries"""

    @pytest.mark.asyncio
    async def test_root_can_access_any_maintenance(self):
        session = _mock_session()
        app = _build_app(ROOT_USER, session)
        indicator = _fake_indicator("transceiver")
        indicator.get_time_series = AsyncMock(return_value=[])

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = indicator
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-999/transceiver/timeseries"
                )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_guest_own_maintenance_ok(self):
        session = _mock_session()
        app = _build_app(GUEST_USER, session)
        indicator = _fake_indicator("transceiver")
        indicator.get_time_series = AsyncMock(return_value=[])

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = indicator
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-001/transceiver/timeseries"
                )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_guest_wrong_maintenance_403(self):
        """Guest assigned to MAINT-001 cannot access MAINT-999."""
        session = _mock_session()
        app = _build_app(GUEST_USER, session)

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = _fake_indicator("transceiver")
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-999/transceiver/timeseries"
                )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_pm_own_maintenance_ok(self):
        session = _mock_session()
        app = _build_app(PM_USER, session)
        indicator = _fake_indicator("transceiver")
        indicator.get_time_series = AsyncMock(return_value=[])

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = indicator
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-001/transceiver/timeseries"
                )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_pm_wrong_maintenance_403(self):
        session = _mock_session()
        app = _build_app(PM_USER, session)

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = _fake_indicator("transceiver")
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-999/transceiver/timeseries"
                )

        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════
# GetIndicatorTimeseries — Data
# ══════════════════════════════════════════════════════════════════


class TestTimeseriesData:
    """GET /indicators/{maint}/{name}/timeseries — data scenarios"""

    @pytest.mark.asyncio
    async def test_returns_time_series(self):
        session = _mock_session()
        app = _build_app(ROOT_USER, session)
        indicator = _fake_indicator("transceiver")
        indicator.get_time_series = AsyncMock(return_value=[
            TimeSeriesPoint(timestamp=NOW, values={"test_rate": 95.0}),
        ])

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = indicator
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-001/transceiver/timeseries"
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["indicator_name"] == "transceiver"
        assert len(data["data"]) == 1
        assert data["data"][0]["values"]["test_rate"] == 95.0

    @pytest.mark.asyncio
    async def test_empty_time_series(self):
        session = _mock_session()
        app = _build_app(ROOT_USER, session)
        indicator = _fake_indicator("transceiver")
        indicator.get_time_series = AsyncMock(return_value=[])

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = indicator
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-001/transceiver/timeseries"
                )

        assert resp.status_code == 200
        assert resp.json()["data"] == []

    @pytest.mark.asyncio
    async def test_nonexistent_indicator_404(self):
        session = _mock_session()
        app = _build_app(ROOT_USER, session)

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = None
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-001/nonexistent/timeseries"
                )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_limit_param(self):
        session = _mock_session()
        app = _build_app(ROOT_USER, session)
        indicator = _fake_indicator("transceiver")
        indicator.get_time_series = AsyncMock(return_value=[])

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = indicator
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-001/transceiver/timeseries",
                    params={"limit": 10},
                )

        assert resp.status_code == 200
        indicator.get_time_series.assert_called_once()
        call_kwargs = indicator.get_time_series.call_args.kwargs
        assert call_kwargs["limit"] == 10

    @pytest.mark.asyncio
    async def test_limit_too_large_rejected(self):
        """limit > 1000 should be rejected by Query validation."""
        session = _mock_session()
        app = _build_app(ROOT_USER, session)

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = _fake_indicator("transceiver")
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-001/transceiver/timeseries",
                    params={"limit": 9999},
                )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_limit_zero_rejected(self):
        session = _mock_session()
        app = _build_app(ROOT_USER, session)

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = _fake_indicator("transceiver")
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-001/transceiver/timeseries",
                    params={"limit": 0},
                )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_multiple_data_points(self):
        session = _mock_session()
        app = _build_app(ROOT_USER, session)
        indicator = _fake_indicator("transceiver")
        points = [
            TimeSeriesPoint(
                timestamp=datetime(2026, 1, 15, i, 0, 0, tzinfo=timezone.utc),
                values={"test_rate": 90.0 + i},
            )
            for i in range(5)
        ]
        indicator.get_time_series = AsyncMock(return_value=points)

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = indicator
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-001/transceiver/timeseries"
                )

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["data"]) == 5
        assert data["series_names"] == ["test_rate"]


# ══════════════════════════════════════════════════════════════════
# GetIndicatorRawData — Access Control
# ══════════════════════════════════════════════════════════════════


class TestRawDataAccessControl:
    """Access control on GET /indicators/{maint}/{name}/rawdata"""

    @pytest.mark.asyncio
    async def test_guest_wrong_maintenance_403(self):
        session = _mock_session()
        app = _build_app(GUEST_USER, session)

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = _fake_indicator("transceiver")
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-999/transceiver/rawdata"
                )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_guest_own_maintenance_ok(self):
        session = _mock_session()
        app = _build_app(GUEST_USER, session)
        indicator = _fake_indicator("transceiver")
        indicator.get_latest_raw_data = AsyncMock(return_value=[])

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = indicator
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-001/transceiver/rawdata"
                )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_root_any_maintenance(self):
        session = _mock_session()
        app = _build_app(ROOT_USER, session)
        indicator = _fake_indicator("transceiver")
        indicator.get_latest_raw_data = AsyncMock(return_value=[])

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = indicator
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-999/transceiver/rawdata"
                )

        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════
# GetIndicatorRawData — Pagination
# ══════════════════════════════════════════════════════════════════


class TestRawDataPagination:
    """GET /indicators/{maint}/{name}/rawdata — pagination scenarios"""

    @pytest.mark.asyncio
    async def test_default_page(self):
        session = _mock_session()
        app = _build_app(ROOT_USER, session)
        indicator = _fake_indicator("transceiver")
        rows = [RawDataRow(id=i, value=f"v{i}", collected_at=NOW) for i in range(3)]
        indicator.get_latest_raw_data = AsyncMock(return_value=rows)

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = indicator
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-001/transceiver/rawdata"
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert data["page_size"] == 50
        assert len(data["rows"]) == 3

    @pytest.mark.asyncio
    async def test_pagination_passes_offset(self):
        """Page 3, page_size=10 should pass offset=20, limit=10."""
        session = _mock_session()
        app = _build_app(ROOT_USER, session)
        indicator = _fake_indicator("transceiver")
        indicator.get_latest_raw_data = AsyncMock(return_value=[])

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = indicator
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-001/transceiver/rawdata",
                    params={"page": 3, "page_size": 10},
                )

        assert resp.status_code == 200
        call_kwargs = indicator.get_latest_raw_data.call_args.kwargs
        assert call_kwargs["limit"] == 10
        assert call_kwargs["offset"] == 20

    @pytest.mark.asyncio
    async def test_page_size_max(self):
        """page_size > 200 should be rejected."""
        session = _mock_session()
        app = _build_app(ROOT_USER, session)

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = _fake_indicator("transceiver")
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-001/transceiver/rawdata",
                    params={"page_size": 201},
                )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_page_zero_rejected(self):
        session = _mock_session()
        app = _build_app(ROOT_USER, session)

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = _fake_indicator("transceiver")
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-001/transceiver/rawdata",
                    params={"page": 0},
                )

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_empty_rawdata(self):
        session = _mock_session()
        app = _build_app(ROOT_USER, session)
        indicator = _fake_indicator("transceiver")
        indicator.get_latest_raw_data = AsyncMock(return_value=[])

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = indicator
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-001/transceiver/rawdata"
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["rows"] == []
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_nonexistent_indicator_404(self):
        session = _mock_session()
        app = _build_app(ROOT_USER, session)

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = None
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-001/nonexistent/rawdata"
                )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_transceiver_columns(self):
        """Transceiver raw data should return specialized columns."""
        session = _mock_session()
        app = _build_app(ROOT_USER, session)
        indicator = _fake_indicator("transceiver")
        indicator.get_latest_raw_data = AsyncMock(return_value=[])

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.ensure_cache", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = indicator
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/indicators/MAINT-001/transceiver/rawdata"
                )

        assert resp.status_code == 200
        cols = resp.json()["columns"]
        col_keys = [c["key"] for c in cols]
        assert "tx_power" in col_keys
        assert "rx_power" in col_keys
        assert "switch_hostname" in col_keys


# ══════════════════════════════════════════════════════════════════
# TriggerCollection — Access Control
# ══════════════════════════════════════════════════════════════════


class TestCollectAccessControl:
    """Access control on POST /indicators/{maint}/{name}/collect"""

    @pytest.mark.asyncio
    async def test_guest_cannot_collect(self):
        """GUEST has no write permission → 403."""
        session = _mock_session()
        app = _build_app(GUEST_USER, session)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/indicators/MAINT-001/transceiver/collect"
            )

        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_pm_wrong_maintenance_403(self):
        """PM accessing another maintenance → 403."""
        session = _mock_session()
        app = _build_app(PM_USER, session)

        with patch(
            "app.api.endpoints.indicators.indicator_manager"
        ) as mock_mgr, patch(
            "app.api.endpoints.indicators.write_log", new_callable=AsyncMock
        ):
            mock_mgr.get_indicator.return_value = _fake_indicator("transceiver")
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/indicators/MAINT-999/transceiver/collect"
                )

        assert resp.status_code == 403
