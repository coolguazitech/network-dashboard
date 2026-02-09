"""
Fetchers package.

提供 Fetcher 抽象層，處理「如何呼叫外部 API」。

核心 API:
    - BaseFetcher: 所有 Fetcher 的基底類別
    - FetchContext: fetch 呼叫的上下文
    - FetchResult: fetch 回傳結果
    - fetcher_registry: 全域 Fetcher 註冊表
    - setup_fetchers(): 應用啟動時初始化
"""
from app.fetchers.base import BaseFetcher, FetchContext, FetchResult
from app.fetchers.registry import (
    fetcher_registry,
    setup_fetchers,
)

__all__ = [
    "BaseFetcher",
    "FetchContext",
    "FetchResult",
    "fetcher_registry",
    "setup_fetchers",
]
