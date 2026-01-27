"""
Shared factory device configuration.

Single source of truth for device naming, IP addressing, and MAC distribution.
Used by init_factory_data.py, generate_factory_scenarios.py, and seed_client_data.py.
"""

MAINTENANCE_ID = "TEST-100"
TARGET_VERSION = "6635P07"

# Network topology - Device naming
# Format: {global_number: device_type}
DEVICES_CONFIG: dict[int, str] = {
    # CORE switches (2 devices)
    1: "CORE",
    2: "CORE",
    # AGG switches (8 devices)
    3: "AGG",
    4: "AGG",
    5: "AGG",
    6: "AGG",
    7: "AGG",
    8: "AGG",
    9: "AGG",
    10: "AGG",
    # EQP switches (10 devices)
    11: "EQP",
    12: "EQP",
    13: "EQP",
    14: "EQP",
    15: "EQP",
    16: "EQP",
    17: "EQP",
    18: "EQP",
    19: "EQP",
    20: "EQP",
    # AMHS switches (4 devices)
    21: "AMHS",
    22: "AMHS",
    23: "AMHS",
    24: "AMHS",
    # SNR switches (5 devices)
    25: "SNR",
    26: "SNR",
    27: "SNR",
    28: "SNR",
    29: "SNR",
    # OTHERS switches (5 devices)
    30: "OTHERS",
    31: "OTHERS",
    32: "OTHERS",
    33: "OTHERS",
    34: "OTHERS",
}

# Devices NOT being replaced (keep OLD hostname)
DEVICES_NOT_REPLACED = {11, 12, 21}

# MAC address distribution by category
MAC_DISTRIBUTION = {
    "EQP": 50,
    "AMHS": 25,
    "SNR": 15,
    "OTHERS": 10,
}


def get_old_ip(num: int, device_type: str) -> str:
    """Generate OLD device IP address (10.1.x.x range)."""
    if device_type == "CORE":
        return f"10.1.1.{num}"
    elif device_type == "AGG":
        return f"10.1.2.{num}"
    else:
        return f"10.1.3.{num}"


def get_new_ip(num: int, device_type: str) -> str:
    """Generate NEW device IP address (10.2.x.x range)."""
    if device_type == "CORE":
        return f"10.2.1.{num}"
    elif device_type == "AGG":
        return f"10.2.2.{num}"
    else:
        return f"10.2.3.{num}"


def get_device_mappings() -> list[tuple[str, str, str, str]]:
    """
    Generate device mappings.

    Returns list of (old_hostname, old_ip, new_hostname, new_ip) tuples.
    """
    mappings = []
    for num, device_type in DEVICES_CONFIG.items():
        old_hostname = f"SW-OLD-{num:03d}-{device_type}"
        old_ip = get_old_ip(num, device_type)
        if num in DEVICES_NOT_REPLACED:
            new_hostname = old_hostname
            new_ip = old_ip
        else:
            new_hostname = f"SW-NEW-{num:03d}-{device_type}"
            new_ip = get_new_ip(num, device_type)
        mappings.append((old_hostname, old_ip, new_hostname, new_ip))
    return mappings


def get_active_device_list() -> list[dict[str, str]]:
    """
    Get the 34 active devices (NEW + not-replaced OLD).

    Returns list of {hostname, ip, device_type, num} dicts.
    """
    devices = []
    for num, device_type in DEVICES_CONFIG.items():
        if num in DEVICES_NOT_REPLACED:
            hostname = f"SW-OLD-{num:03d}-{device_type}"
            ip = get_old_ip(num, device_type)
        else:
            hostname = f"SW-NEW-{num:03d}-{device_type}"
            ip = get_new_ip(num, device_type)
        devices.append({
            "hostname": hostname,
            "ip": ip,
            "device_type": device_type,
            "num": num,
        })
    return devices


def generate_mac_addresses() -> dict[str, list[tuple[str, str]]]:
    """Generate 100 MAC addresses with descriptions.

    Uses valid hex octets for category identification:
      EQP    → E0
      AMHS   → A0
      SNR    → B0
      OTHERS → C0
    """
    macs: dict[str, list[tuple[str, str]]] = {}
    macs["EQP"] = [
        (f"00:11:22:E0:{i:02X}:{i:02X}", f"EQP Equipment {i:02d}")
        for i in range(1, 51)
    ]
    macs["AMHS"] = [
        (f"00:11:22:A0:{i:02X}:{i:02X}", f"AMHS Robot {i:02d}")
        for i in range(1, 26)
    ]
    macs["SNR"] = [
        (f"00:11:22:B0:{i:02X}:{i:02X}", f"SNR Storage {i:02d}")
        for i in range(1, 16)
    ]
    macs["OTHERS"] = [
        (f"00:11:22:C0:{i:02X}:{i:02X}", f"Other Device {i:02d}")
        for i in range(1, 11)
    ]
    return macs
