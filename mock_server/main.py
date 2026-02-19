"""
NETORA Mock API Server — 獨立的假資料伺服器。

提供與真實 FNA/DNA API 相同格式的 CLI 文字回應，
支援兩種模式：
  - convergence: 基於歲修累計活躍時間的收斂行為
  - steady_state: 穩態模擬，偶爾出現持續性故障

統一 API:
    GET /api/{api_name}?switch_ip={ip}&device_type={type}&maintenance_id={mid}
    → Response: text/plain (CLI 原始輸出)

啟動:
    uvicorn mock_server.main:app --host 0.0.0.0 --port 9999
"""
from __future__ import annotations

import logging
from typing import Callable

from fastapi import FastAPI, Query, Response

from mock_server import db
from mock_server.config import settings
from mock_server.convergence import should_device_fail
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
    description="提供假的網路設備 CLI 輸出，支援時間收斂和穩態兩種模式",
    version="1.1.0",
)

# API name → generator function 的對應
# 每個 generator 接受: (device_type, is_old, active_seconds, converge_time, **kwargs)
GENERATORS: dict[str, Callable[..., str]] = {
    "get_gbic_details": gbic_details.generate,
    "get_channel_group": channel_group.generate,
    "get_uplink": uplink.generate,
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

# Ping 是從監控主機發起，不需要連進設備，永遠可以嘗試
_REACHABILITY_EXEMPT_APIS = {"ping_batch", "gnms_ping"}


@app.get("/api/{api_name}")
def mock_api(
    api_name: str,
    switch_ip: str = Query(..., description="設備 IP"),
    device_type: str = Query("hpe", description="設備類型: hpe, ios, nxos"),
    maintenance_id: str = Query(..., description="歲修 ID"),
    switch_ips: str | None = Query(None, description="逗號分隔的 IP 清單（gnms_ping 用）"),
) -> Response:
    """
    統一的 Mock API 端點。

    根據 api_name 調用對應的 generator，
    結合當前模式（convergence 或 steady_state）產生資料。
    """
    generator = GENERATORS.get(api_name)
    if generator is None:
        return Response(
            content=f"Unknown API: {api_name}",
            status_code=404,
            media_type="text/plain",
        )

    # 從 DB 查詢活躍時間（兩種模式都需要）
    active_seconds = db.get_active_seconds(maintenance_id)
    converge_time = float(settings.mock_converge_time)

    if settings.mock_mode == "steady_state":
        # ── 穩態模式 ──
        # 所有設備皆可達（不回 504）。
        # should_fail_steady() 決定哪些設備+API 組合故障。
        # 技巧：is_old=True → generator 內的 should_device_fail() 產出故障資料
        #        is_old=False → 健康資料
        # active_seconds 設為極大值，讓收斂函數行為確定。
        is_old = should_fail_steady(
            switch_ip, api_name, active_seconds,
            settings.mock_steady_failure_rate,
            settings.mock_steady_onset_range,
        )
        active_seconds = converge_time * 10  # 遠超收斂點
    else:
        # ── 收斂模式（原始行為）──
        is_old = db.get_device_role(maintenance_id, switch_ip)

        # 不可達判斷：ping 以外的 API 都需要連進設備才能採集
        # 如果設備不可達，直接回 504 模擬連線超時
        device_unreachable = should_device_fail(is_old, active_seconds, converge_time)
        if device_unreachable and api_name not in _REACHABILITY_EXEMPT_APIS:
            logger.debug(
                "%s for %s SKIPPED (device unreachable, is_old=%s, elapsed=%.0fs)",
                api_name, switch_ip, is_old, active_seconds,
            )
            return Response(
                content=f"Connection timed out: {switch_ip}",
                status_code=504,
                media_type="text/plain",
            )

    # 產生 CLI 文字
    import inspect
    sig = inspect.signature(generator)
    kwargs: dict[str, object] = {
        "device_type": device_type,
        "is_old": is_old,
        "active_seconds": active_seconds,
        "converge_time": converge_time,
    }
    if "switch_ip" in sig.parameters:
        kwargs["switch_ip"] = switch_ip
    if "switch_ips" in sig.parameters:
        kwargs["switch_ips"] = switch_ips
    # uplink: 從 DB 讀取期望鄰居，讓 mock 產出正確的鄰居主機名
    if api_name == "get_uplink":
        expected = db.get_uplink_neighbors(maintenance_id, switch_ip)
        if expected:
            kwargs["expected_neighbors"] = expected
    # mac_table: 從 DB 讀取 MAC 清單，讓 mock 回傳與使用者匯入的 MAC 一致的資料
    if api_name == "get_mac_table":
        kwargs["mac_list"] = db.get_mac_list(maintenance_id)
    # gnms_ping 穩態模式：每個 client IP 獨立判斷，與設備可達性無關
    if api_name == "gnms_ping" and settings.mock_mode == "steady_state":
        kwargs["steady_state_failure_rate"] = settings.mock_steady_failure_rate
    output = generator(**kwargs)

    logger.debug(
        "%s for %s (mode=%s, device_type=%s, is_old=%s, elapsed=%.0fs)",
        api_name, switch_ip, settings.mock_mode, device_type, is_old, active_seconds,
    )

    return Response(content=output, media_type="text/plain")


@app.get("/health")
def health() -> dict:
    """健康檢查。"""
    return {
        "status": "ok",
        "service": "mock-api",
        "mode": settings.mock_mode,
        "converge_time": settings.mock_converge_time,
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
