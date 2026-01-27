#!/usr/bin/env python3
"""
Generate Mock API Scenario Files for Factory Network.

Creates YAML scenario files for testing with 34 factory switches.
Uses shared device configuration from factory_device_config.py.
"""
import sys
from pathlib import Path

# Add scripts dir to path for factory_device_config import
sys.path.insert(0, str(Path(__file__).parent))

import yaml

from factory_device_config import (
    TARGET_VERSION,
    get_active_device_list,
)

# Build device lists from shared config
_active_devices = get_active_device_list()
_device_ip_map = {d["hostname"]: d["ip"] for d in _active_devices}

CORE_SWITCHES = [
    d["hostname"] for d in _active_devices if d["device_type"] == "CORE"
]
AGG_SWITCHES = [
    d["hostname"] for d in _active_devices if d["device_type"] == "AGG"
]
EDGE_SWITCHES: dict[str, list[str]] = {}
for _dtype in ["EQP", "AMHS", "SNR", "OTHERS"]:
    EDGE_SWITCHES[_dtype] = [
        d["hostname"] for d in _active_devices
        if d["device_type"] == _dtype
    ]

ALL_EDGE_SWITCHES: list[str] = []
for _cat in ["EQP", "AMHS", "SNR", "OTHERS"]:
    ALL_EDGE_SWITCHES.extend(EDGE_SWITCHES[_cat])


def get_uplink_neighbors(hostname: str) -> list[tuple[str, str, str]]:
    """
    Get uplink neighbor information for a switch.

    Returns list of (local_interface, neighbor_hostname, neighbor_interface).
    """
    neighbors = []

    # EDGE -> AGG uplinks
    if hostname in ALL_EDGE_SWITCHES:
        idx = ALL_EDGE_SWITCHES.index(hostname)
        agg_idx_1 = idx % len(AGG_SWITCHES)
        agg_idx_2 = (idx + 1) % len(AGG_SWITCHES)

        neighbors.append((
            "XGE1/0/51",
            AGG_SWITCHES[agg_idx_1],
            f"XGE1/0/{idx + 1}"
        ))
        neighbors.append((
            "XGE1/0/52",
            AGG_SWITCHES[agg_idx_2],
            f"XGE1/0/{idx + 1}"
        ))

    # AGG -> CORE uplinks
    elif hostname in AGG_SWITCHES:
        idx = AGG_SWITCHES.index(hostname)
        neighbors.append((
            "HGE1/0/25",
            CORE_SWITCHES[0],
            f"HGE1/0/{idx + 1}"
        ))
        neighbors.append((
            "HGE1/0/26",
            CORE_SWITCHES[1],
            f"HGE1/0/{idx + 1}"
        ))

    return neighbors


def generate_hpe_transceiver_output(hostname: str) -> str:
    """Generate HPE Comware transceiver CLI output."""
    output_lines = []

    if hostname in ALL_EDGE_SWITCHES:
        # EDGE switch - XGE uplinks + some GE access ports
        for port in [51, 52]:
            output_lines.append(f"""XGE1/0/{port} transceiver information:
  Transceiver Type              : 10GBASE-SR-SFP+
  Connector Type                : LC
  Wavelength(nm)                : 850
  Transfer Distance(m)          : 300(62.5um/125um OM1)
                                  300(50um/125um OM2)
                                  300(50um/125um OM3)
  Vendor Name                   : HPE
  Vendor Part Number            : J9150A
  Temperature(Celsius)          : 32
  Temp High Threshold(Celsius)  : 75
  Temp Low Threshold(Celsius)   : -5
  Voltage(V)                    : 3.28
  Bias Current(mA)              : 7.20
  Bias High Threshold(mA)       : 13.20
  Current RX Power(dBm)         : -3.15
  RX Power High Threshold(dBm)  : 1.00
  RX Power Low Threshold(dBm)   : -13.97
  Current TX Power(dBm)         : -2.48
  TX Power High Threshold(dBm)  : 1.00
  TX Power Low Threshold(dBm)   : -11.30
""")

        # Add a few access ports
        for port in [1, 2, 5, 10]:
            output_lines.append(f"""GE1/0/{port} transceiver information:
  Transceiver Type              : 1000BASE-T
  Connector Type                : RJ45
  Vendor Name                   : HPE
  Temperature(Celsius)          : 28
""")

    elif hostname in AGG_SWITCHES:
        # AGG switch - HGE uplinks to CORE
        for port in [25, 26]:
            output_lines.append(f"""HGE1/0/{port} transceiver information:
  Transceiver Type              : 100GBASE-SR4-QSFP28
  Connector Type                : MPO
  Wavelength(nm)                : 850
  Transfer Distance(m)          : 70(50um/125um OM3)
                                  100(50um/125um OM4)
  Vendor Name                   : HPE
  Vendor Part Number            : 845416-B21
  Temperature(Celsius)          : 35
  Temp High Threshold(Celsius)  : 75
  Temp Low Threshold(Celsius)   : -5
  Voltage(V)                    : 3.30
  Bias Current(mA)              : 8.50
  Current RX Power(dBm)         : -2.85
  RX Power High Threshold(dBm)  : 2.40
  RX Power Low Threshold(dBm)   : -9.50
  Current TX Power(dBm)         : -2.20
  TX Power High Threshold(dBm)  : 2.40
  TX Power Low Threshold(dBm)   : -7.30
""")

    elif hostname in CORE_SWITCHES:
        # CORE switch - HGE ports for downlinks to AGG
        for port in range(1, 9):
            output_lines.append(f"""HGE1/0/{port} transceiver information:
  Transceiver Type              : 100GBASE-SR4-QSFP28
  Connector Type                : MPO
  Wavelength(nm)                : 850
  Vendor Name                   : HPE
  Vendor Part Number            : 845416-B21
  Temperature(Celsius)          : 34
  Voltage(V)                    : 3.31
  Bias Current(mA)              : 8.30
  Current RX Power(dBm)         : -2.90
  Current TX Power(dBm)         : -2.15
""")

    return "\n".join(output_lines)


