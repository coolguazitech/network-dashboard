"""
Mock SNMP data generators.

根據設備 IP + vendor type 產生模擬的 SNMP OID/value pairs，
供 MockSnmpEngine 回傳給 collector。

設計原則：
- 與 mock_server/generators 的介面名稱保持一致
  (HPE: GE1/0/x, XGE1/0/1, BAGG1; IOS: Gi1/0/x, Te1/1/1, Po1;
   NXOS: Eth1/x, Eth1/49, Po1)
- 使用 deterministic hash（基於 IP）確保同一設備每次回傳一致
- 每次採集週期有 ~5% 機率觸發故障，模擬真實環境
- uplink 鄰居從 DB 讀取 uplink_expectations 期望值
"""
from __future__ import annotations

import hashlib
import logging
import random as _random
import time
from typing import Any

from app.snmp.oid_maps import (
    CISCO_CDP_CACHE_DEVICE_ID,
    CISCO_CDP_CACHE_DEVICE_PORT,
    CISCO_ENV_FAN_DESCR,
    CISCO_ENV_FAN_STATE,
    CISCO_ENV_SUPPLY_DESCR,
    CISCO_ENV_SUPPLY_STATE,
    CISCO_VTP_VLAN_STATE,
    DOT1D_BASE_PORT_IF_INDEX,
    DOT1D_TP_FDB_PORT,
    DOT1Q_TP_FDB_PORT,
    DOT3AD_AGG_PORT_ACTOR_OPER_STATE,
    DOT3AD_AGG_PORT_ATTACHED_AGG_ID,
    DOT3_STATS_DUPLEX,
    ENT_PHYSICAL_CLASS,
    ENT_PHYSICAL_NAME,
    HH3C_ENTITY_EXT_ERROR_STATUS,
    HH3C_TRANSCEIVER_RX_POWER,
    HH3C_TRANSCEIVER_TEMPERATURE,
    HH3C_TRANSCEIVER_TX_POWER,
    HH3C_TRANSCEIVER_VOLTAGE,
    IF_HIGH_SPEED,
    IF_IN_ERRORS,
    IF_NAME,
    IF_OPER_STATUS,
    IF_OUT_ERRORS,
    LLDP_LOC_PORT_DESC,
    LLDP_REM_PORT_DESC,
    LLDP_REM_PORT_ID,
    LLDP_REM_SYS_NAME,
    SYS_DESCR,
    SYS_OBJECT_ID,
)


# ── Device profile definitions ───────────────────────────────────

# HPE Comware interfaces (matches mock_server/generators/interface_status.py)
_HPE_INTERFACES: list[tuple[str, int, int]] = [
    # (ifName, ifIndex, speed_mbps)
    ("GE1/0/1", 1, 1000),
    ("GE1/0/2", 2, 1000),
    ("GE1/0/3", 3, 1000),
    ("GE1/0/4", 4, 1000),
    ("GE1/0/5", 5, 1000),
    ("GE1/0/6", 6, 1000),
    ("GE1/0/7", 7, 1000),
    ("GE1/0/8", 8, 1000),
    ("GE1/0/9", 9, 1000),
    ("GE1/0/10", 10, 1000),
    ("GE1/0/11", 11, 1000),
    ("GE1/0/12", 12, 1000),
    ("GE1/0/13", 13, 1000),
    ("GE1/0/14", 14, 1000),
    ("GE1/0/15", 15, 1000),
    ("GE1/0/16", 16, 1000),
    ("GE1/0/17", 17, 1000),
    ("GE1/0/18", 18, 1000),
    ("XGE1/0/1", 19, 10000),
    ("BAGG1", 20, 10000),
]

_IOS_INTERFACES: list[tuple[str, int, int]] = [
    ("Gi1/0/1", 1, 1000),
    ("Gi1/0/2", 2, 1000),
    ("Gi1/0/3", 3, 1000),
    ("Gi1/0/4", 4, 1000),
    ("Gi1/0/5", 5, 1000),
    ("Gi1/0/6", 6, 1000),
    ("Gi1/0/7", 7, 1000),
    ("Gi1/0/8", 8, 1000),
    ("Gi1/0/9", 9, 1000),
    ("Gi1/0/10", 10, 1000),
    ("Gi1/0/11", 11, 1000),
    ("Gi1/0/12", 12, 1000),
    ("Gi1/0/13", 13, 1000),
    ("Gi1/0/14", 14, 1000),
    ("Gi1/0/15", 15, 1000),
    ("Gi1/0/16", 16, 1000),
    ("Gi1/0/17", 17, 1000),
    ("Gi1/0/18", 18, 1000),
    ("Te1/1/1", 19, 10000),
    ("Po1", 20, 10000),
]

