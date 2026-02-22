"""
Unit tests for Thresholds API endpoints.

Tests GET, PUT, and POST /reset routes for per-maintenance threshold
configuration with mocked services and DB sessions.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, status
from httpx import ASGITransport, AsyncClient

from app.api.endpoints.auth import get_current_user, require_write
from app.api.endpoints.thresholds import router
from app.db.base import get_async_session


# ── Helpers ──────────────────────────────────────────────────────


def _create_app(user_override=None, session_override=None, *, writable: bool = True):
    """Build a throwaway FastAPI app wired to the thresholds router.

    Args:
        user_override: JWT-like payload dict for the current user.
        session_override: Mocked AsyncSession.
        writable: If True, the user passes the require_write check.
                  If False, require_write raises 403.
    """
    app = FastAPI()
    app.include_router(router)  # router already has prefix="/thresholds"
    if user_override is not None:
        app.dependency_overrides[get_current_user] = lambda: user_override

    # require_write() is a *factory* that returns a dependency.
    # We override the inner dependency produced by require_write().
    if writable and user_override is not None:
        # Allow write — return the user payload.
        _inner_dep = require_write()
        app.dependency_overrides[_inner_dep] = lambda: user_override
    elif not writable:
        # Block write — raise 403.
        _inner_dep = require_write()

        async def _reject():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="您沒有寫入權限",
            )
        app.dependency_overrides[_inner_dep] = _reject

    if session_override is not None:
        app.dependency_overrides[get_async_session] = lambda: session_override
    return app


def _mock_session():
    s = AsyncMock()
    s.execute = AsyncMock()
    s.commit = AsyncMock()
    s.refresh = AsyncMock()
    return s


def _sample_threshold_response(maintenance_id: str = "MAINT-001") -> dict:
    """Return a realistic threshold response structure."""
    return {
        "maintenance_id": maintenance_id,
        "transceiver": {
            "tx_power_min": {
                "value": -12.0,
                "default": -12.0,
                "is_override": False,
                "unit": "dBm",
                "description": "TX Power 下限",
            },
            "tx_power_max": {
                "value": 2.0,
                "default": 2.0,
                "is_override": False,
                "unit": "dBm",
                "description": "TX Power 上限",
            },
            "rx_power_min": {
                "value": -22.0,
                "default": -22.0,
                "is_override": False,
                "unit": "dBm",
                "description": "RX Power 下限",
            },
            "rx_power_max": {
                "value": 0.0,
                "default": 0.0,
                "is_override": False,
                "unit": "dBm",
                "description": "RX Power 上限",
            },
        },
    }


# ══════════════════════════════════════════════════════════════════
# TestGetThresholds
# ══════════════════════════════════════════════════════════════════


class TestGetThresholds:
    """GET /thresholds/{maintenance_id}"""

    @pytest.mark.anyio
    async def test_get_success(self, root_user):
        session = _mock_session()
        expected = _sample_threshold_response()

        app = _create_app(user_override=root_user, session_override=session)

        with patch(
            "app.api.endpoints.thresholds.load_thresholds",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/thresholds/MAINT-001")

        assert resp.status_code == 200
        data = resp.json()
        assert data["maintenance_id"] == "MAINT-001"
        assert "transceiver" in data

    @pytest.mark.anyio
    async def test_requires_auth(self):
        """Without any auth override the endpoint should return 403 (no token)."""
        session = _mock_session()
        # No user_override -> get_current_user is not overridden, so HTTPBearer
        # will fail because we don't send a Bearer token.
        app = FastAPI()
        app.include_router(router)  # router already has prefix="/thresholds"
        app.dependency_overrides[get_async_session] = lambda: session

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/thresholds/MAINT-001")

        assert resp.status_code in (401, 403)

    @pytest.mark.anyio
    async def test_pm_can_read(self, pm_user):
        """PM users should also be able to read thresholds."""
        session = _mock_session()
        expected = _sample_threshold_response()

        app = _create_app(user_override=pm_user, session_override=session)

        with patch(
            "app.api.endpoints.thresholds.load_thresholds",
            new_callable=AsyncMock,
            return_value=expected,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/thresholds/MAINT-001")

        assert resp.status_code == 200


# ══════════════════════════════════════════════════════════════════
# TestPutThresholds
# ══════════════════════════════════════════════════════════════════


class TestPutThresholds:
    """PUT /thresholds/{maintenance_id}"""

    @pytest.mark.anyio
    async def test_update_success(self, root_user):
        session = _mock_session()
        updated_response = _sample_threshold_response()
        updated_response["transceiver"]["tx_power_min"]["value"] = -15.0
        updated_response["transceiver"]["tx_power_min"]["is_override"] = True

        app = _create_app(
            user_override=root_user, session_override=session, writable=True
        )

        with (
            patch(
                "app.api.endpoints.thresholds.update_thresholds",
                new_callable=AsyncMock,
                return_value=updated_response,
            ),
            patch(
                "app.api.endpoints.thresholds.get_threshold",
                return_value=-12.0,
            ),
            patch(
                "app.api.endpoints.thresholds.get_default",
                return_value=-12.0,
            ),
            patch(
                "app.api.endpoints.thresholds.write_log",
                new_callable=AsyncMock,
            ) as mock_log,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.put(
                    "/thresholds/MAINT-001",
                    json={"transceiver_tx_power_min": -15.0},
                )

        assert resp.status_code == 200
        data = resp.json()
        assert data["transceiver"]["tx_power_min"]["value"] == -15.0
        # Verify write_log was called
        mock_log.assert_awaited_once()

    @pytest.mark.anyio
    async def test_requires_write_guest_rejected(self, guest_user):
        """GUEST users should be rejected with 403 for PUT."""
        session = _mock_session()

        app = _create_app(
            user_override=guest_user, session_override=session, writable=False
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/thresholds/MAINT-001",
                json={"transceiver_tx_power_min": -15.0},
            )

        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_update_with_null_clears_override(self, root_user):
        """Sending null for a field should clear the override (restore default)."""
        session = _mock_session()
        restored_response = _sample_threshold_response()

        app = _create_app(
            user_override=root_user, session_override=session, writable=True
        )

        with (
            patch(
                "app.api.endpoints.thresholds.update_thresholds",
                new_callable=AsyncMock,
                return_value=restored_response,
            ),
            patch(
                "app.api.endpoints.thresholds.get_threshold",
                return_value=-15.0,
            ),
            patch(
                "app.api.endpoints.thresholds.get_default",
                return_value=-12.0,
            ),
            patch(
                "app.api.endpoints.thresholds.write_log",
                new_callable=AsyncMock,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.put(
                    "/thresholds/MAINT-001",
                    json={"transceiver_tx_power_min": None},
                )

        assert resp.status_code == 200

    @pytest.mark.anyio
    async def test_validation_min_greater_than_max(self, root_user):
        """Pydantic validator should reject min >= max."""
        session = _mock_session()

        app = _create_app(
            user_override=root_user, session_override=session, writable=True
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.put(
                "/thresholds/MAINT-001",
                json={
                    "transceiver_tx_power_min": 5.0,
                    "transceiver_tx_power_max": -5.0,
                },
            )

        assert resp.status_code == 422  # Pydantic validation error


# ══════════════════════════════════════════════════════════════════
# TestResetThresholds
# ══════════════════════════════════════════════════════════════════


class TestResetThresholds:
    """POST /thresholds/{maintenance_id}/reset"""

    @pytest.mark.anyio
    async def test_reset_success(self, root_user):
        session = _mock_session()
        reset_response = _sample_threshold_response()

        app = _create_app(
            user_override=root_user, session_override=session, writable=True
        )

        with (
            patch(
                "app.api.endpoints.thresholds.reset_thresholds",
                new_callable=AsyncMock,
                return_value=reset_response,
            ),
            patch(
                "app.api.endpoints.thresholds.write_log",
                new_callable=AsyncMock,
            ) as mock_log,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post("/thresholds/MAINT-001/reset")

        assert resp.status_code == 200
        data = resp.json()
        assert data["maintenance_id"] == "MAINT-001"
        mock_log.assert_awaited_once()

    @pytest.mark.anyio
    async def test_requires_write_guest_rejected(self, guest_user):
        """GUEST users should be rejected with 403 for reset."""
        session = _mock_session()

        app = _create_app(
            user_override=guest_user, session_override=session, writable=False
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post("/thresholds/MAINT-001/reset")

        assert resp.status_code == 403

    @pytest.mark.anyio
    async def test_pm_can_reset(self, pm_user):
        """PM users should be allowed to reset thresholds (have write access)."""
        session = _mock_session()
        reset_response = _sample_threshold_response()

        app = _create_app(
            user_override=pm_user, session_override=session, writable=True
        )

        with (
            patch(
                "app.api.endpoints.thresholds.reset_thresholds",
                new_callable=AsyncMock,
                return_value=reset_response,
            ),
            patch(
                "app.api.endpoints.thresholds.write_log",
                new_callable=AsyncMock,
            ),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post("/thresholds/MAINT-001/reset")

        assert resp.status_code == 200
