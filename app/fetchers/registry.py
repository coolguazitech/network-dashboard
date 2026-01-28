"""
Fetcher Registry.

管理 fetch_type → BaseFetcher 的映射。
應用啟動時呼叫 setup_fetchers() 根據 USE_MOCK_API 註冊 mock 或 real fetcher。
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

    全域唯一實例 (module-level singleton)。
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


def setup_fetchers(use_mock: bool) -> None:
    """
    應用啟動時呼叫。根據 use_mock 註冊 mock 或 real fetcher。

    Args:
        use_mock: True = 註冊 MockFetcher (開發/測試)
                  False = 註冊 Real Fetcher (正式環境)
    """
    fetcher_registry.clear()

    if use_mock:
        from app.fetchers.mock import register_mock_fetchers

        register_mock_fetchers()
        logger.info(
            "Registered %d mock fetchers: %s",
            len(fetcher_registry),
            fetcher_registry.list_fetchers(),
        )
    else:
        from app.fetchers.implementations import register_real_fetchers

        register_real_fetchers()
        logger.info(
            "Registered %d real fetchers: %s",
            len(fetcher_registry),
            fetcher_registry.list_fetchers(),
        )