_NXOS_INTERFACES: list[tuple[str, int, int]] = [
    ("Eth1/1", 1, 1000),
    ("Eth1/2", 2, 1000),
    ("Eth1/3", 3, 1000),
    ("Eth1/4", 4, 1000),
    ("Eth1/5", 5, 1000),
    ("Eth1/6", 6, 1000),
    ("Eth1/7", 7, 1000),
    ("Eth1/8", 8, 1000),
    ("Eth1/9", 9, 1000),
    ("Eth1/10", 10, 1000),
    ("Eth1/11", 11, 1000),
    ("Eth1/12", 12, 1000),
    ("Eth1/13", 13, 1000),
    ("Eth1/14", 14, 1000),
    ("Eth1/15", 15, 1000),
    ("Eth1/16", 16, 1000),
    ("Eth1/17", 17, 1000),
    ("Eth1/18", 18, 1000),
    ("Eth1/49", 19, 10000),
    ("Po1", 20, 10000),
]

# Vendor sysDescr templates
_SYS_DESCR_HPE = (
    "HPE Comware Platform Software, Software Version 7.1.070, "
    "Release 6728P06\n"
    "HPE FF 5130-24G-4SFP+ EI Switch"
)
_SYS_DESCR_IOS = (
    "Cisco IOS Software, C3750E Software (C3750E-UNIVERSALK9-M), "
    "Version 15.2(7)E2, RELEASE SOFTWARE (fc3)"
)
_SYS_DESCR_NXOS = (
    "Cisco NX-OS(tm) n9000, Software (n9000-dk9), "
    "Version 9.3(8), RELEASE SOFTWARE"
)

# Fallback LLDP neighbors (used when DB has no uplink_expectations)
_DEFAULT_NEIGHBORS: list[tuple[str, str, str]] = [
    ("GigabitEthernet1/0/49", "SW-DEFAULT-CORE-01", "HGE1/0/1"),
    ("GigabitEthernet1/0/50", "SW-DEFAULT-CORE-02", "HGE1/0/1"),
]

# Valid VLANs (matches mock_server)
_VALID_VLANS = [10, 20, 100, 200]

logger = logging.getLogger(__name__)

# ── Helpers ───────────────────────────────────────────────────────

def _det_hash(ip: str, salt: str = "") -> int:
    """Deterministic hash from IP + salt."""
    return int(hashlib.md5(f"{ip}:{salt}".encode()).hexdigest(), 16)


def _det_float(ip: str, salt: str = "") -> float:
    """Deterministic float in [0, 1)."""
    return (_det_hash(ip, salt) % 10000) / 10000.0


def _should_fail_this_cycle(ip: str, fail_rate: float = 0.05) -> bool:
    """Per-cycle random failure: ~5% chance each collection round.

    Uses a time-bucket (60s granularity) + IP as seed so the result
    is stable within one collection cycle but changes across cycles.
    """
    bucket = int(time.time()) // 60  # changes every minute
    seed = _det_hash(ip, f"cycle_{bucket}")
    return (seed % 10000) / 10000.0 < fail_rate


# ── Uplink neighbor lookup (from DB) ──────────────────────────────

# Cache: ip → [(local_interface, expected_neighbor, expected_interface)]
_uplink_cache: dict[str, list[tuple[str, str, str]]] = {}
_uplink_cache_ts: float = 0.0
_UPLINK_CACHE_TTL = 300.0  # 5 minutes


