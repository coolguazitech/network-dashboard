"""
Unit tests for all 10 SNMP collectors.

Each collector extends BaseSnmpCollector and implements:
    async def collect(self, target, device_type, session_cache, engine)
        -> tuple[str, list[ParsedData]]

Tests mock the engine (walk/get) and session_cache, then verify the
collector returns correct raw_text and parsed_items.
"""
from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock

import pytest

# Stub out pysnmp before importing app.snmp.engine, because the real
# pysnmp-lextudio v3arch module is not installed in the test environment.
_pysnmp_stub = ModuleType("pysnmp")
_hlapi_stub = ModuleType("pysnmp.hlapi")
_v3arch_stub = ModuleType("pysnmp.hlapi.v3arch")
_asyncio_stub = ModuleType("pysnmp.hlapi.v3arch.asyncio")

for _attr in (
    "CommunityData",
    "ContextData",
    "ObjectIdentity",
    "ObjectType",
    "UdpTransportTarget",
    "bulk_cmd",
    "get_cmd",
):
    setattr(_asyncio_stub, _attr, MagicMock())
_asyncio_stub.SnmpEngine = MagicMock()  # aliased as PySnmpEngine

for _mod_name, _mod in (
    ("pysnmp", _pysnmp_stub),
    ("pysnmp.hlapi", _hlapi_stub),
    ("pysnmp.hlapi.v3arch", _v3arch_stub),
    ("pysnmp.hlapi.v3arch.asyncio", _asyncio_stub),
):
    sys.modules.setdefault(_mod_name, _mod)

from app.core.enums import DeviceType  # noqa: E402
from app.snmp.engine import SnmpTarget  # noqa: E402

# Collectors
from app.snmp.collectors.error_count import ErrorCountCollector  # noqa: E402
from app.snmp.collectors.neighbor_lldp import NeighborLldpCollector  # noqa: E402
from app.snmp.collectors.interface_status import InterfaceStatusCollector  # noqa: E402
from app.snmp.collectors.mac_table import MacTableCollector  # noqa: E402
from app.snmp.collectors.channel_group import ChannelGroupCollector  # noqa: E402
from app.snmp.collectors.version import VersionCollector  # noqa: E402
from app.snmp.collectors.fan import FanCollector  # noqa: E402
from app.snmp.collectors.power import PowerCollector  # noqa: E402
from app.snmp.collectors.transceiver import TransceiverCollector  # noqa: E402
from app.snmp.collectors.neighbor_cdp import NeighborCdpCollector  # noqa: E402

# ParsedData types
from app.parsers.protocols import (  # noqa: E402
    InterfaceErrorData,
    NeighborData,
    InterfaceStatusData,
    MacTableData,
    PortChannelData,
    VersionData,
    FanStatusData,
    PowerData,
    TransceiverData,
    TransceiverChannelData,
)

# OID constants
from app.snmp.oid_maps import (  # noqa: E402
    IF_IN_ERRORS,
    IF_OUT_ERRORS,
    IF_OPER_STATUS,
    IF_HIGH_SPEED,
    DOT3_STATS_DUPLEX,
    DOT1Q_TP_FDB_PORT,
    DOT3AD_AGG_PORT_ATTACHED_AGG_ID,
    DOT3AD_AGG_PORT_ACTOR_OPER_STATE,
    SYS_DESCR,
    HH3C_ENTITY_EXT_ERROR_STATUS,
    ENT_PHYSICAL_CLASS,
    ENT_PHYSICAL_NAME,
    CISCO_ENV_FAN_STATE,
    CISCO_ENV_FAN_DESCR,
    CISCO_ENV_SUPPLY_STATE,
    CISCO_ENV_SUPPLY_DESCR,
    HH3C_TRANSCEIVER_TEMPERATURE,
    HH3C_TRANSCEIVER_VOLTAGE,
    HH3C_TRANSCEIVER_TX_POWER,
    HH3C_TRANSCEIVER_RX_POWER,
    CISCO_CDP_CACHE_DEVICE_ID,
    CISCO_CDP_CACHE_DEVICE_PORT,
    LLDP_REM_SYS_NAME,
    LLDP_REM_PORT_ID,
    LLDP_REM_PORT_DESC,
    LLDP_LOC_PORT_DESC,
)


