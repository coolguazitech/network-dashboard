"""
Fetcher base classes.

定義 Fetcher 抽象層的核心型別：
- BaseFetcher: 所有 Fetcher 的基底類別
- FetchContext: 每次 fetch 的上下文（switch 資訊 + HTTP client + 額外參數）
- FetchResult: fetch 回傳結果

使用者只需繼承 BaseFetcher 並實作 fetch() 方法即可對接外部 API。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class FetchContext:
    """
    每次 fetch 呼叫的上下文。

    由框架建立並傳入 Fetcher.fetch()，包含目標設備資訊和可選的 HTTP client。

    Attributes:
        switch_ip: 目標 switch IP
        switch_hostname: 目標 switch hostname
        site: 站點識別碼 (e.g. "t_site", "m_site")
        source: 資料來源 (e.g. "FNA", "DNA")
        brand: 設備品牌 (e.g. "HPE", "Cisco-IOS", "Cisco-NXOS")
        vendor: 廠牌 (e.g. "hpe", "cisco")
        platform: 平台 (e.g. "hpe_comware", "cisco_nxos")
        params: 額外參數 (e.g. {"target_ips": [...]} for ping_many)
        http: HTTP client（由框架注入，mock fetcher 不需要）
        base_url: 外部 API 基底 URL
        timeout: HTTP 請求 timeout（秒）
    """

    switch_ip: str
    switch_hostname: str
    site: str
    source: str | None = None
    brand: str | None = None
    vendor: str | None = None
    platform: str | None = None
    params: dict[str, Any] = field(default_factory=dict)
    http: httpx.AsyncClient | None = None
    base_url: str = ""
    timeout: int = 30


@dataclass
class FetchResult:
    """
    Fetcher 回傳結果。

    Attributes:
        raw_output: API 回傳的原始字串（交給 Parser 解析）
        success: 是否成功
        error: 失敗時的錯誤訊息
    """

    raw_output: str
    success: bool = True
    error: str | None = None


class BaseFetcher(ABC):
    """
    所有 Fetcher 的基底類別。

    繼承此類別並實作 fetch() 方法來對接你的外部 API。
    框架會在排程觸發時呼叫 fetch()，將 FetchResult.raw_output 交給 Parser 解析。

    Class Attributes:
        fetch_type: 此 Fetcher 處理的資料類型 (e.g. "transceiver", "mac_table")

    Example::

        class MyTransceiverFetcher(BaseFetcher):
            fetch_type = "transceiver"

            async def fetch(self, ctx: FetchContext) -> FetchResult:
                resp = await ctx.http.get(
                    f"{ctx.base_url}/api/v1/transceiver",
                    params={"device_ip": ctx.switch_ip},
                )
                return FetchResult(raw_output=resp.text)
    """

    fetch_type: str

    @abstractmethod
    async def fetch(self, ctx: FetchContext) -> FetchResult:
        """
        呼叫外部 API 取得原始資料。

        Args:
            ctx: 包含 switch 資訊、HTTP client、額外參數

        Returns:
            FetchResult: raw_output 包含 API 回傳的原始字串
        """
        ...
