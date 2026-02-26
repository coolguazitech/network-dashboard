"""Mock: MAC 位址表 (get_mac_table)。

根據 device_type 產出對應的 CLI 格式。
從 DB 讀取 MaintenanceMacList 的 MAC，分配到各 switch port。
"""
from __future__ import annotations

import hashlib
import random

from mock_server.generators._probabilities import (
    NOT_DETECTED_PROB,
    PORT_CHANGE_PROB,
    VALID_VLANS,
    VLAN_CHANGE_PROB,
)


def generate(
    device_type: str,
    fails: bool = False,
    switch_ip: str = "",
    mac_list: list[dict] | None = None,
    **_kw: object,
) -> str:

    # 設備不可達時回傳空表
    if fails:
        if device_type == "nxos":
            return _empty_nxos()
        elif device_type == "ios":
            return _empty_ios()
        else:
            return _empty_hpe()

    # 將 MAC 清單分配到本台 switch
    entries = _assign_macs_to_ports(switch_ip, mac_list or [], device_type)

    if device_type == "nxos":
        return _generate_nxos(entries)
    elif device_type == "ios":
        return _generate_ios(entries)
    else:
        return _generate_hpe(entries)


def _assign_macs_to_ports(
    switch_ip: str,
    mac_list: list[dict],
    device_type: str,
) -> list[dict]:
    """
    根據 MAC hash 決定哪些 MAC 在本台 switch，並分配 port 和 VLAN。

    每個 MAC 用 hash 決定 switch 歸屬，然後分配到不同 port。
    """
    if not mac_list:
        # 無 MAC 清單時產生假資料
        return _generate_fallback_entries(device_type)

    entries: list[dict] = []
    for item in mac_list:
        raw_mac = item.get("mac_address", "")
        if not raw_mac:
            continue

        # 用 MAC + switch_ip 的 hash 決定是否在本台 switch
        h = hashlib.md5(f"{raw_mac}:{switch_ip}".encode()).hexdigest()
        # 約 1/3 的 MAC 會在本台 switch（確定性，不隨機）
        if int(h[:2], 16) >= 85:
            continue

        # 小機率：MAC 暫時消失（per-MAC 獨立）
        if random.random() < NOT_DETECTED_PROB:
            continue

        # 基線 port / VLAN（確定性 hash）
        port_idx = int(h[2:4], 16) % 24 + 1
        vlan_id = VALID_VLANS[int(h[4:6], 16) % len(VALID_VLANS)]

        # 小機率：VLAN 變化（per-MAC 獨立）
        if random.random() < VLAN_CHANGE_PROB:
            vlan_id = random.choice(VALID_VLANS)

        # 小機率：port 變化（per-MAC 獨立）
        if random.random() < PORT_CHANGE_PROB:
            port_idx = random.randint(1, 24)

        entries.append({
            "mac": _format_mac(raw_mac, device_type),
            "port": _port_name(device_type, port_idx),
            "vlan": vlan_id,
        })

    if not entries:
        return _generate_fallback_entries(device_type)

    return entries


def _generate_fallback_entries(device_type: str) -> list[dict]:
    """無 MAC 清單時產生預設假資料。"""
    entries = []
    for i in range(1, 6):
        raw_mac = f"00:0C:29:AA:BB:{i:02X}"
        entries.append({
            "mac": _format_mac(raw_mac, device_type),
            "port": _port_name(device_type, i),
            "vlan": 10 if i <= 3 else 20,
        })
    return entries


def _format_mac(raw_mac: str, device_type: str) -> str:
    """將任意格式的 MAC 轉換成 device-type 專屬格式。"""
    # 移除所有分隔符號，取得 12 hex chars
    clean = raw_mac.replace(":", "").replace("-", "").replace(".", "").lower()
    if len(clean) != 12:
        return raw_mac

    if device_type == "hpe":
        # HPE: xxxx-xxxx-xxxx
        return f"{clean[0:4]}-{clean[4:8]}-{clean[8:12]}"
    else:
        # IOS / NXOS: xxxx.xxxx.xxxx
        return f"{clean[0:4]}.{clean[4:8]}.{clean[8:12]}"


def _port_name(device_type: str, idx: int) -> str:
    """產生 device-type 專屬的 port 名稱。

    注意：必須與 interface_status generator 使用的名稱一致，
    ClientCollectionService 靠 exact match 做介面比對。
    """
    if device_type == "hpe":
        return f"GE1/0/{idx}"
    elif device_type == "ios":
        return f"Gi1/0/{idx}"
    else:
        return f"Eth1/{idx}"


# --- HPE: display mac-address ---


def _empty_hpe() -> str:
    return (
        "MAC ADDR          VLAN ID  STATE          PORT INDEX       AGING TIME(s)\n"
    )


def _generate_hpe(entries: list[dict]) -> str:
    lines = [
        "MAC ADDR          VLAN ID  STATE          PORT INDEX       AGING TIME(s)",
    ]
    for e in entries:
        mac = e["mac"]
        vlan = e["vlan"]
        port = e["port"]
        lines.append(
            f"{mac:<18}{vlan:<9}{'Learned':<15}{port:<17} AGING"
        )
    return "\n".join(lines)


# --- IOS: show mac address-table ---


def _empty_ios() -> str:
    return (
        "          Mac Address Table\n"
        "-------------------------------------------\n"
        "\n"
        "Vlan    Mac Address       Type        Ports\n"
        "----    -----------       --------    -----\n"
        "Total Mac Addresses for this criterion: 0\n"
    )


def _generate_ios(entries: list[dict]) -> str:
    lines = [
        "          Mac Address Table",
        "-------------------------------------------",
        "",
        "Vlan    Mac Address       Type        Ports",
        "----    -----------       --------    -----",
    ]
    for e in entries:
        mac = e["mac"]
        vlan = e["vlan"]
        port = e["port"]
        lines.append(f"  {vlan:<6}{mac:<18}{'DYNAMIC':<12}{port}")
    lines.append(f"Total Mac Addresses for this criterion: {len(entries)}")
    return "\n".join(lines)


# --- NXOS: show mac address-table ---


def _empty_nxos() -> str:
    return (
        "Legend:\n"
        "        * - primary entry, G - Gateway MAC, (R) - Routed MAC, O - Overlay MAC\n"
        "        age - seconds since last seen,+ - primary entry using vPC Peer-Link\n"
        "\n"
        "   VLAN     MAC Address      Type      age     Secure   NTFY   Ports\n"
        "---------+-----------------+--------+---------+------+----+------------------\n"
    )


def _generate_nxos(entries: list[dict]) -> str:
    lines = [
        "Legend:",
        "        * - primary entry, G - Gateway MAC, (R) - Routed MAC, O - Overlay MAC",
        "        age - seconds since last seen,+ - primary entry using vPC Peer-Link",
        "",
        "   VLAN     MAC Address      Type      age     Secure   NTFY   Ports",
        "---------+-----------------+--------+---------+------+----+------------------",
    ]
    for e in entries:
        mac = e["mac"]
        vlan = e["vlan"]
        port = e["port"]
        lines.append(
            f"*   {vlan:<7}{mac:<17}{'dynamic':<9}{'0':<10}{'F':<7}{'F':<5}{port}"
        )
    return "\n".join(lines)
