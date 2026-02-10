"""
Dev Tools API Endpoints.

提供開發測試工具，用於快速驗證 Parser 和 Fetcher 的正確性。
"""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.enums import DeviceType
from app.fetchers.base import FetchContext
from app.fetchers.registry import fetcher_registry
from app.parsers.registry import parser_registry

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================


class TestParserRequest(BaseModel):
    """測試 Parser 的請求 (選項 1)"""

    parser_type: str = Field(
        ...,
        description="Parser 類型 (如 mac_table, arp_table, transceiver)",
        examples=["arp_table", "mac_table", "transceiver"],
    )
    device_type: DeviceType | None = Field(
        None,
        description="設備類型 (如 hpe, nxos, ios)。若不指定則嘗試使用 generic parser",
    )
    raw_output: str = Field(
        ...,
        description="外部 API 的 raw output（直接貼上）",
    )


class TestFetchAndParseRequest(BaseModel):
    """測試 Fetch + Parse 的請求 (選項 2)"""

    fetcher_type: str = Field(
        ...,
        description="Fetcher 類型 (如 mac_table, arp_table)",
        examples=["arp_table", "mac_table"],
    )
    switch_ip: str = Field(
        ...,
        description="交換機 IP 地址",
        examples=["10.0.0.1"],
    )
    device_type: DeviceType = Field(
        ...,
        description="設備類型 (如 hpe, nxos, ios)",
    )
    headers: dict[str, str] | None = Field(
        None,
        description="HTTP headers（含 token），例如 {'Authorization': 'Bearer xxx'}",
    )


class TestParserResponse(BaseModel):
    """Parser 測試結果"""

    success: bool = Field(..., description="是否成功")
    parser_used: str = Field(..., description="使用的 Parser")
    parsed_count: int = Field(..., description="解析出的記錄數")
    parsed_items: list[dict] = Field(..., description="解析結果（JSON 格式）")
    error: str | None = Field(None, description="錯誤訊息（如果失敗）")


class TestFetchAndParseResponse(BaseModel):
    """Fetch + Parse 測試結果"""

    success: bool = Field(..., description="是否成功")
    fetcher_used: str = Field(..., description="使用的 Fetcher")
    parser_used: str = Field(..., description="使用的 Parser")
    raw_output: str = Field(..., description="Fetcher 返回的 raw output")
    parsed_count: int = Field(..., description="解析出的記錄數")
    parsed_items: list[dict] = Field(..., description="解析結果（JSON 格式）")
    error: str | None = Field(None, description="錯誤訊息（如果失敗）")


# ============================================================================
# Endpoints
# ============================================================================


@router.post(
    "/dev/test-parser",
    response_model=TestParserResponse,
    summary="測試 Parser（選項 1）",
    description="""
    快速測試 Parser 是否正確解析外部 API 的 raw output。

    **使用場景**：
    - 你用 curl 拿到外部 API 的 raw output
    - 想快速驗證 Parser 是否正確解析
    - 不需要配置 maintenance、devices、MAC list 等

    **步驟**：
    1. curl 外部 API（自己處理 token）
    2. 把 raw output 貼到這個 endpoint
    3. 立即看到 Parser 的解析結果

    **範例**：
    ```bash
    # 1. 拿到 raw output
    curl -H "Authorization: Bearer $TOKEN" \\
      http://fna/switch/network/get_arp_table/10.0.0.1 > arp.txt

    # 2. 測試 Parser
    curl -X POST http://localhost:8000/api/dev/test-parser \\
      -H "Content-Type: application/json" \\
      -d '{
        "parser_type": "arp_table",
        "device_type": "hpe",
        "raw_output": "'"$(cat arp.txt)"'"
      }'
    ```
    """,
)
async def test_parser(request: TestParserRequest) -> TestParserResponse:
    """測試 Parser（只測試解析邏輯，不涉及 Fetch）"""
    try:
        # 1. 取得 Parser
        parser = parser_registry.get(
            device_type=request.device_type,  # type: ignore
            indicator_type=request.parser_type,
        )
        if parser is None:
            raise HTTPException(
                status_code=404,
                detail=f"No parser found for device_type={request.device_type}, "
                f"parser_type={request.parser_type}. "
                f"Available parsers: {parser_registry.list_parsers()}",
            )

        # 2. 解析
        parsed_items = parser.parse(request.raw_output)

        # 3. 轉換為 JSON（使用 Pydantic model_dump）
        parsed_json = [
            item.model_dump() if hasattr(item, "model_dump") else item
            for item in parsed_items
        ]

        return TestParserResponse(
            success=True,
            parser_used=f"{parser.__class__.__name__} (device_type={request.device_type}, parser_type={request.parser_type})",
            parsed_count=len(parsed_items),
            parsed_items=parsed_json,
            error=None,
        )

    except HTTPException:
        raise
    except Exception as e:
        return TestParserResponse(
            success=False,
            parser_used=f"device_type={request.device_type}, parser_type={request.parser_type}",
            parsed_count=0,
            parsed_items=[],
            error=str(e),
        )


