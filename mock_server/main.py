"""
NETORA Mock API Server — Production-faithful fake data server.

暴露與真實 FNA / DNA / GNMS Ping 完全相同的 URL 結構，
只有回傳的 raw data 是模擬的。

FNA 路由 (5):
    GET /switch/network/get_gbic_details/{switch_ip}
    Authorization: Bearer <token>
    → text/plain (CLI output)

DNA 路由 (20):
    GET /api/v1/hpe/environment/display_fan?hosts=10.1.1.1
    → text/plain (JSON-like TextFSM output)

GNMS Ping:
    POST /api/v1/ping  (JSON body)
    → text/plain (CSV)

啟動:
    uvicorn mock_server.main:app --host 0.0.0.0 --port 9999
"""
from __future__ import annotations

import logging
from typing import Callable

from fastapi import FastAPI, Query, Request, Response

from mock_server import db
from mock_server.config import settings
from mock_server.steady_state import should_fail_steady
from mock_server.generators import (
    channel_group,
    dynamic_acl,
    error_count,
    fan,
    gbic_details,
    gnms_ping,
    interface_status,
    mac_table,
    ping_batch,
    power,
    static_acl,
    uplink,
    version,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="NETORA Mock API Server",
    description="Production-faithful mock — 相同 URL 結構，模擬回傳資料",
    version="3.0.0",
)

# ── Generator Registry ──────────────────────────────────────────────
# api_name → generator function
# 每個 generator 接受: (device_type, fails, **kwargs) → str
GENERATORS: dict[str, Callable[..., str]] = {
    "get_gbic_details": gbic_details.generate,
    "get_channel_group": channel_group.generate,
    "get_uplink": uplink.generate,  # legacy
    "get_uplink_lldp": uplink.generate_lldp,
    "get_uplink_cdp": uplink.generate_cdp,
    "get_error_count": error_count.generate,
    "get_static_acl": static_acl.generate,
    "get_dynamic_acl": dynamic_acl.generate,
    "get_mac_table": mac_table.generate,
    "get_fan": fan.generate,
    "get_power": power.generate,
    "get_version": version.generate,
    "ping_batch": ping_batch.generate,
    "get_interface_status": interface_status.generate,
    "gnms_ping": gnms_ping.generate,
}


# ── Shared Core Handler ─────────────────────────────────────────────

def _generate_response(
    api_name: str,
    switch_ip: str,
    device_type: str,
    maintenance_id: str,
) -> Response:
    """
    Core mock response generation.

    Used by FNA, DNA, and legacy handlers.
    Looks up the generator, queries failure state from DB, and returns text/plain.
    """
    generator = GENERATORS.get(api_name)
    if generator is None:
        return Response(
            content=f"Unknown API: {api_name}",
            status_code=404,
            media_type="text/plain",
        )

    if not switch_ip:
        return Response(
            content="switch_ip is required",
            status_code=422,
            media_type="text/plain",
        )

    # 從 DB 查詢活躍時間（用於決定故障出現時機）
    # DNA 路由不帶 maintenance_id → active_seconds=0.0
    active_seconds = db.get_active_seconds(maintenance_id) if maintenance_id else 0.0

    fails = should_fail_steady(
        switch_ip, api_name, active_seconds,
        settings.mock_steady_failure_rate,
        settings.mock_steady_onset_range,
    )

    kwargs: dict[str, object] = {
        "device_type": device_type,
        "fails": fails,
        "switch_ip": switch_ip,
    }

    # uplink: 從 DB 讀取期望鄰居
    if api_name in ("get_uplink", "get_uplink_lldp", "get_uplink_cdp") and maintenance_id:
        expected = db.get_uplink_neighbors(maintenance_id, switch_ip)
        if expected:
            kwargs["expected_neighbors"] = expected

    # mac_table: 從 DB 讀取 MAC 清單
    if api_name == "get_mac_table" and maintenance_id:
        kwargs["mac_list"] = db.get_mac_list(maintenance_id)

    output = generator(**kwargs)

    logger.debug(
        "%s for %s (device_type=%s, fails=%s, elapsed=%.0fs)",
        api_name, switch_ip, device_type, fails, active_seconds,
    )

    return Response(content=output, media_type="text/plain")


# ── FNA Routes (5) ──────────────────────────────────────────────────
# Pattern: GET /switch/network/{command}/{switch_ip}
# Auth: Bearer token（接受但不驗證）
# ConfiguredFetcher 模板不含 '?' → 自動附加 device_type, maintenance_id 等 query params

FNA_ROUTES: dict[str, str] = {
    "/switch/network/get_gbic_details/{switch_ip}": "get_gbic_details",
    "/switch/network/get_channel_group/{switch_ip}": "get_channel_group",
    "/switch/network/get_interface_error_count/{switch_ip}": "get_error_count",
    "/switch/network/get_static_acl/{switch_ip}": "get_static_acl",
    "/switch/network/get_dynamic_acl/{switch_ip}": "get_dynamic_acl",
}


def _make_fna_handler(api_name: str):  # noqa: ANN202
    """Factory: create a handler for an FNA route."""

    async def handler(
        switch_ip: str,
        device_type: str = Query("hpe"),
        maintenance_id: str = Query(""),
    ) -> Response:
        return _generate_response(api_name, switch_ip, device_type, maintenance_id)

    handler.__name__ = f"fna_{api_name}"
    handler.__qualname__ = f"fna_{api_name}"
    return handler


for _path, _api_name in FNA_ROUTES.items():
    app.add_api_route(_path, _make_fna_handler(_api_name), methods=["GET"], tags=["FNA"])


