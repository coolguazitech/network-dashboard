"""
MockFetcher 時間收斂機制。

提供時間追蹤和收斂計算功能，讓 MockFetcher 產生隨時間收斂到正常狀態的資料。

核心組件:
    - MockTimeTracker: 追蹤各歲修建立時間，計算經過時間
    - exponential_decay_failure_rate(): 計算當前失敗率
    - should_fail(): 根據當前時間決定是否產生失敗資料

收斂時間統一從 settings.mock_ping_converge_time 讀取。

收斂公式:
    failure_rate(t) = target + (initial - target) × e^(-3t/T)

    t = 經過時間（秒），從歲修建立時間開始計算
    T = 收斂時間常數（來自 .env 的 MOCK_PING_CONVERGE_TIME）
    initial = 初始失敗率
    target = 目標失敗率

範例:
    tracker = MockTimeTracker()
    elapsed = tracker.get_elapsed_seconds("MAINT-2025-001")
    fails = should_fail(
        elapsed=elapsed,
        converge_time=tracker.converge_time,
        initial_failure_rate=0.40,
        target_failure_rate=0.05,
    )
"""
from __future__ import annotations

import math
import random
import time
from datetime import datetime, timezone


class MockTimeTracker:
    """
    追蹤各歲修建立時間的 Singleton。

    每個歲修有自己的起始時間（從 MaintenanceConfig.created_at 讀取），
    用於計算該歲修的經過時間，讓 MockFetcher 根據時間產生收斂的資料。

    收斂時間統一從 settings.mock_ping_converge_time 讀取。

    Usage:
        tracker = MockTimeTracker()
        elapsed = tracker.get_elapsed_seconds("MAINT-2025-001")
        converge_time = tracker.converge_time
    """

    _instance: MockTimeTracker | None = None
    _maintenance_start_times: dict[str, datetime]
    _fallback_start_time: float  # 無 maintenance_id 時的 fallback

    def __new__(cls) -> MockTimeTracker:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._maintenance_start_times = {}
            cls._instance._fallback_start_time = time.time()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """
        重置計時器。

        清除所有快取的歲修起始時間，在測試中使用。
        """
        if cls._instance is None:
            cls._instance = cls()
        cls._instance._maintenance_start_times = {}
        cls._instance._fallback_start_time = time.time()

    @classmethod
    def set_maintenance_start_time(
        cls, maintenance_id: str, start_time: datetime
    ) -> None:
        """
        手動設定歲修起始時間（用於測試或快取）。

        Args:
            maintenance_id: 歲修 ID
            start_time: 起始時間
        """
        if cls._instance is None:
            cls._instance = cls()
        cls._instance._maintenance_start_times[maintenance_id] = start_time

    @classmethod
    def clear_maintenance_cache(cls, maintenance_id: str) -> None:
        """
        清除指定歲修的快取。

        當歲修被刪除時呼叫，確保下次重建時使用新的起始時間。

        Args:
            maintenance_id: 歲修 ID
        """
        if cls._instance is not None:
            cls._instance._maintenance_start_times.pop(maintenance_id, None)

    def _load_maintenance_start_time(self, maintenance_id: str) -> datetime | None:
        """
        從資料庫載入歲修的建立時間。

        使用同步方式查詢，因為 Mock Fetcher 可能在非 async context 中呼叫。
        """
        try:
            from sqlalchemy import create_engine, text
            from app.core.config import settings

            # 建立同步 engine 進行查詢
            sync_url = settings.database_url.replace(
                "postgresql+asyncpg://", "postgresql://"
            ).replace(
                "sqlite+aiosqlite://", "sqlite://"
            )
            engine = create_engine(sync_url)

            with engine.connect() as conn:
                result = conn.execute(
                    text(
                        "SELECT created_at FROM maintenance_configs "
                        "WHERE maintenance_id = :mid"
                    ),
                    {"mid": maintenance_id}
                )
                row = result.fetchone()
                if row and row[0]:
                    return row[0]
        except Exception:
            pass
        return None

    def get_elapsed_seconds(self, maintenance_id: str | None = None) -> float:
        """
        取得指定歲修的經過時間（秒）。

        Args:
            maintenance_id: 歲修 ID，若為 None 則使用 fallback 時間

        Returns:
            從歲修建立時間到現在的秒數
        """
        if maintenance_id is None:
            return time.time() - self._fallback_start_time

        # 檢查快取
        if maintenance_id in self._maintenance_start_times:
            start_time = self._maintenance_start_times[maintenance_id]
        else:
            # 從資料庫載入
            start_time = self._load_maintenance_start_time(maintenance_id)
            if start_time:
                self._maintenance_start_times[maintenance_id] = start_time
            else:
                # 找不到時使用 fallback
                return time.time() - self._fallback_start_time

        # 計算經過時間
        # 確保 start_time 是 timezone-aware，如果是 naive 則視為 UTC
        now = datetime.now(timezone.utc)
        if isinstance(start_time, datetime):
            if start_time.tzinfo is None:
                # Treat naive datetime as UTC
                start_time = start_time.replace(tzinfo=timezone.utc)
            delta = now - start_time
            return delta.total_seconds()
        return time.time() - self._fallback_start_time

    @property
    def elapsed_seconds(self) -> float:
        """
        [已棄用] 使用 get_elapsed_seconds(maintenance_id) 代替。

        保留此屬性是為了向後相容，使用 fallback 時間。
        """
        return time.time() - self._fallback_start_time

    @property
    def converge_time(self) -> float:
        """收斂時間（秒），來自 settings.mock_ping_converge_time。"""
        from app.core.config import settings
        return float(settings.mock_ping_converge_time)


