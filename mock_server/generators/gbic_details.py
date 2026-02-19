"""Mock: \u5149\u6a21\u7d44\u8a3a\u65b7\u8cc7\u6599 (get_gbic_details)\u3002"""
from __future__ import annotations

import random

from mock_server.convergence import should_device_fail

TX_NORMAL = -2.0
RX_NORMAL = -5.0
TEMP_NORMAL = 38.0
VOLT_NORMAL = 3.30
TX_BAD = -18.0
RX_BAD = -22.0
TEMP_BAD = 65.0


def generate(
    device_type: str,
    is_old: bool | None,
    active_seconds: float,
    converge_time: float,
) -> str:
    fails = should_device_fail(is_old, active_seconds, converge_time)

    if device_type == "nxos":
        return _generate_nxos(fails)
    elif device_type == "ios":
        return _generate_ios(fails)
    else:
        return _generate_hpe(fails)


def _gen_values(fails: bool) -> tuple[float, float, float, float]:
    if fails:
        tx = TX_BAD + random.gauss(0, 1.0)
        rx = RX_BAD + random.gauss(0, 1.0)
        temp = TEMP_BAD + random.gauss(0, 2.0)
    else:
        tx = TX_NORMAL + random.gauss(0, 1.0)
        rx = RX_NORMAL + random.gauss(0, 1.0)
        temp = TEMP_NORMAL + random.gauss(0, 3.0)

    tx = max(-25.0, min(5.0, tx))
    rx = max(-30.0, min(5.0, rx))
    temp = max(20.0, min(80.0, temp))
    volt = VOLT_NORMAL + random.gauss(0, 0.05)
    volt = max(2.5, min(4.0, volt))
    return tx, rx, temp, volt


def _generate_hpe(fails: bool) -> str:
    lines: list[str] = []
    for i in range(1, 7):
        tx, rx, temp, _volt = _gen_values(fails)
        lines.append(f"GigabitEthernet1/0/{i}")
        lines.append(f"  TX Power : {tx:.1f} dBm")
        lines.append(f"  RX Power : {rx:.1f} dBm")
        lines.append(f"  Temperature : {temp:.1f} C")
        lines.append("")
    return "\n".join(lines)


def _generate_ios(fails: bool) -> str:
    lines: list[str] = [
        "                                   Optical   Optical",
        "                 Temperature  Voltage  Tx Power  Rx Power",
        "Port             (Celsius)    (Volts)  (dBm)     (dBm)",
        "---------        -----------  -------  --------  --------",
    ]
    for i in range(1, 7):
        tx, rx, temp, volt = _gen_values(fails)
        lines.append(
            f"Gi1/0/{i:<12}{temp:<13.1f}{volt:<9.2f}{tx:<10.1f}{rx:.1f}"
        )
    return "\n".join(lines)


def _generate_nxos(fails: bool) -> str:
    lines: list[str] = []
    for i in range(1, 7):
        tx, rx, temp, volt = _gen_values(fails)
        lines.append(f"Ethernet1/{i}")
        lines.append("    transceiver is present")
        lines.append("    type is 10Gbase-SR")
        lines.append("    name is CISCO-FINISAR")
        lines.append(f"    Temperature            {temp:.2f} C")
        lines.append(f"    Voltage                {volt:.2f} V")
        lines.append(f"    Tx Power               {tx:.2f} dBm")
        lines.append(f"    Rx Power               {rx:.2f} dBm")
        lines.append("")
    return "\n".join(lines)