def generate_hpe_neighbor_output(hostname: str) -> str:
    """Generate HPE Comware LLDP neighbor CLI output."""
    neighbors = get_uplink_neighbors(hostname)

    if not neighbors:
        return "No LLDP neighbors found."

    output_lines = []
    for local_if, neighbor_host, neighbor_if in neighbors:
        neighbor_ip = _device_ip_map.get(neighbor_host, "10.0.0.1")
        output_lines.append(
            f"""Local Interface {local_if} has 1 neighbor:
Neighbor Index   : 1
Update Time      : 0 days, 0 hours, 5 minutes, 23 seconds
Chassis Type     : MAC address
Chassis ID       : {_generate_chassis_mac(neighbor_host)}
Port ID Type     : Interface name
Port ID          : {neighbor_if}
Port Description : Uplink Interface
System Name      : {neighbor_host}
System Description: HPE Comware Platform Software
System Capabilities Supported  : Bridge
System Capabilities Enabled    : Bridge
Management Address Type   : IPv4
Management Address        : {neighbor_ip}
Expired Time              : 120
""")

    return "\n".join(output_lines)


def _generate_chassis_mac(hostname: str) -> str:
    """Generate a consistent MAC address based on hostname."""
    hash_val = sum(ord(c) for c in hostname)
    return (
        f"00:1a:2b:{hash_val % 256:02x}"
        f":{hash_val // 256 % 256:02x}"
        f":{hash_val // 65536 % 256:02x}"
    )


def generate_hpe_version_output(
    version: str = TARGET_VERSION,
) -> str:
    """Generate HPE Comware version CLI output."""
    return f"""HPE Comware Platform Software
Comware Software, Version {version}, Release 6635
Copyright (c) 2010-2020 Hewlett Packard Enterprise Development LP
HPE FlexFabric 5710 48G 4SFP+ Switch uptime is 45 weeks, 3 days, 12 hours
Last reboot reason : User reboot

Boot image: flash:/5710-cmw710-boot-{version}.bin
System image: flash:/5710-cmw710-system-{version}.bin
"""


def generate_hpe_port_channel_output(hostname: str) -> str:
    """Generate HPE Comware port-channel CLI output."""
    if hostname in ALL_EDGE_SWITCHES:
        return """Aggregate Interface: Bridge-Aggregation1
Aggregation Mode: Dynamic
Loadsharing Type: Shar
  Port             Status   Weight
  XGE1/0/51        S        1
  XGE1/0/52        S        1
"""
    elif hostname in AGG_SWITCHES:
        return """Aggregate Interface: Bridge-Aggregation1
Aggregation Mode: Dynamic
Loadsharing Type: Shar
  Port             Status   Weight
  HGE1/0/25        S        1
  HGE1/0/26        S        1
"""
    else:
        return ""


def generate_hpe_fan_output() -> str:
    """Generate HPE Comware fan CLI output."""
    return """Slot   Fan   Status     Speed(RPM)
---------------------------------------------
1      FAN1  Normal     6500
1      FAN2  Normal     6480
1      FAN3  Normal     6520
1      FAN4  Normal     6490
"""


def generate_hpe_power_output() -> str:
    """Generate HPE Comware power supply CLI output."""
    return """Power Supply Information:
---------------------------------------------
Slot   PS   Status     Model         Power(W)
---------------------------------------------
1      PS1  Normal     JG136A        460
1      PS2  Normal     JG136A        460
"""


def generate_hpe_error_output(hostname: str) -> str:
    """Generate HPE Comware interface error counters."""
    output_lines = []

    if hostname in ALL_EDGE_SWITCHES:
        for port in [51, 52]:
            output_lines.append(f"""XGE1/0/{port}
  Input:  0 packets, 0 bytes, 0 errors
  Output: 0 packets, 0 bytes, 0 errors
  InBadCRC: 0, OutCollisions: 0
""")
        for port in [1, 2, 5, 10]:
            output_lines.append(f"""GE1/0/{port}
  Input:  0 packets, 0 bytes, 0 errors
  Output: 0 packets, 0 bytes, 0 errors
""")

    elif hostname in AGG_SWITCHES:
        for port in [25, 26]:
            output_lines.append(f"""HGE1/0/{port}
  Input:  0 packets, 0 bytes, 0 errors
  Output: 0 packets, 0 bytes, 0 errors
""")

    elif hostname in CORE_SWITCHES:
        for port in range(1, 9):
            output_lines.append(f"""HGE1/0/{port}
  Input:  0 packets, 0 bytes, 0 errors
  Output: 0 packets, 0 bytes, 0 errors
""")

    return "\n".join(output_lines)


