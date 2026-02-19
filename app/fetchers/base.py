"""
Fetcher base classes.

定義 Fetcher 抽象層的核心型別：
- BaseFetcher: 所有 Fetcher 的基底類別
- FetchContext: 每次 fetch 的上下文（switch 資訊 + 額外參數）
- FetchResult: fetch 回傳結果

ConfiguredFetcher 繼承 BaseFetcher，在 fetch() 中根據
.env 的設定呼叫外部 API（GET + 佔位符路徑 + auto query params）。

★ 開發指南：如何新增一個 Fetcher
=================================

整體架構（資料流）::

    scheduler.yaml 定義 fetcher name + source + interval
    .env 定義 FETCHER_ENDPOINT__{NAME}=endpoint 模板（含佔位符）
        → data_collection._collect_for_maintenance_device(collection_type="xxx")
            → fetcher_registry.get_or_raise("xxx")
                → ConfiguredFetcher.fetch(ctx) → FetchResult(raw_output="...")
                    → parser_registry.get(device_type, "xxx")
                        → YourParser.parse(raw_output) → list[ParsedData]

新增 Fetcher 步驟：
    1. 在 config/scheduler.yaml 加一筆 fetcher entry（source + interval）
       若 source 為新的外部 API（不在 FNA/DNA 之中），需額外：
       a. 在 .env 加 FETCHER_SOURCE__{SOURCE}__BASE_URL 和 __TIMEOUT
       b. 在 app/core/config.py 的 FetcherSourceConfig 加對應的欄位
    2. 在 .env 加一筆 FETCHER_ENDPOINT__{NAME}=... endpoint 模板
       支援佔位符: {switch_ip}, {device_type}, {tenant_group} 等
       （ctx.params 中的任意 key 亦可用；未消耗的變數自動成為 query params）
    3. 在 app/parsers/plugins/ 寫對應的 Parser
    4. 完成！ConfiguredFetcher 自動處理 GET 呼叫。

Mock 模式：
    將 FETCHER_SOURCE__FNA__BASE_URL 和 DNA 指向獨立的 Mock API Server，
    endpoint 模板改為 /api/{api_name}。Mock Server 會自動處理收斂行為。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.core.enums import DeviceType, TenantGroup

if TYPE_CHECKING:
    import httpx


class FetchContext(BaseModel):
    """
    每次 fetch 呼叫的上下文。

    由框架（data_collection._collect_for_maintenance_device）建立並傳入 Fetcher.fetch()，
    包含目標設備資訊和可選的 HTTP client。

    設計原則：
    - 所有核心佔位符變數（switch_ip, device_type, tenant_group 等）都是**必傳的**
    - 使用 Pydantic 驗證確保所有地方都必須傳入這些變數
    - endpoint 模板可以自由選用任意佔位符，不需要修改代碼

    ★ 支援的佔位符變數（ConfiguredFetcher 自動提供）
    ================================================

    核心欄位（必傳）：
    - {switch_ip}: 設備 IP 地址
    - {ip}: switch_ip 的別名
    - {hostname}: 設備 hostname
    - {device_type}: 設備類型（hpe/ios/nxos）
    - {tenant_group}: 租戶群組（f18/f9/etc）
    - {maintenance_id}: 歲修 ID

    可選欄位：
    - params 字典中的任意 key 也可作為佔位符
    - 未被佔位符消耗的變數自動成為 query params

    Attributes:
        switch_ip: 目標 switch IP（必傳）
        switch_hostname: 目標 switch hostname（必傳，用於存入 DB）
        device_type: 設備類型（必傳）
        tenant_group: 租戶群組（必傳）
        maintenance_id: 歲修 ID（可選，傳遞給 API 作為 query param）
        params: 額外參數字典（可選）
        http: httpx.AsyncClient（可選，由框架注入）
    """

    # 核心欄位（必傳）
    switch_ip: str
    switch_hostname: str
    device_type: DeviceType
    tenant_group: TenantGroup

    # 可選欄位
    maintenance_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    http: Any = None  # httpx.AsyncClient，使用 Any 避免 Pydantic 序列化問題

    class Config:
        arbitrary_types_allowed = True  # 允許 httpx.AsyncClient 等非 Pydantic 類型


@dataclass
class FetchResult:
    """
    Fetcher 回傳結果。

    成功 (success=True, 預設值)::
        raw_output 會被傳給 Parser.parse() 解析成 list[ParsedData]。

    失敗 (success=False)::
        框架會建立 CollectionError 記錄，顯示在 dashboard 上（紫色狀態）。
        error 欄位應包含人類可讀的錯誤描述。

    Attributes:
        raw_output: API 回傳的原始字串（交給 Parser 解析）。
        success: 是否成功。預設 True。False 時框架會記錄 CollectionError。
        error: 失敗時的錯誤訊息。
    """

    raw_output: str
    success: bool = True
    error: str | None = None


class BaseFetcher(ABC):
    """
    所有 Fetcher 的基底類別。

    Class Attributes:
        fetch_type: 此 Fetcher 處理的資料類型 (e.g. "transceiver", "mac_table")
            ★ 重要：fetch_type 必須同時匹配以下三處：
            1. scheduler.yaml 中的 fetcher name
            2. parser_registry 中的 indicator_type
            3. fetcher_registry 中的 key
    """

    fetch_type: str

    @abstractmethod
    async def fetch(self, ctx: FetchContext) -> FetchResult:
        """
        呼叫外部 API 取得原始資料。

        Args:
            ctx: 包含 switch 資訊和額外參數。

        Returns:
            FetchResult: raw_output 包含 API 回傳的原始字串
        """
        ...
