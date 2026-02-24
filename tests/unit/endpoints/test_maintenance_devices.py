"""
Unit tests for Maintenance Devices API endpoints.

Tests cover:
- list devices (with search)
- stats
- add device (full mapping, new-only, write permission)
- update device
- delete single / batch-delete
- reachability status
- CSV export / import
"""
from __future__ import annotations

import io
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from app.api.endpoints.auth import get_current_user
from app.api.endpoints.maintenance_devices import router
from app.core.enums import TenantGroup
from app.db.base import get_async_session

# ── User payloads ──────────────────────────────────────────────

ROOT_USER = {
    "user_id": 1,
    "username": "root",
    "role": "ROOT",
    "maintenance_id": None,
    "display_name": "系統管理員",
    "is_root": True,
}
PM_USER = {
    "user_id": 2,
    "username": "pm1",
    "role": "PM",
    "maintenance_id": "MAINT-001",
    "display_name": "PM User",
    "is_root": False,
}
GUEST_USER = {
    "user_id": 3,
    "username": "guest1",
    "role": "GUEST",
    "maintenance_id": "MAINT-001",
    "display_name": "Guest",
    "is_root": False,
}

# ── Helpers ────────────────────────────────────────────────────


def _make_device(
    id: int = 1,
    maintenance_id: str = "MAINT-001",
    old_hostname: str | None = "SW-OLD-001",
    old_ip_address: str | None = "10.0.0.1",
    old_vendor: str | None = "HPE",
    new_hostname: str | None = "SW-NEW-001",
    new_ip_address: str | None = "10.0.0.2",
    new_vendor: str | None = "HPE",
    tenant_group: TenantGroup = TenantGroup.F18,
    description: str | None = None,
    is_replaced: bool = False,
    use_same_port: bool | None = None,
) -> MagicMock:
    """Create a mock MaintenanceDeviceList row."""
    d = MagicMock()
    d.id = id
    d.maintenance_id = maintenance_id
    d.old_hostname = old_hostname
    d.old_ip_address = old_ip_address
    d.old_vendor = old_vendor
    d.new_hostname = new_hostname
    d.new_ip_address = new_ip_address
    d.new_vendor = new_vendor
    d.tenant_group = tenant_group
    d.description = description
    d.is_replaced = is_replaced
    d.use_same_port = use_same_port
    d.created_at = datetime(2025, 1, 1)
    d.updated_at = datetime(2025, 1, 1)
    return d


def _build_app(user: dict) -> FastAPI:
    """Build a minimal FastAPI app with the maintenance-devices router and auth override."""
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: user
    return app


def _scalars_all(rows):
    """Mock result so .scalars().all() returns *rows*."""
    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    result.scalars.return_value = scalars
    return result