@router.post(
    "/dev/test-fetch-and-parse",
    response_model=TestFetchAndParseResponse,
    summary="測試 Fetch + Parse（選項 2）",
    description="""
    測試完整流程：Fetch（呼叫外部 API）+ Parse（解析結果）。

    **使用場景**：
    - 想測試完整的 Fetch + Parse 流程
    - 需要傳入 token（透過 headers）

    **步驟**：
    1. 提供 switch_ip, device_type, headers（含 token）
    2. 系統自動呼叫外部 API
    3. 返回 raw output + parsed result

    **範例**：
    ```bash
    curl -X POST http://localhost:8000/api/dev/test-fetch-and-parse \\
      -H "Content-Type: application/json" \\
      -d '{
        "fetcher_type": "arp_table",
        "switch_ip": "10.0.0.1",
        "device_type": "hpe",
        "headers": {
          "Authorization": "Bearer YOUR_FNA_TOKEN"
        }
      }'
    ```
    """,
)
async def test_fetch_and_parse(
    request: TestFetchAndParseRequest,
) -> TestFetchAndParseResponse:
    """測試 Fetch + Parse（完整流程，含 token）"""
    try:
        # 1. 取得 Fetcher
        fetcher = fetcher_registry.get(request.fetcher_type)
        if fetcher is None:
            raise HTTPException(
                status_code=404,
                detail=f"No fetcher found for '{request.fetcher_type}'. "
                f"Available fetchers: {fetcher_registry.list_fetchers()}",
            )

        # 2. 建立 HTTP client（含 headers）
        async with httpx.AsyncClient(
            headers=request.headers or {},
            timeout=30.0,
        ) as http:
            # 3. 建立 FetchContext
            ctx = FetchContext(
                switch_ip=request.switch_ip,
                switch_hostname="test-switch",  # 測試用
                device_type=request.device_type,
                http=http,
            )

            # 4. Fetch
            fetch_result = await fetcher.fetch(ctx)
            if not fetch_result.success:
                raise HTTPException(
                    status_code=500,
                    detail=f"Fetch failed: {fetch_result.error}",
                )

            # 5. 取得 Parser
            parser = parser_registry.get(
                device_type=request.device_type,
                indicator_type=request.fetcher_type,
            )
            if parser is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"No parser found for device_type={request.device_type}, "
                    f"parser_type={request.fetcher_type}",
                )

            # 6. Parse
            parsed_items = parser.parse(fetch_result.raw_output)

            # 7. 轉換為 JSON
            parsed_json = [
                item.model_dump() if hasattr(item, "model_dump") else item
                for item in parsed_items
            ]

            return TestFetchAndParseResponse(
                success=True,
                fetcher_used=f"{fetcher.__class__.__name__} (fetch_type={request.fetcher_type})",
                parser_used=f"{parser.__class__.__name__} (device_type={request.device_type}, parser_type={request.fetcher_type})",
                raw_output=fetch_result.raw_output,
                parsed_count=len(parsed_items),
                parsed_items=parsed_json,
                error=None,
            )

    except HTTPException:
        raise
    except Exception as e:
        return TestFetchAndParseResponse(
            success=False,
            fetcher_used=f"fetcher_type={request.fetcher_type}",
            parser_used=f"device_type={request.device_type}, parser_type={request.fetcher_type}",
            raw_output="",
            parsed_count=0,
            parsed_items=[],
            error=str(e),
        )
