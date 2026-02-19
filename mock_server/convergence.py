"""
\u6536\u6582\u8a08\u7b97\u51fd\u6578\u3002

\u63d0\u4f9b\u57fa\u65bc\u6307\u6578\u8870\u6e1b\u7684\u5931\u6557\u7387\u8a08\u7b97\u548c\u8a2d\u5099\u65b0\u820a\u5224\u65b7\u3002
\u6240\u6709\u51fd\u6578\u90fd\u63a5\u6536 elapsed \u53c3\u6578\uff08\u7d2f\u8a08\u6d3b\u8e8d\u79d2\u6578\uff09\uff0c
\u800c\u4e0d\u662f\u81ea\u5df1\u8a08\u7b97\u6642\u9593\u3002

\u6536\u6582\u516c\u5f0f:
    failure_rate(t) = target + (initial - target) \u00d7 e^(-3t/T)

    t = \u7d2f\u8a08\u6d3b\u8e8d\u79d2\u6578
    T = \u6536\u6582\u6642\u9593\u5e38\u6578
"""
from __future__ import annotations

import math
import random


def should_device_fail(
    is_old: bool | None,
    elapsed: float,
    converge_time: float,
) -> bool:
    """
    \u5224\u65b7\u8a2d\u5099\u662f\u5426\u61c9\u8a72\u5931\u6557\uff08\u57fa\u65bc\u6642\u9593\u6536\u6582 + \u65b0\u820a\u8a2d\u5099\u5dee\u7570\uff09\u3002

    \u6536\u6582\u908f\u8f2f\uff1a
    - \u6536\u6582\u5207\u63db\u9ede = converge_time / 2
    - \u820a\u8a2d\u5099 (is_old=True): \u5207\u63db\u9ede\u524d\u53ef\u9054\uff0c\u4e4b\u5f8c\u4e0d\u53ef\u9054
    - \u65b0\u8a2d\u5099 (is_old=False): \u5207\u63db\u9ede\u524d\u4e0d\u53ef\u9054\uff0c\u4e4b\u5f8c\u53ef\u9054
    - \u672a\u6307\u5b9a (is_old=None): \u59cb\u7d42\u53ef\u9054
    """
    if is_old is None:
        return False

    if converge_time <= 0:
        return is_old

    switch_time = converge_time / 2
    has_converged = elapsed >= switch_time

    if is_old:
        return has_converged
    else:
        return not has_converged


def exponential_decay_failure_rate(
    elapsed: float,
    converge_time: float,
    initial_failure_rate: float,
    target_failure_rate: float,
) -> float:
    """
    \u8a08\u7b97\u6307\u6578\u8870\u6e1b\u7684\u5931\u6557\u7387\u3002

    rate = target + (initial - target) \u00d7 e^(-3t/T)
    t=T \u6642\u7d04 95% \u6536\u6582\uff0ct=2T \u6642\u7d04 99% \u6536\u6582\u3002
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
    \u6839\u64da\u7576\u524d\u6642\u9593\u6c7a\u5b9a\u662f\u5426\u7522\u751f\u5931\u6557\u8cc7\u6599\u3002

    \u4f7f\u7528 exponential_decay_failure_rate() \u8a08\u7b97\u7576\u524d\u5931\u6557\u7387\uff0c
    \u7136\u5f8c\u7528\u96a8\u6a5f\u6578\u6c7a\u5b9a\u662f\u5426\u5931\u6557\u3002
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
    \u8a08\u7b97\u6536\u6582\u4e2d\u7684\u8b8a\u7570\u6578\uff08\u7528\u65bc\u6578\u503c\u578b\u6307\u6a19\u5982 transceiver\uff09\u3002
    """
    if converge_time <= 0:
        return target_variance
    if elapsed >= converge_time * 2:
        return target_variance

    decay = math.exp(-3.0 * elapsed / converge_time)
    return target_variance + (initial_variance - target_variance) * decay