# =====================================================================
# Shared fixtures
# =====================================================================


@pytest.fixture
def target():
    return SnmpTarget(ip="10.0.0.1", community="public", port=161, timeout=5.0, retries=2)


@pytest.fixture
def engine():
    return AsyncMock()


@pytest.fixture
def session_cache():
    mock = AsyncMock()
    mock.get_ifindex_map = AsyncMock(return_value={
        1: "GigabitEthernet0/1",
        2: "GigabitEthernet0/2",
        49: "GigabitEthernet1/0/1",
        50: "GigabitEthernet1/0/2",
        100: "Vlan100",
        200: "Loopback0",
        500: "Port-channel1",
    })
    mock.get_bridge_port_map = AsyncMock(return_value={
        1: 49,
        2: 50,
    })
    return mock


# =====================================================================
# 1. ErrorCountCollector
# =====================================================================


class TestErrorCountCollector:
    """Tests for ErrorCountCollector (api_name='get_error_count')."""

    @pytest.mark.asyncio
    async def test_error_count_filters_zero_errors(self, target, engine, session_cache):
        """Walk returns errors for 3 interfaces, but 2 have 0 errors. Only 1 result returned."""
        engine.walk = AsyncMock(side_effect=lambda t, oid: {
            IF_IN_ERRORS: [
                (f"{IF_IN_ERRORS}.1", "5"),
                (f"{IF_IN_ERRORS}.2", "0"),
                (f"{IF_IN_ERRORS}.49", "0"),
            ],
            IF_OUT_ERRORS: [
                (f"{IF_OUT_ERRORS}.1", "3"),
                (f"{IF_OUT_ERRORS}.2", "0"),
                (f"{IF_OUT_ERRORS}.49", "0"),
            ],
        }[oid])

        collector = ErrorCountCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text  # non-empty string
        assert len(parsed_items) == 1
        assert isinstance(parsed_items[0], InterfaceErrorData)
        assert parsed_items[0].interface_name == "GigabitEthernet0/1"
        assert parsed_items[0].crc_errors == 8

    @pytest.mark.asyncio
    async def test_error_count_combines_in_out(self, target, engine, session_cache):
        """ifInErrors=5 and ifOutErrors=3 for ifIndex 1. Result has crc_errors=8."""
        engine.walk = AsyncMock(side_effect=lambda t, oid: {
            IF_IN_ERRORS: [
                (f"{IF_IN_ERRORS}.1", "5"),
            ],
            IF_OUT_ERRORS: [
                (f"{IF_OUT_ERRORS}.1", "3"),
            ],
        }[oid])

        collector = ErrorCountCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 1
        assert parsed_items[0].interface_name == "GigabitEthernet0/1"
        assert parsed_items[0].crc_errors == 8

    @pytest.mark.asyncio
    async def test_error_count_skips_no_ifname(self, target, engine, session_cache):
        """ifIndex 999 has errors but no ifName mapping. Should be skipped."""
        engine.walk = AsyncMock(side_effect=lambda t, oid: {
            IF_IN_ERRORS: [
                (f"{IF_IN_ERRORS}.999", "10"),
            ],
            IF_OUT_ERRORS: [
                (f"{IF_OUT_ERRORS}.999", "5"),
            ],
        }[oid])

        collector = ErrorCountCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 0


# =====================================================================
# 2. NeighborLldpCollector
# =====================================================================