def _get_uplink_neighbors(ip: str) -> list[tuple[str, str, str]]:
    """Query DB for expected uplink neighbors by device IP.

    Returns [(local_interface, neighbor_hostname, neighbor_interface), ...]
    Falls back to _DEFAULT_NEIGHBORS if no DB data.
    """
    global _uplink_cache, _uplink_cache_ts  # noqa: PLW0603

    now = time.time()
    if now - _uplink_cache_ts > _UPLINK_CACHE_TTL:
        _uplink_cache.clear()
        _uplink_cache_ts = now

    if ip in _uplink_cache:
        return _uplink_cache[ip]

    try:
        from sqlalchemy import create_engine, text
        from app.core.config import settings

        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            # ip → hostname
            row = conn.execute(
                text(
                    "SELECT new_hostname, new_ip_address, old_hostname, "
                    "old_ip_address, maintenance_id "
                    "FROM maintenance_device_list "
                    "WHERE (old_ip_address = :ip OR new_ip_address = :ip) "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {"ip": ip},
            ).fetchone()

            if row is None:
                _uplink_cache[ip] = _DEFAULT_NEIGHBORS
                return _DEFAULT_NEIGHBORS

            new_host, new_ip, old_host, old_ip, mid = (
                row[0], row[1], row[2], row[3], row[4],
            )
            hostname = new_host if ip == new_ip else old_host
            if not hostname:
                _uplink_cache[ip] = _DEFAULT_NEIGHBORS
                return _DEFAULT_NEIGHBORS

            rows = conn.execute(
                text(
                    "SELECT local_interface, expected_neighbor, "
                    "expected_interface "
                    "FROM uplink_expectations "
                    "WHERE maintenance_id = :mid AND hostname = :host"
                ),
                {"mid": mid, "host": hostname},
            ).fetchall()

        if rows:
            result = [(r[0], r[1], r[2]) for r in rows]
        else:
            result = _DEFAULT_NEIGHBORS

        _uplink_cache[ip] = result
        return result

    except Exception:
        logger.debug("Failed to query uplink expectations for %s", ip)
        _uplink_cache[ip] = _DEFAULT_NEIGHBORS
        return _DEFAULT_NEIGHBORS


def _get_vendor(ip: str) -> str:
    """Deterministic vendor assignment based on IP.

    ~50% HPE, ~25% IOS, ~25% NXOS
    """
    v = _det_hash(ip, "vendor") % 4
    if v <= 1:
        return "hpe"
    elif v == 2:
        return "ios"
    else:
        return "nxos"


def _get_interfaces(vendor: str) -> list[tuple[str, int, int]]:
    if vendor == "hpe":
        return _HPE_INTERFACES
    elif vendor == "ios":
        return _IOS_INTERFACES
    else:
        return _NXOS_INTERFACES


# ── Scalar OID generators ────────────────────────────────────────

def mock_get(ip: str, oid: str) -> dict[str, Any]:
    """Generate mock response for SNMP GET (scalar OIDs)."""
    vendor = _get_vendor(ip)
    result: dict[str, Any] = {}

    if oid == SYS_OBJECT_ID:
        if vendor == "hpe":
            result[SYS_OBJECT_ID] = "1.3.6.1.4.1.25506.11.1.136"
        else:
            result[SYS_OBJECT_ID] = "1.3.6.1.4.1.9.1.2066"

    elif oid == SYS_DESCR:
        if vendor == "hpe":
            result[SYS_DESCR] = _SYS_DESCR_HPE
        elif vendor == "ios":
            result[SYS_DESCR] = _SYS_DESCR_IOS
        else:
            result[SYS_DESCR] = _SYS_DESCR_NXOS

    return result


# ── Table walk generators ────────────────────────────────────────

def mock_walk(
    ip: str,
    oid_prefix: str,
    *,
    community: str = "",
) -> list[tuple[str, str]]:
    """Generate mock response for SNMP WALK (table OIDs).

    NOTE: Vendor-specific OID sections are NOT gated by vendor.
    The collector decides which OIDs to walk based on DB vendor,
    so we must return data for ANY recognised OID prefix regardless
    of what ``_get_vendor(ip)`` returns.

    community: The SNMP community string. For Cisco IOS per-VLAN
    walks, this will be "community@vlanID" — used to extract the
    VLAN context for BRIDGE-MIB MAC table responses.

    Failures: ~5% chance per device per collection cycle (60s bucket).
    """
    vendor = _get_vendor(ip)
    interfaces = _get_interfaces(vendor)

    # Per-cycle randomness: seed changes every 60s so data varies
    bucket = int(time.time()) // 60
    rng = _random.Random(_det_hash(ip, f"{oid_prefix}_{bucket}"))
    fails = _should_fail_this_cycle(ip)

    # ── IF-MIB ────────────────────────────────────────────────
    if oid_prefix == IF_NAME:
        return [(f"{IF_NAME}.{idx}", name) for name, idx, _ in interfaces]

    if oid_prefix == IF_OPER_STATUS:
        results = []
        for name, idx, _ in interfaces:
            if fails and idx in (3, 4, 5):
                status = "2"  # down
            elif idx <= 18 and rng.random() < 0.02:
                status = "2"  # per-port ~2% independent down
            else:
                status = "1"  # up
            results.append((f"{IF_OPER_STATUS}.{idx}", status))
        return results

    if oid_prefix == IF_HIGH_SPEED:
        results = []
        for _, idx, speed in interfaces:
            if idx <= 18 and speed == 1000 and rng.random() < 0.03:
                speed = 100  # ~3% auto-negotiation fallback
            results.append((f"{IF_HIGH_SPEED}.{idx}", str(speed)))
        return results

    if oid_prefix == IF_IN_ERRORS:
        results = []
        for _, idx, _ in interfaces:
            errors = rng.randint(0, 5) if rng.random() < 0.15 else 0
            results.append((f"{IF_IN_ERRORS}.{idx}", str(errors)))
        return results

    if oid_prefix == IF_OUT_ERRORS:
        results = []
        for _, idx, _ in interfaces:
            errors = rng.randint(0, 3) if rng.random() < 0.10 else 0
            results.append((f"{IF_OUT_ERRORS}.{idx}", str(errors)))
        return results

    # ── EtherLike-MIB ─────────────────────────────────────────
    if oid_prefix == DOT3_STATS_DUPLEX:
        results = []
        for _, idx, _ in interfaces:
            if idx <= 18 and rng.random() < 0.03:
                duplex = "2"  # ~3% half duplex
            else:
                duplex = "3"  # full duplex
            results.append((f"{DOT3_STATS_DUPLEX}.{idx}", duplex))
        return results

    # ── Q-BRIDGE-MIB (MAC table) ─────────────────────────────
    if oid_prefix == DOT1Q_TP_FDB_PORT:
        return _mock_mac_table(ip, vendor, interfaces, rng, fails)

    # ── BRIDGE-MIB (bridge port → ifIndex) ────────────────────
    if oid_prefix == DOT1D_BASE_PORT_IF_INDEX:
        # bridge port N → ifIndex N (1:1 mapping for simplicity)
        return [
            (f"{DOT1D_BASE_PORT_IF_INDEX}.{idx}", str(idx))
            for _, idx, _ in interfaces
            if idx <= 18  # only physical ports, not uplink/LAG
        ]

    # ── CISCO-VTP-MIB (VLAN list) ─────────────────────────────
    if oid_prefix == CISCO_VTP_VLAN_STATE:
        # vtpVlanState.{domain=1}.{vlanID} = 1 (operational)
        return [
            (f"{CISCO_VTP_VLAN_STATE}.1.{v}", "1")
            for v in _VALID_VLANS
        ]

    # ── BRIDGE-MIB per-VLAN MAC table (Cisco IOS) ──────────────
    if oid_prefix == DOT1D_TP_FDB_PORT:
        vlan_id = _extract_vlan_from_community(community)
        return _mock_bridge_mac_table(
            ip, vendor, interfaces, rng, fails, vlan_id,
        )

    # ── LLDP-MIB ──────────────────────────────────────────────
    if oid_prefix == LLDP_REM_SYS_NAME:
        neighbors = _get_uplink_neighbors(ip)
        if fails and len(neighbors) > 1:
            neighbors = neighbors[:1]  # lose one neighbor on failure
        return _mock_lldp_rem_sys_name(interfaces, neighbors)
    if oid_prefix == LLDP_REM_PORT_ID:
        neighbors = _get_uplink_neighbors(ip)
        if fails and len(neighbors) > 1:
            neighbors = neighbors[:1]
        return _mock_lldp_rem_port_id(interfaces, neighbors)
    if oid_prefix == LLDP_REM_PORT_DESC:
        neighbors = _get_uplink_neighbors(ip)
        if fails and len(neighbors) > 1:
            neighbors = neighbors[:1]
        return _mock_lldp_rem_port_desc(interfaces, neighbors)
    if oid_prefix == LLDP_LOC_PORT_DESC:
        return _mock_lldp_loc_port_desc(interfaces)

    # ── IEEE8023-LAG-MIB ──────────────────────────────────────
    if oid_prefix == DOT3AD_AGG_PORT_ATTACHED_AGG_ID:
        return _mock_lag_attached_agg(interfaces)
    if oid_prefix == DOT3AD_AGG_PORT_ACTOR_OPER_STATE:
        return _mock_lag_actor_state(interfaces, fails)

    # ── HPE/H3C MIBs (no vendor guard — collector decides) ────
    if oid_prefix == HH3C_ENTITY_EXT_ERROR_STATUS:
        return _mock_hpe_entity_error_status(fails)
    if oid_prefix == HH3C_TRANSCEIVER_TEMPERATURE:
        return _mock_hpe_transceiver_temp(interfaces, rng)
    if oid_prefix == HH3C_TRANSCEIVER_VOLTAGE:
        return _mock_hpe_transceiver_voltage(interfaces, rng)
    if oid_prefix == HH3C_TRANSCEIVER_TX_POWER:
        return _mock_hpe_transceiver_tx(interfaces, rng)
    if oid_prefix == HH3C_TRANSCEIVER_RX_POWER:
        return _mock_hpe_transceiver_rx(interfaces, rng)

    # ── Cisco MIBs (no vendor guard — collector decides) ──────
    if oid_prefix == CISCO_ENV_FAN_STATE:
        return _mock_cisco_fan_state(fails)
    if oid_prefix == CISCO_ENV_FAN_DESCR:
        return _mock_cisco_fan_descr()
    if oid_prefix == CISCO_ENV_SUPPLY_STATE:
        return _mock_cisco_supply_state(fails)
    if oid_prefix == CISCO_ENV_SUPPLY_DESCR:
        return _mock_cisco_supply_descr()
    if oid_prefix == CISCO_CDP_CACHE_DEVICE_ID:
        neighbors = _get_uplink_neighbors(ip)
        if fails and len(neighbors) > 1:
            neighbors = neighbors[:1]
        return _mock_cdp_device_id(interfaces, neighbors)
    if oid_prefix == CISCO_CDP_CACHE_DEVICE_PORT:
        neighbors = _get_uplink_neighbors(ip)
        if fails and len(neighbors) > 1:
            neighbors = neighbors[:1]
        return _mock_cdp_device_port(interfaces, neighbors)
    # Cisco entity sensor / transceiver MIBs
    if oid_prefix in (
        "1.3.6.1.4.1.9.9.91.1.1.1.1.4",  # CISCO_ENT_SENSOR_VALUE
        "1.3.6.1.4.1.9.9.91.1.1.1.1.1",  # TYPE
        "1.3.6.1.4.1.9.9.91.1.1.1.1.2",  # SCALE
        "1.3.6.1.4.1.9.9.91.1.1.1.1.3",  # PRECISION
    ):
        return _mock_cisco_sensor(oid_prefix, interfaces, rng)
    if oid_prefix == "1.3.6.1.2.1.47.1.1.1.1.4":  # entPhysicalContainedIn
        return _mock_cisco_contained_in(interfaces)

    # ── ENTITY-MIB (shared, used by both HPE and Cisco) ───────
    if oid_prefix == ENT_PHYSICAL_NAME:
        # Return both HPE-style and Cisco-style entity names
        return _mock_hpe_entity_name() + _mock_cisco_entity_name(interfaces)
    if oid_prefix == ENT_PHYSICAL_CLASS:
        return _mock_hpe_entity_class()

    # Default: empty walk
    return []


# ── Helpers (VLAN context) ────────────────────────────────────────

def _extract_vlan_from_community(community: str) -> int | None:
    """Extract VLAN ID from 'community@vlanID' format.

    Returns None if community doesn't contain '@' (not per-VLAN context).
    """
    if "@" not in community:
        return None
    try:
        return int(community.rsplit("@", 1)[1])
    except (ValueError, IndexError):
        return None


# ── BRIDGE-MIB per-VLAN MAC table mock ────────────────────────────

def _mock_bridge_mac_table(
    ip: str,
    vendor: str,
    interfaces: list[tuple[str, int, int]],
    rng: _random.Random,
    fails: bool,
    vlan_id: int | None,
) -> list[tuple[str, str]]:
    """Generate mock BRIDGE-MIB dot1dTpFdbPort entries for a single VLAN.

    Index format: {o1}.{o2}.{o3}.{o4}.{o5}.{o6} = bridge_port
    (no VLAN in index — VLAN is from community@vlanID context)
    """
    if fails or vlan_id is None:
        return []

    all_macs = _get_client_macs()
    if not all_macs:
        return []

    try:
        from sqlalchemy import create_engine, text
        from app.core.config import settings

        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT DISTINCT new_ip_address "
                     "FROM maintenance_device_list "
                     "ORDER BY new_ip_address"),
            ).fetchall()
        device_ips = [r[0] for r in rows if r[0]]
    except Exception:
        device_ips = []

    if not device_ips or ip not in device_ips:
        device_ips = [ip]

    results: list[tuple[str, str]] = []
    for mac in all_macs:
        assigned_ip = device_ips[_det_hash(mac, "device") % len(device_ips)]
        if assigned_ip != ip:
            continue

        # Determine VLAN for this MAC — must match requested VLAN context
        h = _det_hash(mac, "port")
        mac_vlan = _VALID_VLANS[h % len(_VALID_VLANS)]
        if mac_vlan != vlan_id:
            continue

        bridge_port = h % 18 + 1
        octets = [int(o, 16) for o in mac.split(":")]
        oct_str = ".".join(str(o) for o in octets)
        oid = f"{DOT1D_TP_FDB_PORT}.{oct_str}"
        results.append((oid, str(bridge_port)))

    return results


