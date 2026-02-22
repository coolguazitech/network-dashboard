"""
Integration tests for Auth API — real SQLite DB, real AuthService logic.

Tests the full request flow: HTTP request -> FastAPI router -> AuthService -> DB.
Uses an in-memory SQLite database via aiosqlite.
"""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.api.endpoints.auth import get_current_user, router
from app.core.enums import UserRole
from app.db.base import Base, get_async_session
from app.db.models import MaintenanceConfig, User
from app.services.auth_service import AuthService

# ══════════════════════════════════════════════════════════════════
# Test DB setup
# ══════════════════════════════════════════════════════════════════

TEST_DB_URL = (
    "sqlite+aiosqlite:///file:test_auth?mode=memory&cache=shared&uri=true"
)


def _build_app():
    """Build a FastAPI app with the auth router for integration testing."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router)  # router already has prefix="/auth"
    return app


@pytest.fixture
async def test_engine():
    """Create a test async engine and initialize all tables."""
    engine = create_async_engine(TEST_DB_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    # Teardown: drop all tables to ensure clean state between tests
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest.fixture
async def test_session(test_engine):
    """Create a test async session bound to the test engine."""
    async_session_factory = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with async_session_factory() as session:
        yield session


@pytest.fixture
async def app_client(test_engine):
    """
    Provide an httpx AsyncClient wired to use the test DB.

    The get_async_session dependency is overridden to use our test engine.
    AuthService methods that use get_session_context are also patched.
    """
    from unittest.mock import patch
    from contextlib import asynccontextmanager

    async_session_factory = sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async def override_get_async_session():
        async with async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    @asynccontextmanager
    async def override_get_session_context():
        async with async_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = _build_app()
    app.dependency_overrides[get_async_session] = override_get_async_session

    # Patch get_session_context used by AuthService and write_log
    with (
        patch("app.services.auth_service.get_session_context", override_get_session_context),
        patch("app.services.system_log.get_session_context", override_get_session_context),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client


# ══════════════════════════════════════════════════════════════════
# test_full_login_flow
# ══════════════════════════════════════════════════════════════════


class TestFullLoginFlow:
    """
    Integration test: init root -> login -> get /me -> change password -> re-login.
    """

    @pytest.mark.asyncio
    async def test_full_login_flow(self, app_client: AsyncClient):
        """
        End-to-end flow:
        1. POST /auth/init-root  -> creates root user
        2. POST /auth/login      -> login with root/admin123
        3. GET  /auth/me         -> verify user info
        4. PUT  /auth/change-password -> change from admin123 to newpass456
        5. POST /auth/login      -> login with root/newpass456
        """
        # Step 1: Init root
        resp = await app_client.post("/auth/init-root")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["username"] == "root"
        assert "Root 帳號已就緒" in body["message"]

        # Step 1b: Init root again should return existing (idempotent)
        resp = await app_client.post("/auth/init-root")
        assert resp.status_code == 200
        assert resp.json()["username"] == "root"

        # Step 2: Login with default credentials
        resp = await app_client.post(
            "/auth/login",
            json={"username": "root", "password": "admin123"},
        )
        assert resp.status_code == 200, resp.text
        login_body = resp.json()
        token = login_body["token"]
        assert token  # non-empty string
        assert login_body["user"]["username"] == "root"
        assert login_body["user"]["role"] == "ROOT"
        assert login_body["user"]["is_root"] is True

        # Step 3: Get /me
        resp = await app_client.get(
            "/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        me_body = resp.json()
        assert me_body["username"] == "root"
        assert me_body["role"] == "ROOT"
        assert me_body["is_root"] is True

        # Step 4: Change password
        resp = await app_client.put(
            "/auth/change-password",
            json={"old_password": "admin123", "new_password": "newpass456"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, resp.text
        assert "密碼變更成功" in resp.json()["message"]

        # Step 5: Login with new password
        resp = await app_client.post(
            "/auth/login",
            json={"username": "root", "password": "newpass456"},
        )
        assert resp.status_code == 200, resp.text
        new_token = resp.json()["token"]
        assert new_token  # non-empty
        # Note: tokens may be identical if generated in the same second
        # with the same claims — that's fine, we just verify login works

        # Step 5b: Old password should fail now
        resp = await app_client.post(
            "/auth/login",
            json={"username": "root", "password": "admin123"},
        )
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════
# test_guest_registration_flow
# ══════════════════════════════════════════════════════════════════


class TestGuestRegistrationFlow:
    """
    Integration test: create maintenance -> register guest -> verify inactive.
    """

    @pytest.mark.asyncio
    async def test_guest_registration_flow(
        self, app_client: AsyncClient, test_session: AsyncSession
    ):
        """
        Flow:
        1. Insert a MaintenanceConfig row (prerequisite for guest registration)
        2. POST /auth/register-guest  -> register a guest user
        3. POST /auth/login           -> should fail (inactive account)
        4. POST /auth/register-guest  -> duplicate username should fail
        """
        # Step 1: Create a maintenance config directly in the DB
        maintenance = MaintenanceConfig(
            maintenance_id="MAINT-TEST",
            name="Test Maintenance",
            is_active=True,
        )
        test_session.add(maintenance)
        await test_session.commit()

        # Step 2: Register a guest user
        resp = await app_client.post(
            "/auth/register-guest",
            json={
                "username": "testguest",
                "password": "guestpass",
                "maintenance_id": "MAINT-TEST",
                "display_name": "Test Guest",
                "email": "guest@example.com",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["username"] == "testguest"
        assert body["maintenance_id"] == "MAINT-TEST"
        assert "註冊成功" in body["message"]

        # Step 3: Try to login -- should fail because account is inactive
        resp = await app_client.post(
            "/auth/login",
            json={"username": "testguest", "password": "guestpass"},
        )
        assert resp.status_code == 401
        assert "啟用" in resp.json()["detail"]

        # Step 4: Duplicate registration should fail
        resp = await app_client.post(
            "/auth/register-guest",
            json={
                "username": "testguest",
                "password": "guestpass",
                "maintenance_id": "MAINT-TEST",
            },
        )
        assert resp.status_code == 400
        assert "已存在" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_register_nonexistent_maintenance(self, app_client: AsyncClient):
        """Registering with a non-existent maintenance_id should fail."""
        resp = await app_client.post(
            "/auth/register-guest",
            json={
                "username": "nobody",
                "password": "pass",
                "maintenance_id": "DOES-NOT-EXIST",
            },
        )
        assert resp.status_code == 400
        assert "不存在" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_maintenances_public_lists_configs(
        self, app_client: AsyncClient, test_session: AsyncSession
    ):
        """
        GET /auth/maintenances-public should return maintenance configs
        inserted into the test DB.
        """
        # Insert two configs
        m1 = MaintenanceConfig(
            maintenance_id="PUB-001",
            name="Public One",
            is_active=True,
        )
        m2 = MaintenanceConfig(
            maintenance_id="PUB-002",
            name="Public Two",
            is_active=False,
        )
        test_session.add_all([m1, m2])
        await test_session.commit()

        resp = await app_client.get("/auth/maintenances-public")
        assert resp.status_code == 200
        body = resp.json()
        ids = [item["id"] for item in body]
        assert "PUB-001" in ids
        assert "PUB-002" in ids
