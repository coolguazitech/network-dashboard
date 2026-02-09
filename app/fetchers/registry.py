"""
Fetcher Registry.

管理 fetch_type → BaseFetcher 的映射。
應用啟動時呼叫 setup_fetchers() 根據 USE_MOCK_API 註冊 mock 或 real fetcher。

★ 啟動流程
==========

::

    main.py (lifespan)
        → setup_fetchers(use_mock=settings.use_mock_api, fetcher_configs=...)
            ├─ use_mock=True  → mock.register_mock_fetchers()    # 開發/測試
            │                     → 註冊 13 個 MockFetcher
            │                     → MockTimeTracker.reset()       # 重置收斂計時器
            └─ use_mock=False → ConfiguredFetcher per scheduler.yaml entry  # 正式環境

    之後 scheduler 觸發時：
        data_collection._collect_for_switch(fetch_type="transceiver")
            → fetcher_registry.get_or_raise("transceiver")
                → 回傳對應的 Fetcher 實例（Mock 或 Real，取決於啟動時的註冊）

★ fetch_type 命名規範
======================

fetch_type 必須同時匹配以下三處（否則資料無法正確流動）：

1. scheduler.yaml 中的 fetcher name::

       # config/scheduler.yaml
       fetchers:
         transceiver:        # ← 這個 name 就是 fetch_type
           source: FNA
           interval: 120

2. .env 中的 endpoint 模板::

       FETCHER_ENDPOINT__TRANSCEIVER=/api/v1/transceiver/{switch_ip}

3. Parser class 的 indicator_type 屬性::

       class HpeTransceiverParser(BaseParser[TransceiverData]):
           indicator_type = "transceiver"  # ← 必須匹配

目前已註冊的 fetch_type:
    FNA:  transceiver, port_channel, acl
    DNA:  version, uplink, fan, power, error_count, mac_table, interface_status, arp_table
    Ping: ping, gnms_ping (mock only)

★ 如何新增 Fetcher Type
========================

1. 在 config/scheduler.yaml 新增 fetcher entry（source + interval）
   若 source 為新的外部 API（不在 FNA/DNA/GNMSPING 之中），需額外：
   a. 在 .env 加 FETCHER_SOURCE__{SOURCE}__BASE_URL 和 __TIMEOUT
   b. 在 app/core/config.py 的 FetcherSourceConfig 加對應的欄位
2. 在 .env 新增 FETCHER_ENDPOINT__{NAME}=... endpoint 模板
   支援佔位符: {switch_ip}, {device_type}, {tenant_group} 等
   （ctx.params 中的任意 key 亦可用；未消耗的變數自動成為 query params）
3. 在 app/parsers/plugins/ 新增 Parser（indicator_type = 你的 fetch_type）
4. 完成！ConfiguredFetcher 自動處理 GET 呼叫。
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.fetchers.base import BaseFetcher

logger = logging.getLogger(__name__)


class FetcherRegistry:
    """
    fetch_type → BaseFetcher 的註冊表。

    全域唯一實例 (module-level singleton)，透過 fetcher_registry 變數存取。

    使用方式::

        from app.fetchers.registry import fetcher_registry

        # 取得 Fetcher（找不到回傳 None）
        fetcher = fetcher_registry.get("transceiver")

        # 取得 Fetcher（找不到拋出 ValueError）
        fetcher = fetcher_registry.get_or_raise("transceiver")

        # 列出所有已註冊的 fetch_type
        types = fetcher_registry.list_fetchers()
        # → ["acl", "arp_table", "error_count", "fan", ...]

        # 檢查 fetch_type 是否已註冊
        if "transceiver" in fetcher_registry:
            ...
    """

    def __init__(self) -> None:
        self._fetchers: dict[str, BaseFetcher] = {}

    def register(self, fetcher: BaseFetcher) -> None:
        """註冊一個 Fetcher。"""
        self._fetchers[fetcher.fetch_type] = fetcher
        logger.debug("Registered fetcher: %s", fetcher.fetch_type)

    def get(self, fetch_type: str) -> BaseFetcher | None:
        """依 fetch_type 查詢 Fetcher，找不到回傳 None。"""
        return self._fetchers.get(fetch_type)

    def get_or_raise(self, fetch_type: str) -> BaseFetcher:
        """依 fetch_type 查詢 Fetcher，找不到拋出 ValueError。"""
        fetcher = self._fetchers.get(fetch_type)
        if fetcher is None:
            available = ", ".join(sorted(self._fetchers.keys()))
            raise ValueError(
                f"No fetcher registered for '{fetch_type}'. "
                f"Available: [{available}]"
            )
        return fetcher

    def list_fetchers(self) -> list[str]:
        """列出所有已註冊的 fetch_type。"""
        return sorted(self._fetchers.keys())

    def clear(self) -> None:
        """清除所有已註冊的 Fetcher（用於測試或重新初始化）。"""
        self._fetchers.clear()

    def __len__(self) -> int:
        return len(self._fetchers)

    def __contains__(self, fetch_type: str) -> bool:
        return fetch_type in self._fetchers


# Module-level singleton
fetcher_registry = FetcherRegistry()


def setup_fetchers(
    use_mock: bool,
    fetcher_configs: dict | None = None,
) -> None:
    """
    應用啟動時呼叫。根據 use_mock 註冊 mock 或 real fetcher。

    Args:
        use_mock: True = 註冊 MockFetcher (開發/測試)
                  False = 註冊 ConfiguredFetcher (正式環境)
        fetcher_configs: scheduler.yaml 中的 fetchers section
            {name: {source}} — 用於建立 ConfiguredFetcher
    """
    fetcher_registry.clear()

    if use_mock:
        from app.fetchers.convergence import MockTimeTracker
        from app.fetchers.mock import register_mock_fetchers

        MockTimeTracker.reset()
        register_mock_fetchers()
        logger.info(
            "Registered %d mock fetchers: %s",
            len(fetcher_registry),
            fetcher_registry.list_fetchers(),
        )
    else:
        from app.fetchers.configured import ConfiguredFetcher

        for name, config in (fetcher_configs or {}).items():
            fetcher = ConfiguredFetcher(
                fetch_type=name,
                source_name=config["source"],
            )
            fetcher_registry.register(fetcher)

        logger.info(
            "Registered %d configured fetchers: %s",
            len(fetcher_registry),
            fetcher_registry.list_fetchers(),
        )