# ── MAC table mock ────────────────────────────────────────────────

# Cache: maintenance_id → [(mac_address, ...)]
_mac_list_cache: list[str] = []
_mac_list_cache_ts: float = 0.0
_MAC_LIST_CACHE_TTL = 300.0  # 5 minutes


def _get_client_macs() -> list[str]:
    """Load client MAC addresses from maintenance_mac_list (cached)."""
    global _mac_list_cache, _mac_list_cache_ts  # noqa: PLW0603

    now = time.time()
    if _mac_list_cache and now - _mac_list_cache_ts < _MAC_LIST_CACHE_TTL:
        return _mac_list_cache

    try:
        from sqlalchemy import create_engine, text
        from app.core.config import settings

        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT mac_address FROM maintenance_mac_list "
                     "ORDER BY mac_address"),
            ).fetchall()

        _mac_list_cache = [r[0].upper() for r in rows]
        _mac_list_cache_ts = now
        return _mac_list_cache

    except Exception:
        logger.debug("Failed to query maintenance_mac_list")
        return _mac_list_cache


def _mock_mac_table(
    ip: str,
    vendor: str,
    interfaces: list[tuple[str, int, int]],
    rng: _random.Random,
    fails: bool,
) -> list[tuple[str, str]]:
    """Generate mock Q-BRIDGE MAC table entries using real client MACs.

    Each MAC is deterministically assigned to one device IP via hash.
    Only MACs assigned to *this* device are included in its MAC table.
    """
    if fails:
        return []

    all_macs = _get_client_macs()
    if not all_macs:
        return []

    # Get all device IPs to determine assignment
    try:
        from sqlalchemy import create_engine, text
        from app.core.config import settings

        engine = create_engine(settings.database_url, pool_pre_ping=True)
        with engine.connect() as conn:
            rows = conn.execute(
                text("SELECT DISTINCT new_ip_address "
                     "FROM maintenance_device_list "
                     "ORDER BY new_ip_address"),
            ).fetchall()
        device_ips = [r[0] for r in rows if r[0]]
    except Exception:
        device_ips = []

    if not device_ips or ip not in device_ips:
        # Fallback: assign by hash mod
        device_ips = [ip]

    # Assign each MAC to a device deterministically
    results: list[tuple[str, str]] = []
    for mac in all_macs:
        assigned_ip = device_ips[_det_hash(mac, "device") % len(device_ips)]
        if assigned_ip != ip:
            continue

        # Determine bridge port and VLAN for this MAC
        h = _det_hash(mac, "port")
        bridge_port = h % 18 + 1  # physical ports 1-18
        vlan = _VALID_VLANS[h % len(_VALID_VLANS)]

        # Convert MAC string "AA:BB:CC:DD:EE:FF" to OID decimal octets
        octets = [int(o, 16) for o in mac.split(":")]
        oct_str = ".".join(str(o) for o in octets)
        oid = f"{DOT1Q_TP_FDB_PORT}.{vlan}.{oct_str}"
        results.append((oid, str(bridge_port)))

    return results


