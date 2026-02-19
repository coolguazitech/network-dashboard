"""Mock: \u96fb\u6e90\u4f9b\u61c9\u5668\u72c0\u614b (get_power)\u3002"""
from __future__ import annotations

from mock_server.convergence import should_device_fail


def generate(
    device_type: str,
    is_old: bool | None,
    active_seconds: float,
    converge_time: float,
    **_kw: object,
) -> str:
    fails = should_device_fail(is_old, active_seconds, converge_time)

    if device_type == "nxos":
        return _generate_nxos(fails)
    elif device_type == "ios":
        return _generate_ios(fails)
    else:
        return _generate_hpe(fails)


def _generate_hpe(fails: bool) -> str:
    ps2 = "Absent" if fails else "Normal"
    return (
        "Slot 1:\n"
        "PowerID State    Mode   Current(A)  Voltage(V)  "
        "Power(W)  FanDirection\n"
        "1       Normal   AC     --          --          "
        "--        Back-to-front\n"
        f"2       {ps2}   AC     --          --          "
        "--        Back-to-front\n"
    )


def _generate_nxos(fails: bool) -> str:
    ps2_status = "Absent" if fails else "Ok"
    ps2_output = "0" if fails else "132"
    return (
        "Power                              Actual        Total\n"
        "Supply    Model                    Output     Capacity    Status\n"
        "-------  -------------------  -----------  -----------  ----------\n"
        f"1        NXA-PAC-1100W-PE           186       1100     Ok\n"
        f"2        NXA-PAC-1100W-PE           {ps2_output}       1100     {ps2_status}\n"
    )


def _generate_ios(fails: bool) -> str:
    ps2 = "NOT OK" if fails else "OK"
    return (
        "PS1 is OK\n"
        f"PS2 is {ps2}\n"
    )