# ── DNA Routes (20) ─────────────────────────────────────────────────
# Pattern: GET /api/v1/{device_type}/{category}/{command}?hosts={switch_ip}
# Auth: 無
# ConfiguredFetcher 模板含 '?' → 顯式模式，只送 hosts，不送 maintenance_id

DNA_ROUTES: list[dict[str, str]] = [
    # get_mac_table (3)
    {"path": "/api/v1/hpe/macaddress/display_macaddress", "api_name": "get_mac_table", "device_type": "hpe"},
    {"path": "/api/v1/ios/macaddress/show_mac_address_table", "api_name": "get_mac_table", "device_type": "ios"},
    {"path": "/api/v1/nxos/macaddress/show_mac_address_table", "api_name": "get_mac_table", "device_type": "nxos"},
    # get_fan (3)
    {"path": "/api/v1/hpe/environment/display_fan", "api_name": "get_fan", "device_type": "hpe"},
    {"path": "/api/v1/ios/environment/show_env_fan", "api_name": "get_fan", "device_type": "ios"},
    {"path": "/api/v1/nxos/environment/show_environment_fan", "api_name": "get_fan", "device_type": "nxos"},
    # get_power (3)
    {"path": "/api/v1/hpe/environment/display_power", "api_name": "get_power", "device_type": "hpe"},
    {"path": "/api/v1/ios/environment/show_env_power", "api_name": "get_power", "device_type": "ios"},
    {"path": "/api/v1/nxos/environment/show_environment_power", "api_name": "get_power", "device_type": "nxos"},
    # get_version (3)
    {"path": "/api/v1/hpe/version/display_version", "api_name": "get_version", "device_type": "hpe"},
    {"path": "/api/v1/ios/version/show_version", "api_name": "get_version", "device_type": "ios"},
    {"path": "/api/v1/nxos/version/show_version", "api_name": "get_version", "device_type": "nxos"},
    # get_interface_status (3)
    {"path": "/api/v1/hpe/interface/display_interface_brief", "api_name": "get_interface_status", "device_type": "hpe"},
    {"path": "/api/v1/ios/interface/show_interface_status", "api_name": "get_interface_status", "device_type": "ios"},
    {"path": "/api/v1/nxos/interface/show_interface_status", "api_name": "get_interface_status", "device_type": "nxos"},
    # get_uplink_lldp (3)
    {"path": "/api/v1/hpe/neighbor/display_lldp_neighbor-information_list", "api_name": "get_uplink_lldp", "device_type": "hpe"},
    {"path": "/api/v1/ios/neighbor/show_lldp_neighbors", "api_name": "get_uplink_lldp", "device_type": "ios"},
    {"path": "/api/v1/nxos/neighbor/show_lldp_neighbors", "api_name": "get_uplink_lldp", "device_type": "nxos"},
    # get_uplink_cdp (2 — HPE 不支援 CDP)
    {"path": "/api/v1/ios/neighbor/show_cdp_neighbors", "api_name": "get_uplink_cdp", "device_type": "ios"},
    {"path": "/api/v1/nxos/neighbor/show_cdp_neighbors", "api_name": "get_uplink_cdp", "device_type": "nxos"},
]


def _make_dna_handler(api_name: str, device_type: str):  # noqa: ANN202
    """Factory: create a handler for a DNA route."""

    async def handler(
        hosts: str = Query(..., description="Switch IP"),
    ) -> Response:
        # DNA 路由不帶 maintenance_id → 自動推斷活躍歲修
        mid = db.get_active_maintenance_id()
        return _generate_response(api_name, hosts, device_type, maintenance_id=mid)

    handler.__name__ = f"dna_{api_name}_{device_type}"
    handler.__qualname__ = f"dna_{api_name}_{device_type}"
    return handler


for _route in DNA_ROUTES:
    app.add_api_route(
        _route["path"],
        _make_dna_handler(_route["api_name"], _route["device_type"]),
        methods=["GET"],
        tags=["DNA"],
    )


# ── GNMS Ping (POST + JSON body) ────────────────────────────────────

@app.post("/api/v1/ping", tags=["GNMS Ping"])
async def mock_gnms_ping(request: Request) -> Response:
    """
    Mock GNMS Ping — POST + JSON body。

    真實 API 格式:
        POST /api/v1/ping
        {"app_name": "...", "token": "...", "addresses": ["10.1.1.1", ...]}
    """
    body = await request.json()
    addresses = body.get("addresses", [])
    switch_ips = ",".join(addresses) if addresses else None

    output = gnms_ping.generate(
        device_type="",
        fails=False,
        switch_ips=switch_ips,
        failure_rate=settings.mock_steady_failure_rate,
    )
    return Response(content=output, media_type="text/plain")


# ── Legacy: ping_batch (internal) ───────────────────────────────────

@app.get("/api/ping_batch", tags=["Legacy"])
def mock_ping_batch(
    switch_ip: str = Query(...),
    device_type: str = Query("hpe"),
    maintenance_id: str = Query(""),
) -> Response:
    """Legacy ping_batch endpoint（不屬於 FNA/DNA，內部測試用）。"""
    return _generate_response("ping_batch", switch_ip, device_type, maintenance_id)


# ── Health Check ─────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    """健康檢查。"""
    return {
        "status": "ok",
        "service": "mock-api",
        "version": "3.0.0",
        "steady_failure_rate": settings.mock_steady_failure_rate,
        "steady_onset_range": settings.mock_steady_onset_range,
        "fna_routes": list(FNA_ROUTES.values()),
        "dna_routes": len(DNA_ROUTES),
        "apis": list(GENERATORS.keys()),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "mock_server.main:app",
        host="0.0.0.0",
        port=settings.mock_server_port,
        reload=True,
    )
