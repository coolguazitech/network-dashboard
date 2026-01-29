"""
MockFetcher 時間收斂機制。

提供時間追蹤和收斂計算功能，讓 MockFetcher 產生隨時間收斂到正常狀態的資料。

核心組件:
    - ConvergenceConfig: 收斂參數配置
    - MockTimeTracker: 追蹤 Mock 系統啟動時間的 Singleton
    - exponential_decay_failure_rate(): 計算當前失敗率
    - should_fail(): 根據當前時間決定是否產生失敗資料

收斂公式:
    failure_rate(t) = target + (initial - target) × e^(-3t/T)

    t = 經過時間（秒）
    T = 收斂時間常數
    initial = 初始失敗率
    target = 目標失敗率

範例:
    tracker = MockTimeTracker()
    fails = should_fail(
        elapsed=tracker.elapsed_seconds,
        converge_time=tracker.config.ping_converge_time,
        initial_failure_rate=0.40,
        target_failure_rate=0.05,
    )
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass


@dataclass
class ConvergenceConfig:
    """
    收斂參數配置。

    Attributes:
        hardware_stabilize_time: fan/power 穩定時間（秒）
        transceiver_converge_time: 光模塊功率收斂時間（秒）
        error_converge_time: 錯誤計數歸零時間（秒）
        ping_converge_time: Ping 成功率收斂時間（秒）
        topology_stabilize_time: uplink/port_channel 穩定時間（秒）
        version_stabilize_time: 版本驗證穩定時間（秒）
    """

    hardware_stabilize_time: float = 60.0
    transceiver_converge_time: float = 300.0
    error_converge_time: float = 600.0
    ping_converge_time: float = 300.0
    topology_stabilize_time: float = 120.0
    version_stabilize_time: float = 60.0


class MockTimeTracker:
    """
    追蹤 Mock 系統啟動時間的 Singleton。

    用於計算經過時間，讓 MockFetcher 根據時間產生收斂的資料。

    Usage:
        tracker = MockTimeTracker()
        elapsed = tracker.elapsed_seconds
        config = tracker.config
    """

    _instance: MockTimeTracker | None = None
    _start_time: float = 0.0
    _config: ConvergenceConfig

    def __new__(cls) -> MockTimeTracker:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._start_time = time.time()
            cls._instance._config = ConvergenceConfig()
        return cls._instance

    @classmethod
    def reset(cls, config: ConvergenceConfig | None = None) -> None:
        """
        重置計時器。

        在 setup_fetchers() 或測試中呼叫以重新開始計時。

        Args:
            config: 可選的新配置，None 則保留現有配置
        """
        if cls._instance is None:
            cls._instance = cls()
        cls._instance._start_time = time.time()
        if config is not None:
            cls._instance._config = config

    @property
    def elapsed_seconds(self) -> float:
        """自 Mock 系統啟動以來經過的秒數。"""
        return time.time() - self._start_time

    @property
    def config(self) -> ConvergenceConfig:
        """當前的收斂配置。"""
        return self._config


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
