"""
Unit tests for Dashboard API endpoints.

Tests /config/frontend, /maintenance/{id}/summary, and
/maintenance/{id}/indicator/{type}/details routes.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.endpoints.auth import get_current_user
from app.api.endpoints.dashboard import router
from app.db.base import get_async_session
from app.indicators.base import IndicatorEvaluationResult


# ── Helpers ──────────────────────────────────────────────────────


def _create_app(user_override=None, session_override=None):
    """Build a throwaway FastAPI app wired to the dashboard router."""
    app = FastAPI()
    # dashboard router has no prefix in the source
    app.include_router(router)
    if user_override is not None:
        app.dependency_overrides[get_current_user] = lambda: user_override
    if session_override is not None:
        app.dependency_overrides[get_async_session] = lambda: session_override
    return app


def _mock_session():
    s = AsyncMock()
    s.execute = AsyncMock()
    s.commit = AsyncMock()
    s.refresh = AsyncMock()
    return s


# ══════════════════════════════════════════════════════════════════
# TestGetFrontendConfig
# ══════════════════════════════════════════════════════════════════


class TestGetFrontendConfig:
    """GET /config/frontend"""

    @pytest.mark.anyio
    async def test_returns_config(self, root_user):
        app = _create_app(user_override=root_user)

        with patch("app.api.endpoints.dashboard.settings") as mock_settings:
            mock_settings.frontend_polling_interval_seconds = 10
            mock_settings.checkpoint_interval_minutes = 5
            mock_settings.collection_interval_seconds = 30

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/config/frontend")

        assert resp.status_code == 200
        data = resp.json()
        assert data["polling_interval_seconds"] == 10
        assert data["checkpoint_interval_minutes"] == 5
        assert data["collection_interval_seconds"] == 30

    @pytest.mark.anyio
    async def test_returns_all_expected_keys(self, pm_user):
        app = _create_app(user_override=pm_user)

        with patch("app.api.endpoints.dashboard.settings") as mock_settings:
            mock_settings.frontend_polling_interval_seconds = 15
            mock_settings.checkpoint_interval_minutes = 10
            mock_settings.collection_interval_seconds = 60

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/config/frontend")

        assert resp.status_code == 200
        data = resp.json()
        expected_keys = {
            "polling_interval_seconds",
            "checkpoint_interval_minutes",
            "collection_interval_seconds",
        }
        assert set(data.keys()) == expected_keys


# ══════════════════════════════════════════════════════════════════
# TestGetMaintenanceSummary
# ══════════════════════════════════════════════════════════════════


class TestGetMaintenanceSummary:
    """GET /maintenance/{maintenance_id}/summary"""

    @pytest.mark.anyio
    async def test_returns_indicators(self, root_user):
        session = _mock_session()

        fake_summary = {
            "maintenance_id": "MAINT-001",
            "indicators": {
                "transceiver": {
                    "total_count": 100,
                    "pass_count": 95,
                    "fail_count": 5,
                    "pass_rate": 95.0,
                    "status": "warning",
                    "summary": "95% pass",
                    "collection_errors": 0,
                },
                "version": {
                    "total_count": 50,
                    "pass_count": 50,
                    "fail_count": 0,
                    "pass_rate": 100.0,
                    "status": "success",
                    "summary": "all pass",
                    "collection_errors": 0,
                },
            },
            "overall": {
                "total_count": 150,
                "pass_count": 145,
                "fail_count": 5,
                "pass_rate": 96.0,
                "status": "warning",
            },
        }

        app = _create_app(user_override=root_user, session_override=session)

        with patch(
            "app.api.endpoints.dashboard.IndicatorService"
        ) as MockService:
            instance = MockService.return_value
            instance.get_dashboard_summary = AsyncMock(return_value=fake_summary)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/maintenance/MAINT-001/summary")

        assert resp.status_code == 200
        data = resp.json()
        assert data["maintenance_id"] == "MAINT-001"
        assert "transceiver" in data["indicators"]
        assert "version" in data["indicators"]
        assert data["overall"]["pass_rate"] == 96.0

    @pytest.mark.anyio
    async def test_maintenance_access_checked(self, guest_user):
        """Guest accessing a maintenance they are NOT assigned to gets 403."""
        session = _mock_session()
        # guest_user is assigned to MAINT-001, so accessing MAINT-999 is forbidden
        app = _create_app(user_override=guest_user, session_override=session)

        with patch(
            "app.api.endpoints.dashboard.IndicatorService"
        ) as MockService:
            instance = MockService.return_value
            instance.get_dashboard_summary = AsyncMock(return_value={})

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/maintenance/MAINT-999/summary")

        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_guest_can_access_own_maintenance(self, guest_user):
        """Guest accessing their own assigned maintenance should succeed."""
        session = _mock_session()

        fake_summary = {
            "maintenance_id": "MAINT-001",
            "indicators": {},
            "overall": {
                "total_count": 0,
                "pass_count": 0,
                "fail_count": 0,
                "pass_rate": 0.0,
                "status": "error",
            },
        }

        app = _create_app(user_override=guest_user, session_override=session)

        with patch(
            "app.api.endpoints.dashboard.IndicatorService"
        ) as MockService:
            instance = MockService.return_value
            instance.get_dashboard_summary = AsyncMock(return_value=fake_summary)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/maintenance/MAINT-001/summary")

        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════
# TestGetIndicatorDetails
# ══════════════════════════════════════════════════════════════════


class TestGetIndicatorDetails:
    """GET /maintenance/{maintenance_id}/indicator/{indicator_type}/details"""

    @pytest.mark.anyio
    async def test_returns_details(self, root_user):
        session = _mock_session()

        fake_result = IndicatorEvaluationResult(
            indicator_type="transceiver",
            maintenance_id="MAINT-001",
            total_count=10,
            pass_count=8,
            fail_count=2,
            pass_rates={"tx_power": 90.0, "rx_power": 80.0},
            failures=[
                {"device": "SW01", "interface": "Gi1/0/1", "reason": "low power"},
                {"device": "SW02", "interface": "Gi1/0/2", "reason": "high temp"},
            ],
            passes=[
                {"device": "SW03", "interface": "Gi1/0/1"},
            ],
            summary="8/10 pass",
        )

        # Mock evaluate_all to return dict with the indicator
        fake_results = {"transceiver": fake_result}

        # Mock the CollectionError query — no collection errors
        err_mock_result = MagicMock()
        err_mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = err_mock_result

        app = _create_app(user_override=root_user, session_override=session)

        with patch(
            "app.api.endpoints.dashboard.IndicatorService"
        ) as MockService:
            instance = MockService.return_value
            instance.evaluate_all = AsyncMock(return_value=fake_results)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/maintenance/MAINT-001/indicator/transceiver/details"
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["indicator_type"] == "transceiver"
        assert data["total_count"] == 10
        assert data["pass_count"] == 8
        assert data["fail_count"] == 2
        assert len(data["failures"]) == 2
        assert data["collection_errors"] == 0

    @pytest.mark.anyio
    async def test_unknown_indicator_returns_error(self, root_user):
        session = _mock_session()

        # evaluate_all returns results without the requested indicator
        fake_results = {}

        err_mock_result = MagicMock()
        err_mock_result.scalars.return_value.all.return_value = []
        session.execute.return_value = err_mock_result

        app = _create_app(user_override=root_user, session_override=session)

        with patch(
            "app.api.endpoints.dashboard.IndicatorService"
        ) as MockService:
            instance = MockService.return_value
            instance.evaluate_all = AsyncMock(return_value=fake_results)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/maintenance/MAINT-001/indicator/nonexistent/details"
                )

        assert resp.status_code == 200
        data = resp.json()
        assert "error" in data

    @pytest.mark.anyio
    async def test_details_with_collection_errors(self, root_user):
        """Collection errors should be merged into the failure list."""
        session = _mock_session()

        fake_result = IndicatorEvaluationResult(
            indicator_type="transceiver",
            maintenance_id="MAINT-001",
            total_count=5,
            pass_count=4,
            fail_count=1,
            pass_rates={"tx_power": 80.0},
            failures=[
                {"device": "SW01", "interface": "Gi1/0/1", "reason": "low power"},
            ],
            passes=[],
            summary="4/5 pass",
        )

        fake_results = {"transceiver": fake_result}

        # Mock collection error: one error for a device NOT in failures
        ce = MagicMock()
        ce.switch_hostname = "SW99"
        ce.error_message = "Connection refused"
        err_mock_result = MagicMock()
        err_mock_result.scalars.return_value.all.return_value = [ce]
        session.execute.return_value = err_mock_result

        app = _create_app(user_override=root_user, session_override=session)

        with patch(
            "app.api.endpoints.dashboard.IndicatorService"
        ) as MockService:
            instance = MockService.return_value
            instance.evaluate_all = AsyncMock(return_value=fake_results)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/maintenance/MAINT-001/indicator/transceiver/details"
                )

        assert resp.status_code == 200
        data = resp.json()
        # Original failure + supplemental CE device
        assert len(data["failures"]) == 2
        assert data["collection_errors"] == 1
        # total adjusted: 5 + 1 supplement = 6
        assert data["total_count"] == 6

    @pytest.mark.anyio
    async def test_guest_wrong_maintenance_returns_403(self, guest_user):
        """Guest trying to access details for wrong maintenance."""
        session = _mock_session()
        app = _create_app(user_override=guest_user, session_override=session)

        with patch(
            "app.api.endpoints.dashboard.IndicatorService"
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/maintenance/MAINT-999/indicator/transceiver/details"
                )

        assert resp.status_code == 403