# ── LLDP mock ─────────────────────────────────────────────────────

def _mock_lldp_rem_sys_name(
    interfaces: list[tuple[str, int, int]],
    neighbors: list[tuple[str, str, str]],
) -> list[tuple[str, str]]:
    """LLDP remote sys name. Index: timemark.localPortNum.remIndex"""
    uplink_idx = interfaces[-2][1]  # XGE/Te/Eth1/49
    results = []
    for i, (_, neighbor_host, _) in enumerate(neighbors):
        # timemark=0, localPortNum=uplink_idx, remIndex=i+1
        oid = f"{LLDP_REM_SYS_NAME}.0.{uplink_idx}.{i + 1}"
        results.append((oid, neighbor_host))
    return results


def _mock_lldp_rem_port_id(
    interfaces: list[tuple[str, int, int]],
    neighbors: list[tuple[str, str, str]],
) -> list[tuple[str, str]]:
    uplink_idx = interfaces[-2][1]
    results = []
    for i, (_, _, remote_intf) in enumerate(neighbors):
        oid = f"{LLDP_REM_PORT_ID}.0.{uplink_idx}.{i + 1}"
        results.append((oid, remote_intf))
    return results


def _mock_lldp_rem_port_desc(
    interfaces: list[tuple[str, int, int]],
    neighbors: list[tuple[str, str, str]],
) -> list[tuple[str, str]]:
    uplink_idx = interfaces[-2][1]
    results = []
    for i, (_, _, remote_intf) in enumerate(neighbors):
        oid = f"{LLDP_REM_PORT_DESC}.0.{uplink_idx}.{i + 1}"
        results.append((oid, remote_intf))
    return results