class TestNeighborLldpCollector:
    """Tests for NeighborLldpCollector (api_name='get_uplink_lldp')."""

    @pytest.mark.asyncio
    async def test_lldp_basic_neighbor(self, target, engine, session_cache):
        """Remote entries for one neighbor. Verify local_interface, remote_hostname, remote_interface."""
        # LLDP remote index: {timemark}.{local_port_num}.{rem_index}
        # Use timemark=0, local_port_num=49, rem_index=1
        engine.walk = AsyncMock(side_effect=lambda t, oid: {
            LLDP_REM_SYS_NAME: [
                (f"{LLDP_REM_SYS_NAME}.0.49.1", "switch-remote.example.com"),
            ],
            LLDP_REM_PORT_ID: [
                (f"{LLDP_REM_PORT_ID}.0.49.1", "Gi0/1"),
            ],
            LLDP_REM_PORT_DESC: [
                (f"{LLDP_REM_PORT_DESC}.0.49.1", "GigabitEthernet0/1"),
            ],
            LLDP_LOC_PORT_DESC: [
                (f"{LLDP_LOC_PORT_DESC}.49", "GigabitEthernet1/0/1"),
            ],
        }[oid])

        collector = NeighborLldpCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 1
        assert isinstance(parsed_items[0], NeighborData)
        assert parsed_items[0].local_interface == "GigabitEthernet1/0/1"
        assert parsed_items[0].remote_hostname == "switch-remote.example.com"
        assert parsed_items[0].remote_interface == "GigabitEthernet0/1"

    @pytest.mark.asyncio
    async def test_lldp_prefers_port_desc(self, target, engine, session_cache):
        """Both lldpRemPortDesc and lldpRemPortId present. Should use port_desc."""
        engine.walk = AsyncMock(side_effect=lambda t, oid: {
            LLDP_REM_SYS_NAME: [
                (f"{LLDP_REM_SYS_NAME}.0.49.1", "remote-switch"),
            ],
            LLDP_REM_PORT_ID: [
                (f"{LLDP_REM_PORT_ID}.0.49.1", "Gi0/1"),
            ],
            LLDP_REM_PORT_DESC: [
                (f"{LLDP_REM_PORT_DESC}.0.49.1", "GigabitEthernet0/1 Description"),
            ],
            LLDP_LOC_PORT_DESC: [
                (f"{LLDP_LOC_PORT_DESC}.49", "GigabitEthernet1/0/1"),
            ],
        }[oid])

        collector = NeighborLldpCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 1
        assert parsed_items[0].remote_interface == "GigabitEthernet0/1 Description"

    @pytest.mark.asyncio
    async def test_lldp_fallback_to_port_id(self, target, engine, session_cache):
        """Only lldpRemPortId present (no port_desc). Should use port_id."""
        engine.walk = AsyncMock(side_effect=lambda t, oid: {
            LLDP_REM_SYS_NAME: [
                (f"{LLDP_REM_SYS_NAME}.0.49.1", "remote-switch"),
            ],
            LLDP_REM_PORT_ID: [
                (f"{LLDP_REM_PORT_ID}.0.49.1", "Gi0/1"),
            ],
            LLDP_REM_PORT_DESC: [],  # no port_desc entries
            LLDP_LOC_PORT_DESC: [
                (f"{LLDP_LOC_PORT_DESC}.49", "GigabitEthernet1/0/1"),
            ],
        }[oid])

        collector = NeighborLldpCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 1
        assert parsed_items[0].remote_interface == "Gi0/1"


# =====================================================================
# 3. InterfaceStatusCollector
# =====================================================================