def exponential_decay_failure_rate(
    elapsed: float,
    converge_time: float,
    initial_failure_rate: float,
    target_failure_rate: float,
) -> float:
    """
    計算指數衰減的失敗率。

    使用公式: rate = target + (initial - target) × e^(-3t/T)

    在 t=T 時約 95% 收斂，t=2T 時約 99% 收斂。

    Args:
        elapsed: 經過時間（秒）
        converge_time: 收斂時間常數 T（秒）
        initial_failure_rate: 初始失敗率 (0.0 - 1.0)
        target_failure_rate: 目標失敗率 (0.0 - 1.0)

    Returns:
        當前的失敗率 (0.0 - 1.0)
    """
    if converge_time <= 0:
        return target_failure_rate
    if elapsed >= converge_time * 2:
        return target_failure_rate

    decay = math.exp(-3.0 * elapsed / converge_time)
    return target_failure_rate + (initial_failure_rate - target_failure_rate) * decay


def should_fail(
    elapsed: float,
    converge_time: float,
    initial_failure_rate: float,
    target_failure_rate: float,
) -> bool:
    """
    根據當前時間決定是否產生失敗資料。

    使用 exponential_decay_failure_rate() 計算當前失敗率，
    然後用隨機數決定是否失敗。

    Args:
        elapsed: 經過時間（秒）
        converge_time: 收斂時間常數 T（秒）
        initial_failure_rate: 初始失敗率 (0.0 - 1.0)
        target_failure_rate: 目標失敗率 (0.0 - 1.0)

    Returns:
        True 表示應產生失敗資料，False 表示應產生正常資料
    """
    rate = exponential_decay_failure_rate(
        elapsed, converge_time, initial_failure_rate, target_failure_rate,
    )
    return random.random() < rate


def get_converging_variance(
    elapsed: float,
    converge_time: float,
    initial_variance: float,
    target_variance: float,
) -> float:
    """
    計算收斂中的變異數（用於數值型指標如 transceiver）。

    Args:
        elapsed: 經過時間（秒）
        converge_time: 收斂時間常數 T（秒）
        initial_variance: 初始變異數
        target_variance: 目標變異數

    Returns:
        當前的變異數
    """
    if converge_time <= 0:
        return target_variance
    if elapsed >= converge_time * 2:
        return target_variance

    decay = math.exp(-3.0 * elapsed / converge_time)
    return target_variance + (initial_variance - target_variance) * decay