def _mock_lldp_loc_port_desc(
    interfaces: list[tuple[str, int, int]],
) -> list[tuple[str, str]]:
    """LLDP local port description. Index: localPortNum"""
    return [
        (f"{LLDP_LOC_PORT_DESC}.{idx}", name)
        for name, idx, _ in interfaces
    ]


# ── LAG mock ──────────────────────────────────────────────────────

def _mock_lag_attached_agg(
    interfaces: list[tuple[str, int, int]],
) -> list[tuple[str, str]]:
    """dot3adAggPortAttachedAggID: member ifIndex → aggregate ifIndex.

    Attach the last two physical interfaces to the LAG (last interface).
    """
    agg_ifindex = interfaces[-1][1]   # BAGG1 / Po1
    member1 = interfaces[-3][1]       # GE1/0/18 / Gi1/0/18 / Eth1/18
    member2 = interfaces[-2][1]       # XGE1/0/1 / Te1/1/1 / Eth1/49
    return [
        (f"{DOT3AD_AGG_PORT_ATTACHED_AGG_ID}.{member1}", str(agg_ifindex)),
        (f"{DOT3AD_AGG_PORT_ATTACHED_AGG_ID}.{member2}", str(agg_ifindex)),
    ]


def _mock_lag_actor_state(
    interfaces: list[tuple[str, int, int]],
    fails: bool,
) -> list[tuple[str, str]]:
    """dot3adAggPortActorOperState: member sync status.

    Bits: 0=lacpActivity, 1=lacpTimeout, 2=aggregation, 3=synchronization
    Sync bit mask = 0x08 (bit 3).
    0x3D (61) = all bits set including sync → "up"
    0x37 (55) = sync bit unset → "down"
    """
    member1 = interfaces[-3][1]
    member2 = interfaces[-2][1]
    state_synced = "61"     # 0x3D — bit 3 set
    state_not_synced = "55" # 0x37 — bit 3 unset
    return [
        (f"{DOT3AD_AGG_PORT_ACTOR_OPER_STATE}.{member1}", state_synced),
        (f"{DOT3AD_AGG_PORT_ACTOR_OPER_STATE}.{member2}",
         state_not_synced if fails else state_synced),
    ]


# ── HPE fan/power/transceiver mock ───────────────────────────────

def _mock_hpe_entity_class() -> list[tuple[str, str]]:
    """ENTITY-MIB entPhysicalClass for HPE.

    Entity indices 1-4: fans (class 7)
    Entity indices 5-6: power supplies (class 6)
    Entity indices 7-10: modules (class 9)
    """
    return [
        (f"{ENT_PHYSICAL_CLASS}.1", "7"),  # fan
        (f"{ENT_PHYSICAL_CLASS}.2", "7"),
        (f"{ENT_PHYSICAL_CLASS}.3", "7"),
        (f"{ENT_PHYSICAL_CLASS}.4", "7"),
        (f"{ENT_PHYSICAL_CLASS}.5", "6"),  # power supply
        (f"{ENT_PHYSICAL_CLASS}.6", "6"),
        (f"{ENT_PHYSICAL_CLASS}.7", "9"),  # module
        (f"{ENT_PHYSICAL_CLASS}.8", "9"),
    ]