class TestInterfaceStatusCollector:
    """Tests for InterfaceStatusCollector (api_name='get_interface_status')."""

    @pytest.mark.asyncio
    async def test_interface_status_basic(self, target, engine, session_cache):
        """Two physical interfaces with different status/speed/duplex. Verify results."""
        engine.walk = AsyncMock(side_effect=lambda t, oid: {
            IF_OPER_STATUS: [
                (f"{IF_OPER_STATUS}.1", "1"),   # up
                (f"{IF_OPER_STATUS}.2", "2"),   # down
            ],
            IF_HIGH_SPEED: [
                (f"{IF_HIGH_SPEED}.1", "1000"),  # 1G
                (f"{IF_HIGH_SPEED}.2", "100"),   # 100M
            ],
            DOT3_STATS_DUPLEX: [
                (f"{DOT3_STATS_DUPLEX}.1", "3"),  # full
                (f"{DOT3_STATS_DUPLEX}.2", "2"),  # half
            ],
        }[oid])

        collector = InterfaceStatusCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 2

        item0 = parsed_items[0]
        assert isinstance(item0, InterfaceStatusData)
        assert item0.interface_name == "GigabitEthernet0/1"
        assert item0.link_status == "up"  # normalized LinkStatus
        assert item0.speed == "1G"
        assert item0.duplex == "full"  # normalized DuplexMode

        item1 = parsed_items[1]
        assert item1.interface_name == "GigabitEthernet0/2"
        assert item1.link_status == "down"
        assert item1.speed == "100M"
        assert item1.duplex == "half"

    @pytest.mark.asyncio
    async def test_interface_status_skips_vlan_loopback(self, target, engine, session_cache):
        """Interfaces named 'Vlan100' and 'Loopback0' should be skipped."""
        engine.walk = AsyncMock(side_effect=lambda t, oid: {
            IF_OPER_STATUS: [
                (f"{IF_OPER_STATUS}.1", "1"),     # GigabitEthernet0/1 - physical
                (f"{IF_OPER_STATUS}.100", "1"),   # Vlan100 - skip
                (f"{IF_OPER_STATUS}.200", "1"),   # Loopback0 - skip
            ],
            IF_HIGH_SPEED: [
                (f"{IF_HIGH_SPEED}.1", "1000"),
                (f"{IF_HIGH_SPEED}.100", "0"),
                (f"{IF_HIGH_SPEED}.200", "0"),
            ],
            DOT3_STATS_DUPLEX: [],
        }[oid])

        collector = InterfaceStatusCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 1
        assert parsed_items[0].interface_name == "GigabitEthernet0/1"

    @pytest.mark.asyncio
    async def test_interface_status_speed_formatting(self, target, engine, session_cache):
        """ifHighSpeed=1000 -> '1G', 100 -> '100M', 10000 -> '10G', 0 -> 'unknown'."""
        # Use 4 different ifIndexes: 1, 2, 49, 50
        engine.walk = AsyncMock(side_effect=lambda t, oid: {
            IF_OPER_STATUS: [
                (f"{IF_OPER_STATUS}.1", "1"),
                (f"{IF_OPER_STATUS}.2", "1"),
                (f"{IF_OPER_STATUS}.49", "1"),
                (f"{IF_OPER_STATUS}.50", "1"),
            ],
            IF_HIGH_SPEED: [
                (f"{IF_HIGH_SPEED}.1", "1000"),
                (f"{IF_HIGH_SPEED}.2", "100"),
                (f"{IF_HIGH_SPEED}.49", "10000"),
                (f"{IF_HIGH_SPEED}.50", "0"),
            ],
            DOT3_STATS_DUPLEX: [],
        }[oid])

        collector = InterfaceStatusCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 4

        speed_by_iface = {item.interface_name: item.speed for item in parsed_items}
        assert speed_by_iface["GigabitEthernet0/1"] == "1G"
        assert speed_by_iface["GigabitEthernet0/2"] == "100M"
        assert speed_by_iface["GigabitEthernet1/0/1"] == "10G"
        assert speed_by_iface["GigabitEthernet1/0/2"] == "unknown"


# =====================================================================
# 4. MacTableCollector
# =====================================================================


