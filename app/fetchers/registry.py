"""
Fetcher Registry.

管理 fetch_type → BaseFetcher 的映射。
應用啟動時呼叫 setup_fetchers() 註冊 ConfiguredFetcher。

★ fetch_type 命名規範（get_* 命名，兩處必須一致）
=================================================

1. scheduler.yaml 的 fetcher key::

       fetchers:
         get_fan:          # ← fetch_type
           source: DNA

2. .env 的 endpoint 模板::

       FETCHER_ENDPOINT__GET_FAN=/api/v1/fan/{switch_ip}

目前已註冊的 fetch_type（11 個）:
    FNA (6): get_gbic_details, get_channel_group, get_uplink, get_error_count,
             get_static_acl, get_dynamic_acl
    DNA (4): get_mac_table, get_fan, get_power, get_version
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
        # → ["acl", "error_count", "fan", ...]

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
    fetcher_configs: dict | None = None,
) -> None:
    """
    應用啟動時呼叫。註冊 ConfiguredFetcher。

    Args:
        fetcher_configs: scheduler.yaml 中的 fetchers section
            {name: {source}} — 用於建立 ConfiguredFetcher
    """
    fetcher_registry.clear()

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
