"""Mock: \u4ecb\u9762 CRC \u932f\u8aa4\u8a08\u6578 (get_error_count)\u3002"""
from __future__ import annotations

import random


def generate(device_type: str, fails: bool = False, **_kw: object) -> str:
    has_error = fails

    if device_type == "nxos":
        return _generate_nxos(has_error)
    elif device_type == "ios":
        return _generate_ios(has_error)
    else:
        return _generate_hpe(has_error)


def _generate_hpe(has_error: bool) -> str:
    lines = ["Interface            Input(errs)       Output(errs)"]
    for i in range(1, 21):
        in_err = random.randint(1, 15) if has_error else 0
        out_err = random.randint(0, 5) if has_error else 0
        lines.append(
            f"GE1/0/{i}                        "
            f"{in_err}                  {out_err}"
        )
    return "\n".join(lines)


def _generate_nxos(has_error: bool) -> str:
    lines = [
        "--------------------------------------------------------------------------------",
        "Port          Align-Err    FCS-Err   Xmit-Err    Rcv-Err  UnderSize OutDiscards",
        "--------------------------------------------------------------------------------",
    ]
    for i in range(1, 21):
        fcs = random.randint(1, 10) if has_error else 0
        rcv = random.randint(1, 15) if has_error else 0
        xmit = random.randint(0, 5) if has_error else 0
        lines.append(
            f"Eth1/{i:<14d}{0:>9d}{fcs:>11d}{xmit:>11d}"
            f"{rcv:>11d}{0:>11d}{0:>12d}"
        )
    return "\n".join(lines)


def _generate_ios(has_error: bool) -> str:
    lines = ["Interface            Input(errs)       Output(errs)"]
    for i in range(1, 21):
        in_err = random.randint(1, 15) if has_error else 0
        out_err = random.randint(0, 5) if has_error else 0
        lines.append(
            f"Gi1/0/{i}                        "
            f"{in_err}                  {out_err}"
        )
    return "\n".join(lines)