class TestMacTableCollector:
    """Tests for MacTableCollector (api_name='get_mac_table')."""

    @pytest.mark.asyncio
    async def test_mac_table_basic(self, target, engine, session_cache):
        """
        One MAC entry: vlan=100, MAC octets 0.1.2.3.4.5, bridge_port=1
        -> ifIndex 49 -> 'GigabitEthernet1/0/1'.
        Result: MacTableData(mac_address='00:01:02:03:04:05', interface_name='GigabitEthernet1/0/1', vlan_id=100).
        """
        # Index format: {vlan_id}.{o1}.{o2}.{o3}.{o4}.{o5}.{o6}
        oid_index = "100.0.1.2.3.4.5"
        engine.walk = AsyncMock(return_value=[
            (f"{DOT1Q_TP_FDB_PORT}.{oid_index}", "1"),  # bridge_port=1
        ])

        collector = MacTableCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 1
        item = parsed_items[0]
        assert isinstance(item, MacTableData)
        assert item.mac_address == "00:01:02:03:04:05"
        assert item.interface_name == "GigabitEthernet1/0/1"
        assert item.vlan_id == 100

    @pytest.mark.asyncio
    async def test_mac_table_skips_unknown_bridge_port(self, target, engine, session_cache):
        """bridge_port not in bridge_port_map -> skip."""
        oid_index = "100.0.1.2.3.4.5"
        engine.walk = AsyncMock(return_value=[
            (f"{DOT1Q_TP_FDB_PORT}.{oid_index}", "99"),  # bridge_port=99, not in map
        ])

        collector = MacTableCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 0

    @pytest.mark.asyncio
    async def test_mac_table_multiple_entries(self, target, engine, session_cache):
        """Two MACs on different VLANs/ports."""
        engine.walk = AsyncMock(return_value=[
            (f"{DOT1Q_TP_FDB_PORT}.100.0.1.2.3.4.5", "1"),   # bridge_port=1 -> ifIndex 49
            (f"{DOT1Q_TP_FDB_PORT}.200.10.20.30.40.50.60", "2"),  # bridge_port=2 -> ifIndex 50
        ])

        collector = MacTableCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 2

        item0 = parsed_items[0]
        assert item0.mac_address == "00:01:02:03:04:05"
        assert item0.interface_name == "GigabitEthernet1/0/1"
        assert item0.vlan_id == 100

        item1 = parsed_items[1]
        assert item1.mac_address == "0A:14:1E:28:32:3C"
        assert item1.interface_name == "GigabitEthernet1/0/2"
        assert item1.vlan_id == 200


# =====================================================================
# 5. ChannelGroupCollector
# =====================================================================


class TestChannelGroupCollector:
    """Tests for ChannelGroupCollector (api_name='get_channel_group')."""

    @pytest.mark.asyncio
    async def test_channel_group_basic(self, target, engine, session_cache):
        """
        Two members (ifIndex 49, 50) attached to aggregate (ifIndex 500).
        Both synced (bit 2 set, value=0x3D). Aggregate ifOperStatus=1 (up).
        Result: PortChannelData with members, status='up'.
        """
        def walk_side_effect(t, oid):
            if oid == DOT3AD_AGG_PORT_ATTACHED_AGG_ID:
                return [
                    (f"{DOT3AD_AGG_PORT_ATTACHED_AGG_ID}.49", "500"),
                    (f"{DOT3AD_AGG_PORT_ATTACHED_AGG_ID}.50", "500"),
                ]
            elif oid == DOT3AD_AGG_PORT_ACTOR_OPER_STATE:
                # 0x3D = 61 decimal, bit 2 (0x04) is set -> synced
                return [
                    (f"{DOT3AD_AGG_PORT_ACTOR_OPER_STATE}.49", "61"),
                    (f"{DOT3AD_AGG_PORT_ACTOR_OPER_STATE}.50", "61"),
                ]
            elif oid == IF_OPER_STATUS:
                return [
                    (f"{IF_OPER_STATUS}.500", "1"),  # aggregate is up
                ]
            return []

        engine.walk = AsyncMock(side_effect=walk_side_effect)

        collector = ChannelGroupCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 1
        item = parsed_items[0]
        assert isinstance(item, PortChannelData)
        assert item.interface_name == "Port-channel1"
        assert item.status == "up"  # normalized LinkStatus
        assert "GigabitEthernet1/0/1" in item.members
        assert "GigabitEthernet1/0/2" in item.members
        assert item.member_status["GigabitEthernet1/0/1"] == "up"
        assert item.member_status["GigabitEthernet1/0/2"] == "up"

    @pytest.mark.asyncio
    async def test_channel_group_member_down(self, target, engine, session_cache):
        """
        One member has sync bit unset (value=0x39). That member shows 'down'.
        0x39 = 57 decimal. Bit 2 (0x04) is NOT set -> not synced -> down.
        """
        def walk_side_effect(t, oid):
            if oid == DOT3AD_AGG_PORT_ATTACHED_AGG_ID:
                return [
                    (f"{DOT3AD_AGG_PORT_ATTACHED_AGG_ID}.49", "500"),
                    (f"{DOT3AD_AGG_PORT_ATTACHED_AGG_ID}.50", "500"),
                ]
            elif oid == DOT3AD_AGG_PORT_ACTOR_OPER_STATE:
                return [
                    (f"{DOT3AD_AGG_PORT_ACTOR_OPER_STATE}.49", "61"),  # 0x3D bit3=sync set
                    (f"{DOT3AD_AGG_PORT_ACTOR_OPER_STATE}.50", "55"),  # 0x37 bit3=sync unset
                ]
            elif oid == IF_OPER_STATUS:
                return [
                    (f"{IF_OPER_STATUS}.500", "1"),
                ]
            return []

        engine.walk = AsyncMock(side_effect=walk_side_effect)

        collector = ChannelGroupCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 1
        item = parsed_items[0]
        assert item.member_status["GigabitEthernet1/0/1"] == "up"
        assert item.member_status["GigabitEthernet1/0/2"] == "down"