def _mock_hpe_entity_name() -> list[tuple[str, str]]:
    return [
        (f"{ENT_PHYSICAL_NAME}.1", "Fan 1"),
        (f"{ENT_PHYSICAL_NAME}.2", "Fan 2"),
        (f"{ENT_PHYSICAL_NAME}.3", "Fan 3"),
        (f"{ENT_PHYSICAL_NAME}.4", "Fan 4"),
        (f"{ENT_PHYSICAL_NAME}.5", "PSU 1"),
        (f"{ENT_PHYSICAL_NAME}.6", "PSU 2"),
        (f"{ENT_PHYSICAL_NAME}.7", "Slot 1"),
        (f"{ENT_PHYSICAL_NAME}.8", "Slot 2"),
    ]


def _mock_hpe_entity_error_status(fails: bool) -> list[tuple[str, str]]:
    """HH3C-ENTITY-EXT error status.

    2=normal, 41=fanError, 51=psuError
    """
    fan_status = "2"    # normal
    fan3_status = "41" if fails else "2"  # fan 3 fails
    psu_status = "2"

    return [
        (f"{HH3C_ENTITY_EXT_ERROR_STATUS}.1", fan_status),
        (f"{HH3C_ENTITY_EXT_ERROR_STATUS}.2", fan_status),
        (f"{HH3C_ENTITY_EXT_ERROR_STATUS}.3", fan3_status),
        (f"{HH3C_ENTITY_EXT_ERROR_STATUS}.4", fan_status),
        (f"{HH3C_ENTITY_EXT_ERROR_STATUS}.5", psu_status),
        (f"{HH3C_ENTITY_EXT_ERROR_STATUS}.6", psu_status),
        (f"{HH3C_ENTITY_EXT_ERROR_STATUS}.7", "2"),
        (f"{HH3C_ENTITY_EXT_ERROR_STATUS}.8", "2"),
    ]


def _mock_hpe_transceiver_temp(
    interfaces: list[tuple[str, int, int]],
    rng: _random.Random,
) -> list[tuple[str, str]]:
    """HH3C transceiver temperature (1°C units). Only SFP+ ports."""
    # Only the uplink interface has a transceiver
    uplink = interfaces[-2]  # XGE1/0/1
    temp = 35 + rng.randint(0, 15)
    return [(f"{HH3C_TRANSCEIVER_TEMPERATURE}.{uplink[1]}", str(temp))]


def _mock_hpe_transceiver_voltage(
    interfaces: list[tuple[str, int, int]],
    rng: _random.Random,
) -> list[tuple[str, str]]:
    """HH3C transceiver voltage (hundredths of V, i.e. 330 = 3.30V)."""
    uplink = interfaces[-2]
    voltage_hundredths = 320 + rng.randint(0, 20)  # 3.20-3.40V
    return [(f"{HH3C_TRANSCEIVER_VOLTAGE}.{uplink[1]}", str(voltage_hundredths))]


def _mock_hpe_transceiver_tx(
    interfaces: list[tuple[str, int, int]],
    rng: _random.Random,
) -> list[tuple[str, str]]:
    """HH3C transceiver TX power (0.01 dBm units)."""
    uplink = interfaces[-2]
    tx = -300 + rng.randint(-100, 100)  # -3.0 ± 1.0 dBm
    return [(f"{HH3C_TRANSCEIVER_TX_POWER}.{uplink[1]}", str(tx))]


def _mock_hpe_transceiver_rx(
    interfaces: list[tuple[str, int, int]],
    rng: _random.Random,
) -> list[tuple[str, str]]:
    """HH3C transceiver RX power (0.01 dBm units)."""
    uplink = interfaces[-2]
    rx = -800 + rng.randint(-200, 200)  # -8.0 ± 2.0 dBm
    return [(f"{HH3C_TRANSCEIVER_RX_POWER}.{uplink[1]}", str(rx))]


# ── Cisco fan/power mock ─────────────────────────────────────────

def _mock_cisco_fan_state(fails: bool) -> list[tuple[str, str]]:
    """CISCO-ENVMON fan state. 1=normal, 3=critical, 5=notPresent."""
    fan3 = "5" if fails else "1"
    return [
        (f"{CISCO_ENV_FAN_STATE}.1", "1"),
        (f"{CISCO_ENV_FAN_STATE}.2", "1"),
        (f"{CISCO_ENV_FAN_STATE}.3", fan3),
        (f"{CISCO_ENV_FAN_STATE}.4", "1"),
    ]


def _mock_cisco_fan_descr() -> list[tuple[str, str]]:
    return [
        (f"{CISCO_ENV_FAN_DESCR}.1", "Fan1(Sys_Fan1)"),
        (f"{CISCO_ENV_FAN_DESCR}.2", "Fan2(Sys_Fan2)"),
        (f"{CISCO_ENV_FAN_DESCR}.3", "Fan3(Sys_Fan3)"),
        (f"{CISCO_ENV_FAN_DESCR}.4", "Fan4(Sys_Fan4)"),
    ]


def _mock_cisco_supply_state(fails: bool) -> list[tuple[str, str]]:
    """CISCO-ENVMON supply state."""
    return [
        (f"{CISCO_ENV_SUPPLY_STATE}.1", "1"),
        (f"{CISCO_ENV_SUPPLY_STATE}.2", "1"),
    ]