def _scalar_one_or_none(value):
    """Mock result so .scalar_one_or_none() returns *value*."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalar(value):
    """Mock result so .scalar() returns *value*."""
    result = MagicMock()
    result.scalar.return_value = value
    return result


# ══════════════════════════════════════════════════════════════════
# TestListDevices
# ══════════════════════════════════════════════════════════════════


class TestListDevices:
    """GET /api/maintenance-devices/{maintenance_id}"""

    @pytest.mark.anyio
    async def test_list_success(self):
        """GET -> 200 with devices array."""
        devices = [_make_device(id=1), _make_device(id=2, old_hostname="SW-OLD-002", new_hostname="SW-NEW-002")]
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_scalars_all(devices))

        app = _build_app(ROOT_USER)
        app.dependency_overrides[get_async_session] = lambda: session

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/maintenance-devices/MAINT-001")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["count"] == 2
        assert len(body["devices"]) == 2

    @pytest.mark.anyio
    async def test_list_with_search(self):
        """Search param -> 200."""
        device = _make_device(id=1)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_scalars_all([device]))

        app = _build_app(ROOT_USER)
        app.dependency_overrides[get_async_session] = lambda: session

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get(
                "/api/maintenance-devices/MAINT-001",
                params={"search": "SW-OLD"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["count"] == 1


# ══════════════════════════════════════════════════════════════════
# TestGetStats
# ══════════════════════════════════════════════════════════════════


class TestGetStats:
    """GET /api/maintenance-devices/{maintenance_id}/stats"""

    @pytest.mark.anyio
    async def test_stats(self):
        """-> 200 with device counts."""
        device = _make_device(id=1)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_scalars_all([device]))

        # PingRecordRepo.get_latest_per_device returns ping records
        mock_repo_instance = AsyncMock()
        mock_repo_instance.get_latest_per_device = AsyncMock(return_value=[])

        app = _build_app(ROOT_USER)
        app.dependency_overrides[get_async_session] = lambda: session

        # PingRecordRepo is imported locally inside the function body via
        # `from app.repositories.typed_records import PingRecordRepo`,
        # so we patch it at the source module.
        with patch(
            "app.repositories.typed_records.PingRecordRepo",
        ) as MockPingCls:
            MockPingCls.return_value = mock_repo_instance
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get("/api/maintenance-devices/MAINT-001/stats")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        # device has both old and new hostname -> total = 2
        assert body["total"] == 2
        assert body["old_count"] == 1
        assert body["new_count"] == 1


# ══════════════════════════════════════════════════════════════════
# TestAddDevice
# ══════════════════════════════════════════════════════════════════


class TestAddDevice:
    """POST /api/maintenance-devices/{maintenance_id}"""

    @pytest.mark.anyio
    async def test_add_full_mapping(self):
        """old+new -> 200."""
        session = AsyncMock()

        # validate_device_mapping queries:
        # 1. check old_hostname unique
        # 2. check new_hostname unique
        # 3. check old_ip unique
        # 4. check new_ip unique
        session.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(None),  # old_hostname not duplicate
                _scalar_one_or_none(None),  # new_hostname not duplicate
                _scalar_one_or_none(None),  # old_ip not duplicate
                _scalar_one_or_none(None),  # new_ip not duplicate
            ]
        )
        session.add = MagicMock()
        session.commit = AsyncMock()

        created_device = _make_device(id=10)
        session.refresh = AsyncMock(side_effect=lambda obj: _set_device_attrs(obj, created_device))

        app = _build_app(ROOT_USER)
        app.dependency_overrides[get_async_session] = lambda: session

        with patch(
            "app.api.endpoints.maintenance_devices.write_log",
            new_callable=AsyncMock,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/maintenance-devices/MAINT-001",
                    json={
                        "old_hostname": "SW-OLD-001",
                        "old_ip_address": "10.0.0.1",
                        "old_vendor": "HPE",
                        "new_hostname": "SW-NEW-001",
                        "new_ip_address": "10.0.0.2",
                        "new_vendor": "HPE",
                    },
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["device"]["old_hostname"] == "SW-OLD-001"

    @pytest.mark.anyio
    async def test_add_new_only(self):
        """Only new side -> 200."""
        session = AsyncMock()

        # validate_device_mapping: only new_hostname and new_ip checks
        session.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(None),  # new_hostname not duplicate
                _scalar_one_or_none(None),  # new_ip not duplicate
            ]
        )
        session.add = MagicMock()
        session.commit = AsyncMock()

        new_only_device = _make_device(
            id=11, old_hostname=None, old_ip_address=None, old_vendor=None,
        )
        session.refresh = AsyncMock(
            side_effect=lambda obj: _set_device_attrs(obj, new_only_device),
        )

        app = _build_app(PM_USER)
        app.dependency_overrides[get_async_session] = lambda: session

        with patch(
            "app.api.endpoints.maintenance_devices.write_log",
            new_callable=AsyncMock,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/maintenance-devices/MAINT-001",
                    json={
                        "new_hostname": "SW-NEW-011",
                        "new_ip_address": "10.0.1.1",
                        "new_vendor": "Cisco-IOS",
                    },
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

    @pytest.mark.anyio
    async def test_requires_write(self):
        """GUEST -> 403."""
        app = _build_app(GUEST_USER)

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/api/maintenance-devices/MAINT-001",
                json={
                    "new_hostname": "SW-NEW-099",
                    "new_ip_address": "10.0.9.1",
                    "new_vendor": "HPE",
                },
            )

        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════
# TestUpdateDevice
# ══════════════════════════════════════════════════════════════════


class TestUpdateDevice:
    """PUT /api/maintenance-devices/{maintenance_id}/{device_id}"""

    @pytest.mark.anyio
    async def test_update_success(self):
        """PUT -> 200."""
        existing = _make_device(id=5)
        session = AsyncMock()

        # Calls:
        # 1. find device
        # 2-5. validate_device_mapping (4 checks since we update hostname fields)
        session.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(existing),  # find
                _scalar_one_or_none(None),      # old_hostname unique
                _scalar_one_or_none(None),      # new_hostname unique
                _scalar_one_or_none(None),      # old_ip unique
                _scalar_one_or_none(None),      # new_ip unique
            ]
        )
        session.commit = AsyncMock()
        session.refresh = AsyncMock(
            side_effect=lambda obj: _set_device_attrs(obj, existing),
        )

        app = _build_app(ROOT_USER)
        app.dependency_overrides[get_async_session] = lambda: session

        with patch(
            "app.api.endpoints.maintenance_devices.write_log",
            new_callable=AsyncMock,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.put(
                    "/api/maintenance-devices/MAINT-001/5",
                    json={
                        "old_hostname": "SW-OLD-001",
                        "description": "updated description",
                    },
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True


# ══════════════════════════════════════════════════════════════════
# TestDeleteDevice
# ══════════════════════════════════════════════════════════════════


class TestDeleteDevice:
    """DELETE /api/maintenance-devices/{maintenance_id}/{device_id} and batch-delete."""

    @pytest.mark.anyio
    async def test_delete_single(self):
        """DELETE -> 200."""
        existing = _make_device(id=5)
        session = AsyncMock()

        # Calls:
        # 1. find device
        # 2. delete LatestCollectionBatch
        # 3. delete CollectionError
        session.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(existing),
                MagicMock(),   # delete LatestCollectionBatch
                MagicMock(),   # delete CollectionError
            ]
        )
        session.delete = AsyncMock()
        session.commit = AsyncMock()

        app = _build_app(ROOT_USER)
        app.dependency_overrides[get_async_session] = lambda: session

        with patch(
            "app.api.endpoints.maintenance_devices.write_log",
            new_callable=AsyncMock,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.delete("/api/maintenance-devices/MAINT-001/5")

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

    @pytest.mark.anyio
    async def test_batch_delete(self):
        """POST batch-delete -> 200."""
        session = AsyncMock()

        # Calls:
        # 1. get hostnames for IDs -> .all()
        hostname_row = MagicMock()
        hostname_row.new_hostname = "SW-NEW-001"
        hostname_row.old_hostname = "SW-OLD-001"
        hostname_result = MagicMock()
        hostname_result.all.return_value = [hostname_row]

        delete_batch_result = MagicMock()
        delete_batch_result.rowcount = 1

        session.execute = AsyncMock(
            side_effect=[
                hostname_result,     # hostname query
                MagicMock(),         # delete LatestCollectionBatch
                MagicMock(),         # delete CollectionError
                delete_batch_result, # delete devices
            ]
        )
        session.commit = AsyncMock()

        app = _build_app(ROOT_USER)
        app.dependency_overrides[get_async_session] = lambda: session

        with patch(
            "app.api.endpoints.maintenance_devices.write_log",
            new_callable=AsyncMock,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/maintenance-devices/MAINT-001/batch-delete",
                    json={"device_ids": [1]},
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["deleted_count"] == 1


# ══════════════════════════════════════════════════════════════════
# TestReachabilityStatus
# ══════════════════════════════════════════════════════════════════


class TestReachabilityStatus:
    """GET /api/maintenance-devices/{maintenance_id}/reachability-status"""

    @pytest.mark.anyio
    async def test_get_status(self):
        """-> 200 with hostname map."""
        session = AsyncMock()

        # PingRecordRepo.get_latest_per_device returns ping records
        ping_record = MagicMock()
        ping_record.switch_hostname = "SW-NEW-001"
        ping_record.is_reachable = True
        ping_record.collected_at = datetime(2025, 1, 15, 10, 0)

        mock_repo = AsyncMock()
        mock_repo.get_latest_per_device = AsyncMock(return_value=[ping_record])

        app = _build_app(ROOT_USER)
        app.dependency_overrides[get_async_session] = lambda: session

        with patch(
            "app.repositories.typed_records.PingRecordRepo",
        ) as MockPingCls:
            MockPingCls.return_value = mock_repo
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.get(
                    "/api/maintenance-devices/MAINT-001/reachability-status"
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert "SW-NEW-001" in body["devices"]
        assert body["devices"]["SW-NEW-001"]["is_reachable"] is True


# ══════════════════════════════════════════════════════════════════
# TestImportExportCsv
# ══════════════════════════════════════════════════════════════════


class TestImportExportCsv:
    """CSV import/export endpoints."""

    @pytest.mark.anyio
    async def test_export_csv(self):
        """-> 200 CSV."""
        device = _make_device(id=1)
        session = AsyncMock()
        session.execute = AsyncMock(return_value=_scalars_all([device]))

        app = _build_app(ROOT_USER)
        app.dependency_overrides[get_async_session] = lambda: session

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.get("/api/maintenance-devices/MAINT-001/export-csv")

        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        body_text = resp.text
        assert "old_hostname" in body_text
        assert "SW-OLD-001" in body_text

    @pytest.mark.anyio
    async def test_import_csv(self):
        """-> 200 with counts."""
        session = AsyncMock()

        csv_content = (
            "old_hostname,old_ip_address,old_vendor,new_hostname,new_ip_address,new_vendor,tenant_group,description\n"
            "SW-OLD-100,10.0.100.1,HPE,SW-NEW-100,10.0.100.2,HPE,F18,test device\n"
        )

        # Calls during import:
        # 1. check existing by old_hostname -> scalar_one_or_none (None)
        # 2. check existing by new_hostname -> scalar_one_or_none (None)
        # 3-6. validate_device_mapping (4 checks)
        session.execute = AsyncMock(
            side_effect=[
                _scalar_one_or_none(None),  # no existing by old_hostname
                _scalar_one_or_none(None),  # no existing by new_hostname
                _scalar_one_or_none(None),  # old_hostname unique
                _scalar_one_or_none(None),  # new_hostname unique
                _scalar_one_or_none(None),  # old_ip unique
                _scalar_one_or_none(None),  # new_ip unique
            ]
        )
        session.add = MagicMock()
        session.commit = AsyncMock()

        app = _build_app(ROOT_USER)
        app.dependency_overrides[get_async_session] = lambda: session

        with patch(
            "app.api.endpoints.maintenance_devices.write_log",
            new_callable=AsyncMock,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/maintenance-devices/MAINT-001/import-csv",
                    files={
                        "file": ("devices.csv", csv_content.encode(), "text/csv"),
                    },
                )

        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        assert body["imported"] == 1
        assert body["total_errors"] == 0


# ── Utility ────────────────────────────────────────────────────


def _set_device_attrs(target, source):
    """Copy relevant attributes from *source* mock onto *target* ORM object."""
    for attr in (
        "id", "maintenance_id",
        "old_hostname", "old_ip_address", "old_vendor",
        "new_hostname", "new_ip_address", "new_vendor",
        "is_replaced", "use_same_port", "tenant_group",
        "description", "created_at", "updated_at",
    ):
        try:
            setattr(target, attr, getattr(source, attr))
        except AttributeError:
            pass