# =====================================================================
# 6. VersionCollector
# =====================================================================


class TestVersionCollector:
    """Tests for VersionCollector (api_name='get_version')."""

    @pytest.mark.asyncio
    async def test_version_hpe(self, target, engine, session_cache):
        """
        sysDescr = 'HPE Comware Platform Software, Version 7.1.070, Release 6728P06'.
        Should extract '7.1.070 6728P06'.
        """
        engine.get = AsyncMock(return_value={
            SYS_DESCR: "HPE Comware Platform Software, Version 7.1.070, Release 6728P06",
        })

        collector = VersionCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 1
        assert isinstance(parsed_items[0], VersionData)
        assert parsed_items[0].version == "7.1.070 6728P06"

    @pytest.mark.asyncio
    async def test_version_cisco_ios(self, target, engine, session_cache):
        """
        sysDescr = 'Cisco IOS Software, Version 15.2(7)E2'.
        Should extract '15.2(7)E2'.
        """
        engine.get = AsyncMock(return_value={
            SYS_DESCR: "Cisco IOS Software, Version 15.2(7)E2",
        })

        collector = VersionCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.CISCO_IOS, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 1
        assert parsed_items[0].version == "15.2(7)E2"

    @pytest.mark.asyncio
    async def test_version_fallback(self, target, engine, session_cache):
        """
        sysDescr = 'Unknown Device'. Should return 'Unknown Device' as fallback.
        """
        engine.get = AsyncMock(return_value={
            SYS_DESCR: "Unknown Device",
        })

        collector = VersionCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 1
        assert parsed_items[0].version == "Unknown Device"


# =====================================================================
# 7. FanCollector
# =====================================================================