def _mock_cisco_supply_descr() -> list[tuple[str, str]]:
    return [
        (f"{CISCO_ENV_SUPPLY_DESCR}.1", "Power Supply 1"),
        (f"{CISCO_ENV_SUPPLY_DESCR}.2", "Power Supply 2"),
    ]


# ── Cisco CDP mock ────────────────────────────────────────────────

def _mock_cdp_device_id(
    interfaces: list[tuple[str, int, int]],
    neighbors: list[tuple[str, str, str]],
) -> list[tuple[str, str]]:
    """CISCO-CDP-MIB device ID. Index: ifIndex.deviceIndex"""
    uplink_idx = interfaces[-2][1]
    results = []
    for i, (_, neighbor_host, _) in enumerate(neighbors):
        oid = f"{CISCO_CDP_CACHE_DEVICE_ID}.{uplink_idx}.{i + 1}"
        results.append((oid, neighbor_host))
    return results


def _mock_cdp_device_port(
    interfaces: list[tuple[str, int, int]],
    neighbors: list[tuple[str, str, str]],
) -> list[tuple[str, str]]:
    uplink_idx = interfaces[-2][1]
    results = []
    for i, (_, _, remote_intf) in enumerate(neighbors):
        oid = f"{CISCO_CDP_CACHE_DEVICE_PORT}.{uplink_idx}.{i + 1}"
        results.append((oid, remote_intf))
    return results


# ── Cisco entity sensor mock (transceiver) ────────────────────────

def _mock_cisco_sensor(
    oid_prefix: str,
    interfaces: list[tuple[str, int, int]],
    rng: _random.Random,
) -> list[tuple[str, str]]:
    """Mock CISCO-ENTITY-SENSOR-MIB for transceiver DOM.

    For simplicity, we create 4 sensors per transceiver port:
    entity 1001=temp, 1002=voltage, 1003=tx_power, 1004=rx_power
    """
    from app.snmp.oid_maps import (
        CISCO_ENT_SENSOR_PRECISION,
        CISCO_ENT_SENSOR_SCALE,
        CISCO_ENT_SENSOR_TYPE,
        CISCO_ENT_SENSOR_VALUE,
    )

    uplink = interfaces[-2]  # Te1/1/1 or Eth1/49
    # Sensor entity indices: 1001=temp, 1002=voltage, 1003=tx, 1004=rx
    sensors = {
        1001: {"type": 8, "scale": 9, "precision": 1,
               "value": 350 + rng.randint(0, 150)},      # 35.0-50.0°C
        1002: {"type": 4, "scale": 9, "precision": 3,
               "value": 3300 + rng.randint(0, 200)},      # 3.300-3.500V
        1003: {"type": 14, "scale": 9, "precision": 1,
               "value": -30 + rng.randint(-10, 10)},      # -3.0±1.0 dBm
        1004: {"type": 14, "scale": 9, "precision": 1,
               "value": -80 + rng.randint(-20, 20)},      # -8.0±2.0 dBm
    }

    results: list[tuple[str, str]] = []
    for entity_idx, s in sensors.items():
        if oid_prefix == CISCO_ENT_SENSOR_VALUE:
            results.append((f"{oid_prefix}.{entity_idx}", str(s["value"])))
        elif oid_prefix == CISCO_ENT_SENSOR_TYPE:
            results.append((f"{oid_prefix}.{entity_idx}", str(s["type"])))
        elif oid_prefix == CISCO_ENT_SENSOR_SCALE:
            results.append((f"{oid_prefix}.{entity_idx}", str(s["scale"])))
        elif oid_prefix == CISCO_ENT_SENSOR_PRECISION:
            results.append((f"{oid_prefix}.{entity_idx}", str(s["precision"])))

    return results


def _mock_cisco_contained_in(
    interfaces: list[tuple[str, int, int]],
) -> list[tuple[str, str]]:
    """entPhysicalContainedIn: sensor → parent (transceiver module)."""
    # All sensors (1001-1004) contained in parent entity 1000
    prefix = "1.3.6.1.2.1.47.1.1.1.1.4"
    return [
        (f"{prefix}.1001", "1000"),
        (f"{prefix}.1002", "1000"),
        (f"{prefix}.1003", "1000"),
        (f"{prefix}.1004", "1000"),
        (f"{prefix}.1000", "0"),  # root
    ]


def _mock_cisco_entity_name(
    interfaces: list[tuple[str, int, int]],
) -> list[tuple[str, str]]:
    """entPhysicalName for Cisco entities."""
    uplink = interfaces[-2]
    results = [
        (f"{ENT_PHYSICAL_NAME}.1000", uplink[0]),
        (f"{ENT_PHYSICAL_NAME}.1001", f"{uplink[0]} Temperature Sensor"),
        (f"{ENT_PHYSICAL_NAME}.1002", f"{uplink[0]} Voltage Sensor"),
        (f"{ENT_PHYSICAL_NAME}.1003", f"{uplink[0]} Tx Power Sensor"),
        (f"{ENT_PHYSICAL_NAME}.1004", f"{uplink[0]} Rx Power Sensor"),
    ]
    return results
