"""
ConfiguredFetcher — 泛用 Fetcher，從 .env 讀取設定。

取代原本每個資料類型都要手寫一個 Fetcher class 的做法。
一個 ConfiguredFetcher instance 對應 scheduler.yaml 中的一筆 fetcher entry。

啟動時由 setup_fetchers() 動態建立並註冊到 fetcher_registry。

HTTP 行為：
- 所有 API 統一使用 GET
- endpoint 模板從 settings.fetcher_endpoint.{fetch_type} 讀取
- 模板中的佔位符 {switch_ip}, {tenant_group} 等會從 FetchContext 帶入路徑
  （固定欄位 switch_ip / device_type / tenant_group + ctx.params 中的任意 key 皆可用）
- 未被佔位符消耗的變數自動成為 query params
- base_url 和 timeout 從 settings.fetcher_source.{source} 讀取

範例：
    endpoint 模板: /api/v1/transceiver/{switch_ip}
    FetchContext:   switch_ip="10.1.1.1", device_type="hpe"

    → GET http://fna:8001/api/v1/transceiver/10.1.1.1?device_type=hpe
"""
from __future__ import annotations

import logging
import re

import httpx

from app.core.config import settings
from app.fetchers.base import BaseFetcher, FetchContext, FetchResult

logger = logging.getLogger(__name__)

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
        endpoint_template = getattr(
            settings.fetcher_endpoint,
            self.fetch_type,
            "",
        )
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
            **ctx.params,  # 允許動態覆蓋或添加額外變數
        }
        # ctx.params 中的同名 key 會覆蓋上面的預設值

        # ── Resolve placeholders in endpoint path ──
        placeholders = set(_PLACEHOLDER_RE.findall(endpoint_template))
        endpoint = endpoint_template.format(
            **{k: all_vars[k] for k in placeholders if k in all_vars},
        )
        url = source_config.base_url.rstrip("/") + endpoint

        # ── Remaining vars → query params ──
        query_params: dict[str, object] = {
            k: v for k, v in all_vars.items() if k not in placeholders
        }

        # ── GET request ──
        timeout = source_config.timeout

        try:
            client = ctx.http or httpx.AsyncClient(timeout=timeout)
            own_client = ctx.http is None

            try:
                resp = await client.get(url, params=query_params, timeout=timeout)
                resp.raise_for_status()
                return FetchResult(raw_output=resp.text)
            finally:
                if own_client:
                    await client.aclose()

        except httpx.HTTPStatusError as e:
            return FetchResult(
                raw_output="",
                success=False,
                error=f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            )
        except httpx.TimeoutException:
            return FetchResult(
                raw_output="",
                success=False,
                error=f"Timeout after {timeout}s for {ctx.switch_ip} ({self.fetch_type})",
            )
        except Exception as e:
            return FetchResult(
                raw_output="",
                success=False,
                error=f"{type(e).__name__}: {e}",
            )

    def __repr__(self) -> str:
        return (
            f"<ConfiguredFetcher {self.fetch_type} "
            f"source={self.source_name}>"
        )