class TestFanCollector:
    """Tests for FanCollector (api_name='get_fan')."""

    @pytest.mark.asyncio
    async def test_fan_hpe_normal(self, target, engine, session_cache):
        """
        HPE device. Entity with class=7 (fan), error_status=2 (normal).
        Result: FanStatusData(fan_id='Fan 1', status='normal').
        """
        def walk_side_effect(t, oid):
            if oid == HH3C_ENTITY_EXT_ERROR_STATUS:
                return [
                    (f"{HH3C_ENTITY_EXT_ERROR_STATUS}.10", "2"),  # normal
                ]
            elif oid == ENT_PHYSICAL_CLASS:
                return [
                    (f"{ENT_PHYSICAL_CLASS}.10", "7"),  # fan
                ]
            elif oid == ENT_PHYSICAL_NAME:
                return [
                    (f"{ENT_PHYSICAL_NAME}.10", "Fan 1"),
                ]
            return []

        engine.walk = AsyncMock(side_effect=walk_side_effect)

        collector = FanCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 1
        assert isinstance(parsed_items[0], FanStatusData)
        assert parsed_items[0].fan_id == "Fan 1"
        assert parsed_items[0].status == "normal"  # normalized OperationalStatus

    @pytest.mark.asyncio
    async def test_fan_cisco_normal(self, target, engine, session_cache):
        """
        Cisco device. Fan state=1 (normal).
        Result: FanStatusData with status containing 'normal'.
        """
        engine.walk = AsyncMock(side_effect=lambda t, oid: {
            CISCO_ENV_FAN_STATE: [
                (f"{CISCO_ENV_FAN_STATE}.1", "1"),  # normal
            ],
            CISCO_ENV_FAN_DESCR: [
                (f"{CISCO_ENV_FAN_DESCR}.1", "Chassis Fan 1"),
            ],
        }[oid])

        collector = FanCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.CISCO_IOS, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 1
        assert parsed_items[0].fan_id == "Chassis Fan 1"
        assert parsed_items[0].status == "normal"  # normalized OperationalStatus

    @pytest.mark.asyncio
    async def test_fan_hpe_failed(self, target, engine, session_cache):
        """
        HPE device. error_status=41 (fanError). Status should be 'fail'.
        """
        def walk_side_effect(t, oid):
            if oid == HH3C_ENTITY_EXT_ERROR_STATUS:
                return [
                    (f"{HH3C_ENTITY_EXT_ERROR_STATUS}.10", "41"),  # fanError
                ]
            elif oid == ENT_PHYSICAL_CLASS:
                return [
                    (f"{ENT_PHYSICAL_CLASS}.10", "7"),  # fan
                ]
            elif oid == ENT_PHYSICAL_NAME:
                return [
                    (f"{ENT_PHYSICAL_NAME}.10", "Fan 1"),
                ]
            return []

        engine.walk = AsyncMock(side_effect=walk_side_effect)

        collector = FanCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 1
        assert parsed_items[0].status == "fail"  # normalized OperationalStatus


# =====================================================================
# 8. PowerCollector
# =====================================================================


class TestPowerCollector:
    """Tests for PowerCollector (api_name='get_power')."""

    @pytest.mark.asyncio
    async def test_power_hpe_normal(self, target, engine, session_cache):
        """
        HPE device. Entity with class=6 (power supply), error_status=2 (normal).
        """
        def walk_side_effect(t, oid):
            if oid == HH3C_ENTITY_EXT_ERROR_STATUS:
                return [
                    (f"{HH3C_ENTITY_EXT_ERROR_STATUS}.20", "2"),  # normal
                ]
            elif oid == ENT_PHYSICAL_CLASS:
                return [
                    (f"{ENT_PHYSICAL_CLASS}.20", "6"),  # powerSupply
                ]
            elif oid == ENT_PHYSICAL_NAME:
                return [
                    (f"{ENT_PHYSICAL_NAME}.20", "PSU 1"),
                ]
            return []

        engine.walk = AsyncMock(side_effect=walk_side_effect)

        collector = PowerCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 1
        assert isinstance(parsed_items[0], PowerData)
        assert parsed_items[0].ps_id == "PSU 1"
        assert parsed_items[0].status == "normal"  # normalized OperationalStatus

    @pytest.mark.asyncio
    async def test_power_cisco_normal(self, target, engine, session_cache):
        """
        Cisco device. Supply state=1 (normal). Status='normal'.
        """
        engine.walk = AsyncMock(side_effect=lambda t, oid: {
            CISCO_ENV_SUPPLY_STATE: [
                (f"{CISCO_ENV_SUPPLY_STATE}.1", "1"),  # normal
            ],
            CISCO_ENV_SUPPLY_DESCR: [
                (f"{CISCO_ENV_SUPPLY_DESCR}.1", "Power Supply 1"),
            ],
        }[oid])

        collector = PowerCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.CISCO_IOS, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 1
        assert parsed_items[0].ps_id == "Power Supply 1"
        assert parsed_items[0].status == "normal"  # normalized OperationalStatus


