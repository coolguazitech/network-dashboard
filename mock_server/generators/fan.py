"""Mock: \u98a8\u6247\u72c0\u614b (get_fan)\u3002"""
from __future__ import annotations


def generate(device_type: str, fails: bool = False, **_kw: object) -> str:
    if device_type == "nxos":
        return _generate_nxos(fails)
    elif device_type == "ios":
        return _generate_ios(fails)
    else:
        return _generate_hpe(fails)


def _generate_hpe(fails: bool) -> str:
    fan3 = "Absent" if fails else "Normal"
    return (
        "Slot 1:\n"
        "FanID    Status      Direction\n"
        "1        Normal      Back-to-front\n"
        "2        Normal      Back-to-front\n"
        f"3        {fan3}      Back-to-front\n"
        "4        Normal      Back-to-front\n"
    )


def _generate_nxos(fails: bool) -> str:
    fan3 = "Absent" if fails else "Ok"
    return (
        "Fan             Model                Hw     Status\n"
        "--------------------------------------------------------------\n"
        "Fan1(Sys_Fan1)  NXA-FAN-30CFM-F      --     Ok\n"
        "Fan2(Sys_Fan2)  NXA-FAN-30CFM-F      --     Ok\n"
        f"Fan3(Sys_Fan3)  NXA-FAN-30CFM-F      --     {fan3}\n"
        "Fan4(Sys_Fan4)  NXA-FAN-30CFM-F      --     Ok\n"
    )


def _generate_ios(fails: bool) -> str:
    fan3 = "NOT OK" if fails else "OK"
    return (
        "FAN 1 is OK\n"
        "FAN 2 is OK\n"
        f"FAN 3 is {fan3}\n"
        "FAN 4 is OK\n"
    )