def _build_device_entry(hostname: str) -> dict:
    """Build a scenario entry for a single device."""
    return {
        "ip_address": _device_ip_map[hostname],
        "vendor": "HPE",
        "platform": "Comware",
        "site": "t_site",
        "power": "on",
        "ping_reachable": True,
        "transceiver_output": generate_hpe_transceiver_output(hostname),
        "neighbor_output": generate_hpe_neighbor_output(hostname),
        "version_output": generate_hpe_version_output(TARGET_VERSION),
        "port_channel_output": generate_hpe_port_channel_output(hostname),
        "fan_output": generate_hpe_fan_output(),
        "power_output": generate_hpe_power_output(),
        "error_output": generate_hpe_error_output(hostname),
    }


def generate_baseline_scenario() -> dict:
    """Generate baseline scenario with all 34 active switches."""
    scenario = {}
    all_switches = CORE_SWITCHES + AGG_SWITCHES + ALL_EDGE_SWITCHES
    for hostname in all_switches:
        scenario[hostname] = _build_device_entry(hostname)
    return scenario


def generate_transceiver_failure_scenario() -> dict:
    """Generate scenario with optical transceiver power degradation."""
    scenario = generate_baseline_scenario()

    # Inject transceiver failure on first device of EQP, AMHS, SNR
    failed_switches = [
        EDGE_SWITCHES["EQP"][0],
        EDGE_SWITCHES["AMHS"][0],
        EDGE_SWITCHES["SNR"][0],
    ]

    for hostname in failed_switches:
        if hostname in scenario:
            scenario[hostname]["transceiver_output"] = (
                scenario[hostname]["transceiver_output"].replace(
                    "Current RX Power(dBm)         : -3.15",
                    "Current RX Power(dBm)         : -15.50",
                )
            )

    return scenario


def generate_uplink_down_scenario() -> dict:
    """Generate scenario with uplink disconnection."""
    scenario = generate_baseline_scenario()

    # Disconnect one uplink on second EQP switch
    hostname = EDGE_SWITCHES["EQP"][1]
    if hostname in scenario:
        lines = scenario[hostname]["neighbor_output"].split("\n")
        # Keep only first neighbor (remove second uplink)
        scenario[hostname]["neighbor_output"] = "\n".join(
            lines[:15]
        )

    return scenario


def generate_version_mismatch_scenario() -> dict:
    """Generate scenario with incorrect firmware version."""
    scenario = generate_baseline_scenario()

    # Set wrong version on some devices
    wrong_version_devices = [
        EDGE_SWITCHES["EQP"][2],
        EDGE_SWITCHES["AMHS"][1],
    ]

    for hostname in wrong_version_devices:
        if hostname in scenario:
            scenario[hostname]["version_output"] = (
                generate_hpe_version_output("6635P05")
            )

    return scenario


def generate_port_channel_degraded_scenario() -> dict:
    """Generate scenario with Port-Channel member down."""
    scenario = generate_baseline_scenario()

    # Degrade Port-Channel on fourth EQP switch
    hostname = EDGE_SWITCHES["EQP"][3]
    if hostname in scenario:
        scenario[hostname]["port_channel_output"] = (
            """Aggregate Interface: Bridge-Aggregation1
Aggregation Mode: Dynamic
Loadsharing Type: Shar
  Port             Status   Weight
  XGE1/0/51        S        1
  XGE1/0/52        D        1
"""
        )

    return scenario


def main():
    """Generate all factory scenario files."""
    output_dir = Path("tests/scenarios")
    output_dir.mkdir(parents=True, exist_ok=True)

    scenarios = {
        "factory_baseline.yaml": generate_baseline_scenario(),
        "factory_transceiver_failure.yaml": (
            generate_transceiver_failure_scenario()
        ),
        "factory_uplink_down.yaml": generate_uplink_down_scenario(),
        "factory_version_mismatch.yaml": (
            generate_version_mismatch_scenario()
        ),
        "factory_port_channel_degraded.yaml": (
            generate_port_channel_degraded_scenario()
        ),
    }

    for filename, scenario_data in scenarios.items():
        filepath = output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# Factory Network Scenario: {filename}\n")
            f.write(f"# Generated scenario with {len(scenario_data)} switches\n")
            f.write("# Topology: 2 CORE + 8 AGG + 24 EDGE\n\n")
            yaml.dump(
                scenario_data, f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        print(f"  Created {filepath}")

    print(f"\nGenerated {len(scenarios)} factory scenario files")


if __name__ == "__main__":
    main()