# =====================================================================
# 9. TransceiverCollector
# =====================================================================


class TestTransceiverCollector:
    """Tests for TransceiverCollector (api_name='get_gbic_details')."""

    @pytest.mark.asyncio
    async def test_transceiver_hpe(self, target, engine, session_cache):
        """
        HPE device with temp=45 (C), voltage=330 (0.01V -> 3.3V),
        tx=-500 (0.01dBm -> -5.0dBm), rx=-800 (0.01dBm -> -8.0dBm)
        for ifIndex 49.
        """
        engine.walk = AsyncMock(side_effect=lambda t, oid: {
            HH3C_TRANSCEIVER_TEMPERATURE: [
                (f"{HH3C_TRANSCEIVER_TEMPERATURE}.49", "45"),
            ],
            HH3C_TRANSCEIVER_VOLTAGE: [
                (f"{HH3C_TRANSCEIVER_VOLTAGE}.49", "330"),
            ],
            HH3C_TRANSCEIVER_TX_POWER: [
                (f"{HH3C_TRANSCEIVER_TX_POWER}.49", "-500"),
            ],
            HH3C_TRANSCEIVER_RX_POWER: [
                (f"{HH3C_TRANSCEIVER_RX_POWER}.49", "-800"),
            ],
        }[oid])

        collector = TransceiverCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 1
        item = parsed_items[0]
        assert isinstance(item, TransceiverData)
        assert item.interface_name == "GigabitEthernet1/0/1"
        assert item.temperature == 45.0
        assert item.voltage == pytest.approx(3.3, abs=0.01)
        assert len(item.channels) == 1
        channel = item.channels[0]
        assert isinstance(channel, TransceiverChannelData)
        assert channel.channel == 1
        assert channel.tx_power == pytest.approx(-5.0, abs=0.01)
        assert channel.rx_power == pytest.approx(-8.0, abs=0.01)


# =====================================================================
# 10. NeighborCdpCollector
# =====================================================================


class TestNeighborCdpCollector:
    """Tests for NeighborCdpCollector (api_name='get_uplink_cdp')."""

    @pytest.mark.asyncio
    async def test_cdp_cisco_basic(self, target, engine, session_cache):
        """
        Cisco device. One CDP neighbor. Compound index '49.1'
        -> local ifIndex 49 -> 'GigabitEthernet1/0/1'.
        """
        engine.walk = AsyncMock(side_effect=lambda t, oid: {
            CISCO_CDP_CACHE_DEVICE_ID: [
                (f"{CISCO_CDP_CACHE_DEVICE_ID}.49.1", "remote-switch.example.com"),
            ],
            CISCO_CDP_CACHE_DEVICE_PORT: [
                (f"{CISCO_CDP_CACHE_DEVICE_PORT}.49.1", "GigabitEthernet0/1"),
            ],
        }[oid])

        collector = NeighborCdpCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.CISCO_IOS, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 1
        assert isinstance(parsed_items[0], NeighborData)
        assert parsed_items[0].local_interface == "GigabitEthernet1/0/1"
        assert parsed_items[0].remote_hostname == "remote-switch.example.com"
        assert parsed_items[0].remote_interface == "GigabitEthernet0/1"

    @pytest.mark.asyncio
    async def test_cdp_hpe_returns_empty(self, target, engine, session_cache):
        """HPE device. Should return empty list immediately without walking."""
        collector = NeighborCdpCollector()
        raw_text, parsed_items = await collector.collect(target, DeviceType.HPE, session_cache, engine)

        assert raw_text
        assert len(parsed_items) == 0
        # engine.walk should NOT have been called for HPE
        engine.walk.assert_not_called()
