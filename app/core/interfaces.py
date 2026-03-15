"""
Interface 名稱正規化與分類 — 集中定義。

所有介面名稱相關的 regex、正規化、分類邏輯都在此模組，
避免散落各處導致不一致。其他模組應從此 import。

支援廠商：Cisco IOS/IOS-XE/IOS-XR, NX-OS, HPE/Comware, Juniper, Linux
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# ═══════════════════════════════════════════════════════════════════
# 1. 介面類型定義 — 使用者可查閱的「系統支援介面類型清單」
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class InterfaceType:
    """一種介面類型的描述。"""
    canonical: str       # 正規化後的 prefix (e.g. "GE")
    category: str        # physical / lag / management / virtual / loopback / tunnel
    speed: str | None     # 頻寬 (e.g. "1G", "10G")
    description: str     # 中文說明
    vendors: str         # 適用廠商
    examples: list[str]  # 使用者可能填入的格式範例


# 依 category 分組的完整介面類型清單
INTERFACE_TYPES: list[InterfaceType] = [
    # ── 實體介面 ──
    InterfaceType("FE",  "physical", "100M", "Fast Ethernet (100M)",
                  "Cisco", ["FastEthernet0/1", "Fa0/1", "Fe0/1"]),
    InterfaceType("GE",  "physical", "1G",   "Gigabit Ethernet (1G)",
                  "Cisco / Juniper", ["GigabitEthernet0/0/1", "Gi0/1", "Ge0/1", "ge-0/0/1"]),
    InterfaceType("TE",  "physical", "10G",  "Ten Gigabit Ethernet (10G)",
                  "Cisco", ["TenGigabitEthernet1/0/1", "Te1/0/1"]),
    InterfaceType("XGE", "physical", "10G",  "Ten Gigabit Ethernet (10G)",
                  "HPE/Comware", ["Ten-GigabitEthernet1/0/1", "XGE1/0/1"]),
    InterfaceType("XE",  "physical", "10G",  "10G Ethernet",
                  "Juniper", ["xe-0/0/1"]),
    InterfaceType("Twe", "physical", "25G",  "Twenty-Five Gigabit Ethernet (25G)",
                  "Cisco", ["TwentyFiveGigabitEthernet1/0/1", "Twe1/0/1"]),
    InterfaceType("WGE", "physical", "25G",  "Twenty-Five Gigabit Ethernet (25G)",
                  "HPE/Comware", ["Twenty-FiveGigabitEthernet1/0/1", "WGE1/0/1"]),
    InterfaceType("Fo",  "physical", "40G",  "Forty Gigabit Ethernet (40G)",
                  "Cisco", ["FortyGigabitEthernet1/0/1", "Fo1/0/1"]),
    InterfaceType("FGE", "physical", "40G",  "Forty Gigabit Ethernet (40G)",
                  "HPE/Comware", ["FortyGigE1/0/1", "FGE1/0/1"]),
    InterfaceType("Hu",  "physical", "100G", "Hundred Gigabit Ethernet (100G)",
                  "Cisco", ["HundredGigabitEthernet0/0/0/1", "Hu0/0/0/1"]),
    InterfaceType("HGE", "physical", "100G", "Hundred Gigabit Ethernet (100G)",
                  "HPE/Comware", ["HundredGigE1/0/1", "HGE1/0/1"]),
    InterfaceType("ET",  "physical", "100G", "100G Ethernet",
                  "Juniper", ["et-0/0/1"]),
    InterfaceType("TwoHu",  "physical", "200G", "Two Hundred Gigabit Ethernet (200G)",
                  "Cisco", ["TwoHundredGigE0/0/0/1", "TwoHu0/0/0/1"]),
    InterfaceType("FourHu", "physical", "400G", "Four Hundred Gigabit Ethernet (400G)",
                  "Cisco", ["FourHundredGigE0/0/0/1", "FourHu0/0/0/1"]),
    InterfaceType("Eth", "physical", None,   "Ethernet (NX-OS)",
                  "Cisco NX-OS", ["Ethernet1/1", "Eth1/1"]),
    # ── LAG (鏈路聚合) ──
    InterfaceType("Po",   "lag", None, "Port-Channel (LAG)",
                  "Cisco IOS/IOS-XE/NX-OS", ["Port-Channel1", "Po1"]),
    InterfaceType("BE",   "lag", None, "Bundle-Ether (LAG)",
                  "Cisco IOS-XR", ["Bundle-Ether1", "BE1"]),
    InterfaceType("BAGG", "lag", None, "Bridge-Aggregation (LAG)",
                  "HPE/Comware", ["Bridge-Aggregation1", "BAGG1"]),
    InterfaceType("AE",   "lag", None, "Aggregated Ethernet (LAG)",
                  "Juniper", ["ae0"]),
    InterfaceType("BOND", "lag", None, "Bond (LAG)",
                  "Linux", ["bond0"]),
    # ── 管理介面 ──
    InterfaceType("Mgmt", "management", None, "Management Ethernet",
                  "Cisco IOS/NX-OS/IOS-XR", ["Management0", "Mgmt0", "mgmt0", "MEth0/0/CPU0/0"]),
    InterfaceType("MGE",  "management", None, "Management Ethernet",
                  "HPE/Comware", ["MGE0/0/0", "M-GigabitEthernet0/0/0"]),
    # ── 虛擬 / 邏輯介面 ──
    InterfaceType("Vlan", "virtual", None, "VLAN Interface (SVI)",
                  "Cisco / HPE", ["Vlan100", "Vlan-interface100"]),
    InterfaceType("Lo",   "loopback", None, "Loopback",
                  "Cisco / Juniper", ["Loopback0", "Lo0"]),
    InterfaceType("Tu",   "tunnel", None, "Tunnel",
                  "Cisco", ["Tunnel0", "Tu0"]),
    InterfaceType("NVE",  "virtual", None, "Network Virtualization Endpoint",
                  "Cisco NX-OS", ["Nve1", "NVE1"]),
    InterfaceType("BDI",  "virtual", None, "Bridge-Domain Interface",
                  "Cisco", ["BDI100"]),
    InterfaceType("VXLAN", "virtual", None, "VXLAN Interface",
                  "Cisco", ["Vxlan1"]),
    InterfaceType("IRB",  "virtual", None, "Integrated Routing and Bridging",
                  "Juniper", ["IRB.100"]),
    InterfaceType("Null", "virtual", None, "Null Interface",
                  "Cisco", ["Null0"]),
    # ── Linux ──
    InterfaceType("ENS",  "physical", None, "Predictable Network Interface",
                  "Linux", ["ens192"]),
    InterfaceType("ETH",  "physical", None, "Ethernet",
                  "Linux", ["eth0"]),
    InterfaceType("BR",   "virtual", None, "Bridge",
                  "Linux", ["br0"]),
]

# 快速查詢 map: canonical → InterfaceType
_TYPE_BY_CANONICAL: dict[str, InterfaceType] = {
    t.canonical: t for t in INTERFACE_TYPES
}

# ═══════════════════════════════════════════════════════════════════
# 2. 正規化 — 將各種長/短格式統一為 canonical prefix + 編號
# ═══════════════════════════════════════════════════════════════════

_PREFIX_MAP: list[tuple[re.Pattern[str], str]] = [
    # ── 長格式：最長 prefix 優先比對 ──
    # HPE/Comware（帶 hyphen 區別 Cisco）
    (re.compile(r"(?i)^Twenty-FiveGigabitEthernet"), "WGE"),
    (re.compile(r"(?i)^Twenty-FiveGigE"), "WGE"),
    (re.compile(r"(?i)^Ten-GigabitEthernet"), "XGE"),
    (re.compile(r"(?i)^TenGigE"), "XGE"),
    (re.compile(r"(?i)^FourHundredGigE"), "FourHu"),
    (re.compile(r"(?i)^TwoHundredGigE"), "TwoHu"),
    (re.compile(r"(?i)^HundredGigE"), "HGE"),
    (re.compile(r"(?i)^FortyGigE"), "FGE"),
    (re.compile(r"(?i)^Bridge-Aggregation"), "BAGG"),
    (re.compile(r"(?i)^M-GigabitEthernet"), "MGE"),            # HPE Mgmt
    (re.compile(r"(?i)^Vlan-interface\s*"), "Vlan"),
    # Cisco IOS / IOS-XE / IOS-XR
    (re.compile(r"(?i)^TwentyFiveGigabitEthernet"), "Twe"),
    (re.compile(r"(?i)^TwentyFiveGigE"), "Twe"),
    (re.compile(r"(?i)^HundredGigabitEthernet"), "Hu"),
    (re.compile(r"(?i)^FortyGigabitEthernet"), "Fo"),
    (re.compile(r"(?i)^TenGigabitEthernet"), "TE"),
    (re.compile(r"(?i)^GigabitEthernet"), "GE"),
    (re.compile(r"(?i)^FastEthernet"), "FE"),
    (re.compile(r"(?i)^Bundle-Ether"), "BE"),
    (re.compile(r"(?i)^Port-[Cc]hannel"), "Po"),
    (re.compile(r"(?i)^Management"), "Mgmt"),
    (re.compile(r"(?i)^Loopback"), "Lo"),
    (re.compile(r"(?i)^Tunnel"), "Tu"),
    (re.compile(r"(?i)^Vxlan"), "VXLAN"),
    # NX-OS
    (re.compile(r"(?i)^Ethernet"), "Eth"),
    (re.compile(r"(?i)^Nve"), "NVE"),
    # Juniper
    (re.compile(r"(?i)^ge-"), "GE"),
    (re.compile(r"(?i)^xe-"), "XE"),
    (re.compile(r"(?i)^et-"), "ET"),
    (re.compile(r"(?i)^ae(?=\d)"), "AE"),
    (re.compile(r"(?i)^IRB\."), "IRB"),
    # ── 短格式（2-6 字元 + 數字）──
    (re.compile(r"(?i)^FourHu(?=\d)"), "FourHu"),
    (re.compile(r"(?i)^TwoHu(?=\d)"), "TwoHu"),
    (re.compile(r"(?i)^XGE(?=[\d/])"), "XGE"),
    (re.compile(r"(?i)^WGE(?=[\d/])"), "WGE"),
    (re.compile(r"(?i)^FGE(?=[\d/])"), "FGE"),
    (re.compile(r"(?i)^HGE(?=[\d/])"), "HGE"),
    (re.compile(r"(?i)^BAGG(?=[\d.])"), "BAGG"),
    (re.compile(r"(?i)^MGE(?=[\d/])"), "MGE"),
    (re.compile(r"(?i)^MEth"), "Mgmt"),
    (re.compile(r"(?i)^Twe(?=\d)"), "Twe"),
    (re.compile(r"(?i)^Te(?=\d)"), "TE"),
    (re.compile(r"(?i)^Gi(?=\d)"), "GE"),
    (re.compile(r"(?i)^Ge(?=\d)"), "GE"),
    (re.compile(r"(?i)^Fa(?=\d)"), "FE"),
    (re.compile(r"(?i)^Fe(?=\d)"), "FE"),
    (re.compile(r"(?i)^Fo(?=\d)"), "Fo"),
    (re.compile(r"(?i)^Hu(?=\d)"), "Hu"),
    (re.compile(r"^Eth(?=[\d/])"), "Eth"),
    (re.compile(r"(?i)^Po(?=[\d.])"), "Po"),
    (re.compile(r"(?i)^BE(?=\d)"), "BE"),
    (re.compile(r"(?i)^NVE(?=\d)"), "NVE"),
    (re.compile(r"(?i)^BDI(?=\d)"), "BDI"),
    (re.compile(r"(?i)^Tu(?=\d)"), "Tu"),
    (re.compile(r"(?i)^Lo(?=\d)"), "Lo"),
    (re.compile(r"(?i)^Mgmt(?=\d)"), "Mgmt"),
    (re.compile(r"(?i)^Null(?=\d)"), "Null"),
    (re.compile(r"(?i)^Vlan(?=\d)"), "Vlan"),
    (re.compile(r"(?i)^VXLAN(?=\d)"), "VXLAN"),
    # Linux
    (re.compile(r"^ens(?=\d)"), "ENS"),
    (re.compile(r"^bond(?=\d)"), "BOND"),
    (re.compile(r"^br(?=\d)"), "BR"),
    (re.compile(r"^eth(?=\d)"), "ETH"),
]


def normalize_interface_name(name: str) -> str:
    """將介面名稱正規化為 canonical 短格式。

    例如:
        "GigabitEthernet0/0/1" → "GE0/0/1"
        "Ten-GigabitEthernet1/0/25" → "XGE1/0/25"
        "Bridge-Aggregation1" → "BAGG1"
        "xe-0/0/1" → "XE0/0/1"
    """
    if not name:
        return name
    for pattern, replacement in _PREFIX_MAP:
        m = pattern.match(name)
        if m:
            return replacement + name[m.end():]
    return name


# ═══════════════════════════════════════════════════════════════════
# 3. 介面分類判斷
# ═══════════════════════════════════════════════════════════════════

# 管理介面 — 正規化後的 prefix
_MANAGEMENT_PREFIXES = ("Mgmt", "MGE", "M-")

# 管理介面 regex（用於尚未正規化的原始名稱）
_MGMT_IFACE_RE = re.compile(
    r"(?i)^(Mgmt|MGE|M-|mgmt|management|MEth)",
)


def is_management_interface(name: str) -> bool:
    """判斷是否為管理介面（正規化前後均可）。"""
    if not name:
        return False
    return bool(_MGMT_IFACE_RE.match(name))


# LAG / Port-Channel — 正規化後的 prefix
_PORT_CHANNEL_PREFIXES = ("BAGG", "Po", "BE", "AE", "BOND")


def is_port_channel(name: str | None) -> bool:
    """判斷正規化後的介面是否為 port-channel / LAG 類型。"""
    if not name:
        return False
    return name.startswith(_PORT_CHANNEL_PREFIXES)


# 非實體介面（SNMP 採集時跳過）
_NON_PHYSICAL_PREFIXES = (
    "Loopback", "Lo",
    "Vlan", "Vl",
    "Null", "Nu",
    "Tunnel", "Tu",
    "mgmt", "Management", "Mgmt", "MGE",
    "Cpu", "cpu",
    "Stack", "InLoopBack",
    "Register", "Aux",
)


def is_non_physical_interface(name: str) -> bool:
    """判斷是否為非實體介面（Loopback / Vlan / Null / Tunnel / Mgmt 等）。"""
    if not name:
        return False
    return name.startswith(_NON_PHYSICAL_PREFIXES)


# 拓撲管理介面 regex（含 Loopback, Vlan0 等不應影響階層判定的連線）
_TOPOLOGY_MGMT_RE = re.compile(
    r"(?i)^(Mgmt|mgmt|management|MGE|M-|MEth|Lo\d|Loopback|Vlan\s*0$)",
)


def is_topology_management_link(name: str) -> bool:
    """判斷介面是否為拓撲中的管理/非實體連線（不影響階層計算）。"""
    if not name:
        return False
    return bool(_TOPOLOGY_MGMT_RE.match(name))


# ═══════════════════════════════════════════════════════════════════
# 4. API 用 — 回傳支援的介面類型清單
# ═══════════════════════════════════════════════════════════════════

def get_supported_interface_types() -> list[dict]:
    """回傳系統支援的介面類型清單（供 API / 前端使用）。"""
    return [
        {
            "canonical": t.canonical,
            "category": t.category,
            "speed": t.speed,
            "description": t.description,
            "vendors": t.vendors,
            "examples": t.examples,
        }
        for t in INTERFACE_TYPES
    ]
