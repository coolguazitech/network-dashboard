"""
NETORA Mock API Server — 獨立的假資料伺服器。

提供與真實 FNA/DNA API 相同格式的 CLI 文字回應，
使用穩態模擬模式，偶爾出現持續性故障。

統一 API:
    GET /api/{api_name}?switch_ip={ip}&device_type={type}&maintenance_id={mid}
    → Response: text/plain (CLI 原始輸出)

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
    description="提供假的網路設備 CLI 輸出，穩態模擬模式",
    version="2.0.0",
)

# API name → generator function 的對應
# 每個 generator 接受: (device_type, fails, **kwargs)
GENERATORS: dict[str, Callable[..., str]] = {
    "get_gbic_details": gbic_details.generate,
    "get_channel_group": channel_group.generate,
    "get_uplink": uplink.generate,  # legacy (backwards compat)
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


@app.get("/api/{api_name}")
def mock_api(
    api_name: str,
    switch_ip: str | None = Query(None, description="設備 IP（gnms_ping 不需要）"),
    device_type: str = Query("hpe", description="設備類型: hpe, ios, nxos"),
    maintenance_id: str = Query(..., description="歲修 ID"),
    switch_ips: str | None = Query(None, description="逗號分隔的 IP 清單（gnms_ping 用）"),
) -> Response:
    """
    統一的 Mock API 端點。

    根據 api_name 調用對應的 generator，
    使用 should_fail_steady() 決定設備是否故障。
    """
    generator = GENERATORS.get(api_name)
    if generator is None:
        return Response(
            content=f"Unknown API: {api_name}",
            status_code=404,
            media_type="text/plain",
        )

    # gnms_ping 不需要 switch_ip；其他 API 必須有
    if api_name != "gnms_ping" and not switch_ip:
        return Response(
            content="switch_ip is required",
            status_code=422,
            media_type="text/plain",
        )

    # 從 DB 查詢活躍時間（用於決定故障出現時機）
    active_seconds = db.get_active_seconds(maintenance_id)

    # 使用 should_fail_steady() 決定此設備+API 是否故障
    fails = should_fail_steady(
        switch_ip or "", api_name, active_seconds,
        settings.mock_steady_failure_rate,
        settings.mock_steady_onset_range,
    )

    # 產生 CLI 文字
    kwargs: dict[str, object] = {
        "device_type": device_type,
        "fails": fails,
        "switch_ip": switch_ip or "",
    }
    if api_name == "gnms_ping":
        kwargs["switch_ips"] = switch_ips
        kwargs["failure_rate"] = settings.mock_steady_failure_rate
    # uplink: 從 DB 讀取期望鄰居
    if api_name in ("get_uplink", "get_uplink_lldp", "get_uplink_cdp"):
        expected = db.get_uplink_neighbors(maintenance_id, switch_ip)
        if expected:
            kwargs["expected_neighbors"] = expected
    # mac_table: 從 DB 讀取 MAC 清單
    if api_name == "get_mac_table":
        kwargs["mac_list"] = db.get_mac_list(maintenance_id)

    output = generator(**kwargs)

    logger.debug(
        "%s for %s (device_type=%s, fails=%s, elapsed=%.0fs)",
        api_name, switch_ip, device_type, fails, active_seconds,
    )

    return Response(content=output, media_type="text/plain")


@app.post("/api/v1/ping")
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


@app.get("/health")
def health() -> dict:
    """健康檢查。"""
    return {
        "status": "ok",
        "service": "mock-api",
        "steady_failure_rate": settings.mock_steady_failure_rate,
        "steady_onset_range": settings.mock_steady_onset_range,
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
