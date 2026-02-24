"""
ConfiguredFetcher — 泛用 Fetcher，從 .env 讀取設定。

取代原本每個資料類型都要手寫一個 Fetcher class 的做法。
一個 ConfiguredFetcher instance 對應 scheduler.yaml 中的一筆 fetcher entry。

啟動時由 setup_fetchers() 動態建立並註冊到 fetcher_registry。

HTTP 行為：
- 所有 API 統一使用 GET
- endpoint 模板從 settings.fetcher_endpoint.{fetch_type} 讀取
- 模板中的佔位符 {switch_ip}, {tenant_group} 等會從 FetchContext 帶入
  （固定欄位 switch_ip / device_type / tenant_group + ctx.params 中的任意 key 皆可用）
- base_url 和 timeout 從 settings.fetcher_source.{source} 讀取

Query params 規則：
- 模板含 '?' → 顯式模式：query params 已寫在模板中，不自動附加
- 模板不含 '?' → 自動模式：未消耗的變數自動成為 query params（mock server 相容）

範例（FNA — IP 在 path 中）:
    模板: /switch/network/get_gbic_details/{switch_ip}
    → GET http://fna:8001/switch/network/get_gbic_details/10.1.1.1
      Authorization: Bearer <token>

範例（DNA — 顯式 query params）:
    模板: /api/v1/hpe/environment/display_fan?hosts={switch_ip}
    → GET http://dna:8001/api/v1/hpe/environment/display_fan?hosts=10.1.1.1

範例（Mock — 自動附加 query params）:
    模板: /api/get_fan
    → GET http://mock:9999/api/get_fan?switch_ip=10.1.1.1&device_type=hpe&...
"""
from __future__ import annotations

import asyncio
import logging
import re

import httpx

from app.core.config import settings
from app.fetchers.base import BaseFetcher, FetchContext, FetchResult

logger = logging.getLogger(__name__)

# 暫態錯誤：值得重試的例外類型
_TRANSIENT_ERRORS = (
    httpx.ConnectError,
    httpx.TimeoutException,
    ConnectionError,
    OSError,
)

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


class ConfiguredFetcher(BaseFetcher):
    """
    Generic fetcher that makes GET calls to external APIs.

    Dynamically instantiated per fetch_type from scheduler.yaml.
    Reads endpoint template from settings.fetcher_endpoint.{fetch_type}.
    Reads base_url/timeout from settings.fetcher_source.{source}.
    """

    def __init__(self, fetch_type: str, source_name: str):
        self.fetch_type = fetch_type
        self.source_name = source_name

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        # ── Source config (base_url, timeout) ──
        source_config = getattr(
            settings.fetcher_source,
            self.source_name.lower(),
            None,
        )
        if source_config is None:
            return FetchResult(
                raw_output="",
                success=False,
                error=f"Unknown source '{self.source_name}' for fetcher '{self.fetch_type}'",
            )

        # ── Endpoint template ──
        # FNA: str (e.g. "/switch/network/get_fan/{switch_ip}")
        # DNA: str | dict[str, str] — dict 時以 device_type 為 key 查找
        endpoint_raw = getattr(
            settings.fetcher_endpoint,
            self.fetch_type,
            "",
        )
        if isinstance(endpoint_raw, dict):
            endpoint_template = endpoint_raw.get(
                ctx.device_type.api_value, "",
            )
        else:
            endpoint_template = endpoint_raw or ""
        if not endpoint_template:
            return FetchResult(
                raw_output="",
                success=False,
                error=f"No endpoint configured for fetcher '{self.fetch_type}'",
            )

        # ── Build substitution variables ──
        # 固定欄位 + ctx.params 合併，任意 key 皆可作為佔位符
        # 設計原則：無腦提供所有可能的佔位符，讓 endpoint 模板自由選用
        all_vars: dict[str, object] = {
            "switch_ip": ctx.switch_ip,
            "ip": ctx.switch_ip,  # 常用別名
            "hostname": ctx.switch_hostname,
            "device_type": ctx.device_type.api_value,
            "tenant_group": (
                ctx.tenant_group.value
                if ctx.tenant_group is not None
                else "default"
            ),
            "maintenance_id": ctx.maintenance_id or "",
            **ctx.params,  # 允許動態覆蓋或添加額外變數
        }
        # ctx.params 中的同名 key 會覆蓋上面的預設值

        # ── Resolve placeholders in endpoint path ──
        placeholders = set(_PLACEHOLDER_RE.findall(endpoint_template))
        endpoint = endpoint_template.format(
            **{k: all_vars[k] for k in placeholders if k in all_vars},
        )
        url = source_config.base_url.rstrip("/") + endpoint

        # ── Query params ──
        # 顯式模式（模板含 '?'）：query params 已在 URL 中，不再附加
        # 自動模式（模板不含 '?'）：未消耗的變數自動成為 query params（mock 相容）
        if "?" in endpoint_template:
            query_params: dict[str, object] = {}
        else:
            query_params = {
                k: v for k, v in all_vars.items() if k not in placeholders
            }

        # ── Headers (FNA Bearer token) ──
        headers: dict[str, str] = {}
        if source_config.token:
            headers["Authorization"] = f"Bearer {source_config.token}"

        # ── GET request (with retry for transient errors) ──
        timeout = source_config.timeout
        max_retries = 2
        last_error: Exception | None = None

        for attempt in range(max_retries + 1):
            try:
                client = ctx.http or httpx.AsyncClient(
                    timeout=timeout, verify=False,
                )
                own_client = ctx.http is None

                try:
                    resp = await client.get(
                        url, params=query_params,
                        headers=headers, timeout=timeout,
                    )
                    resp.raise_for_status()
                    return FetchResult(raw_output=resp.text)
                finally:
                    if own_client:
                        await client.aclose()

            except httpx.HTTPStatusError as e:
                # 伺服器明確回應錯誤 → 不重試
                return FetchResult(
                    raw_output="",
                    success=False,
                    error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
                )
            except _TRANSIENT_ERRORS as e:
                last_error = e
                if attempt < max_retries:
                    wait = (attempt + 1) * 1.0  # 1s, 2s
                    logger.warning(
                        "Transient error fetching %s from %s (attempt %d/%d, "
                        "retry in %.0fs): %s",
                        self.fetch_type, ctx.switch_ip,
                        attempt + 1, max_retries + 1, wait, e,
                    )
                    await asyncio.sleep(wait)
                    continue
                # 重試用盡
                break
            except Exception as e:
                return FetchResult(
                    raw_output="",
                    success=False,
                    error=f"{type(e).__name__}: {e}",
                )

        # 重試全部失敗 → 回傳最後的錯誤
        return FetchResult(
            raw_output="",
            success=False,
            error=f"Failed after {max_retries + 1} attempts: {last_error}",
        )

    def __repr__(self) -> str:
        return (
            f"<ConfiguredFetcher {self.fetch_type} "
            f"source={self.source_name}>"
        )
