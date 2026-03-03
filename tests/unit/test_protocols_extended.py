"""
Extended protocol and ParsedData model validation tests.

Tests Pydantic validators, field constraints, and normalization logic
in app.parsers.protocols for all ParsedData types.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.parsers.protocols import (
    AclData,
    FanStatusData,
    InterfaceErrorData,
    InterfaceStatusData,
    MacTableData,
    NeighborData,
    PingResultData,
    PortChannelData,
    PowerData,
    TransceiverChannelData,
    TransceiverData,
    VersionData,
    _normalize_mac,
    _normalize_operational_status,
    _normalize_link_status,
)


# ══════════════════════════════════════════════════════════════════
# MAC Normalization
# ══════════════════════════════════════════════════════════════════


class TestNormalizeMac:
    """Test _normalize_mac() helper."""

    @pytest.mark.parametrize("raw,expected", [
        ("AA:BB:CC:DD:EE:FF", "AA:BB:CC:DD:EE:FF"),
        ("aa:bb:cc:dd:ee:ff", "AA:BB:CC:DD:EE:FF"),
        ("AA-BB-CC-DD-EE-FF", "AA:BB:CC:DD:EE:FF"),
        ("AABB.CCDD.EEFF", "AA:BB:CC:DD:EE:FF"),
        ("aabb.ccdd.eeff", "AA:BB:CC:DD:EE:FF"),
        ("aabbccddeeff", "AA:BB:CC:DD:EE:FF"),
        ("AABBCCDDEEFF", "AA:BB:CC:DD:EE:FF"),
        ("aabb-ccdd-eeff", "AA:BB:CC:DD:EE:FF"),
    ])
    def test_valid_formats(self, raw, expected):
        assert _normalize_mac(raw) == expected

    @pytest.mark.parametrize("raw", [
        "GGGG.HHHH.IIII",  # Non-hex chars
        "AA:BB:CC",  # Too short
        "AA:BB:CC:DD:EE:FF:00",  # Too long
        "",  # Empty
        "not-a-mac",  # Random string
    ])
    def test_invalid_formats_returns_uppercased(self, raw):
        result = _normalize_mac(raw)
        assert result == raw.upper()


# ══════════════════════════════════════════════════════════════════
# Operational Status Normalization
# ══════════════════════════════════════════════════════════════════


class TestNormalizeOperationalStatus:

    @pytest.mark.parametrize("raw,expected", [
        ("ok", "ok"),
        ("OK", "ok"),
        ("Ok", "ok"),
        ("normal", "normal"),
        ("Normal", "normal"),
        ("good", "good"),
        ("fail", "fail"),
        ("FAIL", "fail"),
        ("absent", "absent"),
        ("unknown", "unknown"),
    ])
    def test_valid_statuses(self, raw, expected):
        assert _normalize_operational_status(raw) == expected

    def test_none_returns_unknown(self):
        assert _normalize_operational_status(None) == "unknown"

    @pytest.mark.parametrize("raw", [
        "broken", "error", "xyz", "123", "",
    ])
    def test_invalid_returns_unknown(self, raw):
        assert _normalize_operational_status(raw) == "unknown"

    def test_whitespace_stripped(self):
        assert _normalize_operational_status("  ok  ") == "ok"


# ══════════════════════════════════════════════════════════════════
# Link Status Normalization
# ══════════════════════════════════════════════════════════════════


class TestNormalizeLinkStatus:

    @pytest.mark.parametrize("raw,expected", [
        ("up", "up"),
        ("UP", "up"),
        ("Up", "up"),
        ("down", "down"),
        ("DOWN", "down"),
    ])
    def test_valid_statuses(self, raw, expected):
        assert _normalize_link_status(raw) == expected

    def test_none_returns_unknown(self):
        assert _normalize_link_status(None) == "unknown"

    def test_invalid_returns_unknown(self):
        assert _normalize_link_status("broken") == "unknown"


# ══════════════════════════════════════════════════════════════════
# MacTableData
# ══════════════════════════════════════════════════════════════════


class TestMacTableData:

    def test_valid(self):
        d = MacTableData(mac_address="AABB.CCDD.EEFF", interface_name="Gi1/0/1", vlan_id=100)
        assert d.mac_address == "AA:BB:CC:DD:EE:FF"
        assert d.vlan_id == 100

    def test_mac_normalization(self):
        d = MacTableData(mac_address="aa-bb-cc-dd-ee-ff", interface_name="Eth1/1", vlan_id=1)
        assert d.mac_address == "AA:BB:CC:DD:EE:FF"

    def test_vlan_zero(self):
        d = MacTableData(mac_address="AA:BB:CC:DD:EE:FF", interface_name="Gi1", vlan_id=0)
        assert d.vlan_id == 0

    def test_vlan_max(self):
        d = MacTableData(mac_address="AA:BB:CC:DD:EE:FF", interface_name="Gi1", vlan_id=4094)
        assert d.vlan_id == 4094

    def test_vlan_out_of_range(self):
        with pytest.raises(ValidationError):
            MacTableData(mac_address="AA:BB:CC:DD:EE:FF", interface_name="Gi1", vlan_id=4095)

    def test_vlan_negative(self):
        with pytest.raises(ValidationError):
            MacTableData(mac_address="AA:BB:CC:DD:EE:FF", interface_name="Gi1", vlan_id=-1)

    def test_default_vlan(self):
        d = MacTableData(mac_address="AA:BB:CC:DD:EE:FF", interface_name="Gi1")
        assert d.vlan_id == 0


# ══════════════════════════════════════════════════════════════════
# InterfaceStatusData
# ══════════════════════════════════════════════════════════════════


class TestInterfaceStatusData:

    def test_valid(self):
        d = InterfaceStatusData(
            interface_name="Gi1/0/1", link_status="up", speed="1G", duplex="full"
        )
        assert d.link_status == "up"
        assert d.duplex == "full"

    def test_link_status_normalization(self):
        d = InterfaceStatusData(interface_name="Gi1/0/1", link_status="UP")
        assert d.link_status == "up"

    def test_duplex_normalization(self):
        d = InterfaceStatusData(interface_name="Gi1", link_status="up", duplex="FULL")
        assert d.duplex == "full"

    def test_duplex_none(self):
        d = InterfaceStatusData(interface_name="Gi1", link_status="up", duplex=None)
        assert d.duplex is None

    def test_unknown_link_status(self):
        d = InterfaceStatusData(interface_name="Gi1", link_status="invalid")
        assert d.link_status == "unknown"

    def test_unknown_duplex(self):
        d = InterfaceStatusData(interface_name="Gi1", link_status="up", duplex="weird")
        assert d.duplex == "unknown"

    @pytest.mark.parametrize("status", ["up", "down", "unknown"])
    def test_all_link_statuses(self, status):
        d = InterfaceStatusData(interface_name="Gi1", link_status=status)
        assert d.link_status == status

    @pytest.mark.parametrize("duplex", ["full", "half", "auto", "unknown"])
    def test_all_duplex_modes(self, duplex):
        d = InterfaceStatusData(interface_name="Gi1", link_status="up", duplex=duplex)
        assert d.duplex == duplex


# ══════════════════════════════════════════════════════════════════
# FanStatusData
# ══════════════════════════════════════════════════════════════════


class TestFanStatusData:

    def test_valid(self):
        d = FanStatusData(fan_id="Fan 1", status="ok")
        assert d.status == "ok"

    @pytest.mark.parametrize("raw,expected", [
        ("OK", "ok"),
        ("Normal", "normal"),
        ("Good", "good"),
        ("FAIL", "fail"),
        ("Absent", "absent"),
        ("NotInstalled", "unknown"),
        (None, "unknown"),
    ])
    def test_status_normalization(self, raw, expected):
        d = FanStatusData(fan_id="Fan 1", status=raw)
        assert d.status == expected


# ══════════════════════════════════════════════════════════════════
# PowerData
# ══════════════════════════════════════════════════════════════════


class TestPowerData:

    def test_valid(self):
        d = PowerData(ps_id="PS-1", status="ok")
        assert d.ps_id == "PS-1"
        assert d.status == "ok"

    @pytest.mark.parametrize("raw,expected", [
        ("OK", "ok"),
        ("Normal", "normal"),
        ("Absent", "absent"),
        ("Not Present", "unknown"),
    ])
    def test_status_normalization(self, raw, expected):
        d = PowerData(ps_id="PS-1", status=raw)
        assert d.status == expected


# ══════════════════════════════════════════════════════════════════
# InterfaceErrorData
# ══════════════════════════════════════════════════════════════════


class TestInterfaceErrorData:

    def test_valid(self):
        d = InterfaceErrorData(interface_name="Gi1/0/1", crc_errors=42)
        assert d.crc_errors == 42

    def test_default_zero(self):
        d = InterfaceErrorData(interface_name="Gi1/0/1")
        assert d.crc_errors == 0

    def test_negative_rejected(self):
        with pytest.raises(ValidationError):
            InterfaceErrorData(interface_name="Gi1", crc_errors=-1)

    def test_large_value(self):
        d = InterfaceErrorData(interface_name="Gi1", crc_errors=999999999)
        assert d.crc_errors == 999999999

    def test_zero(self):
        d = InterfaceErrorData(interface_name="Gi1", crc_errors=0)
        assert d.crc_errors == 0


# ══════════════════════════════════════════════════════════════════
# TransceiverData & TransceiverChannelData
# ══════════════════════════════════════════════════════════════════


class TestTransceiverData:

    def test_sfp_single_channel(self):
        d = TransceiverData(
            interface_name="Gi1/0/1",
            temperature=35.5,
            voltage=3.3,
            channels=[
                TransceiverChannelData(channel=1, tx_power=-2.5, rx_power=-3.1)
            ],
        )
        assert len(d.channels) == 1
        assert d.channels[0].channel == 1

    def test_qsfp_four_channels(self):
        channels = [
            TransceiverChannelData(channel=i, tx_power=-1.0 * i, rx_power=-2.0 * i)
            for i in range(1, 5)
        ]
        d = TransceiverData(
            interface_name="HGE1/0/25",
            temperature=45.0,
            voltage=3.2,
            channels=channels,
        )
        assert len(d.channels) == 4

    def test_channel_out_of_range(self):
        with pytest.raises(ValidationError):
            TransceiverChannelData(channel=5, tx_power=-1.0, rx_power=-2.0)

    def test_channel_zero_rejected(self):
        with pytest.raises(ValidationError):
            TransceiverChannelData(channel=0, tx_power=-1.0, rx_power=-2.0)

    def test_temperature_extreme_accepted(self):
        """極端溫度值不再被 Pydantic 擋下（SNMP sentinel 由 collector 處理）。"""
        d = TransceiverData(
            interface_name="Gi1",
            temperature=200.0,
            voltage=3.3,
            channels=[],
        )
        assert d.temperature == 200.0

    def test_voltage_extreme_accepted(self):
        """極端電壓值不再被 Pydantic 擋下。"""
        d = TransceiverData(
            interface_name="Gi1",
            temperature=30.0,
            voltage=20.0,
            channels=[],
        )
        assert d.voltage == 20.0

    def test_tx_power_extreme_accepted(self):
        """極端 tx_power 值不再被 Pydantic 擋下。"""
        ch = TransceiverChannelData(channel=1, tx_power=20.0, rx_power=-1.0)
        assert ch.tx_power == 20.0

    def test_rx_power_extreme_accepted(self):
        """極端 rx_power 值不再被 Pydantic 擋下。"""
        ch = TransceiverChannelData(channel=1, tx_power=-1.0, rx_power=-50.0)
        assert ch.rx_power == -50.0

    def test_none_values_allowed(self):
        d = TransceiverData(
            interface_name="Gi1",
            temperature=None,
            voltage=None,
            channels=[
                TransceiverChannelData(channel=1, tx_power=None, rx_power=None)
            ],
        )
        assert d.temperature is None
        assert d.voltage is None
        assert d.channels[0].tx_power is None

    def test_empty_channels(self):
        d = TransceiverData(
            interface_name="Gi1",
            temperature=25.0,
            voltage=3.3,
            channels=[],
        )
        assert d.channels == []

    @pytest.mark.parametrize("temp", [-10.0, 0.0, 25.0, 50.0, 100.0])
    def test_temperature_boundaries(self, temp):
        d = TransceiverData(
            interface_name="Gi1", temperature=temp, voltage=3.3, channels=[]
        )
        assert d.temperature == temp

    @pytest.mark.parametrize("power", [-40.0, -20.0, 0.0, 5.0, 10.0])
    def test_power_boundaries(self, power):
        ch = TransceiverChannelData(channel=1, tx_power=power, rx_power=power)
        assert ch.tx_power == power


# ══════════════════════════════════════════════════════════════════
# VersionData
# ══════════════════════════════════════════════════════════════════


class TestVersionData:

    def test_valid(self):
        d = VersionData(version="16.9.4")
        assert d.version == "16.9.4"

    def test_empty_string(self):
        d = VersionData(version="")
        assert d.version == ""

    def test_long_version(self):
        d = VersionData(version="PI.5.3.1.9-20230101 Release 1234")
        assert "PI.5.3.1.9" in d.version


# ══════════════════════════════════════════════════════════════════
# NeighborData
# ══════════════════════════════════════════════════════════════════


class TestNeighborData:

    def test_valid(self):
        d = NeighborData(
            local_interface="Gi1/0/1",
            remote_hostname="SW-CORE-01",
            remote_interface="Gi0/1",
        )
        assert d.remote_hostname == "SW-CORE-01"

    def test_fqdn_hostname(self):
        d = NeighborData(
            local_interface="Gi1",
            remote_hostname="switch.example.com",
            remote_interface="Gi0/1",
        )
        assert d.remote_hostname == "switch.example.com"


# ══════════════════════════════════════════════════════════════════
# PortChannelData
# ══════════════════════════════════════════════════════════════════


class TestPortChannelData:

    def test_valid_up(self):
        d = PortChannelData(
            interface_name="Po1",
            status="up",
            members=["Gi1/0/1", "Gi1/0/2"],
        )
        assert d.status == "up"
        assert len(d.members) == 2

    def test_status_normalization(self):
        d = PortChannelData(interface_name="Po1", status="UP", members=[])
        assert d.status == "up"

    def test_empty_members(self):
        d = PortChannelData(interface_name="Po1", status="down", members=[])
        assert d.members == []

    def test_member_status_normalization(self):
        d = PortChannelData(
            interface_name="Po1",
            status="up",
            members=["Gi1/0/1"],
            member_status={"Gi1/0/1": "UP"},
        )
        assert d.member_status["Gi1/0/1"] == "up"

    def test_member_status_none(self):
        d = PortChannelData(
            interface_name="Po1", status="up", members=["Gi1"], member_status=None
        )
        assert d.member_status is None


# ══════════════════════════════════════════════════════════════════
# AclData
# ══════════════════════════════════════════════════════════════════


class TestAclData:

    def test_with_acl(self):
        d = AclData(interface_name="Gi1/0/1", acl_number="101")
        assert d.acl_number == "101"

    def test_no_acl(self):
        d = AclData(interface_name="Gi1/0/1", acl_number=None)
        assert d.acl_number is None

    def test_named_acl(self):
        d = AclData(interface_name="Gi1", acl_number="MY-ACL")
        assert d.acl_number == "MY-ACL"


# ══════════════════════════════════════════════════════════════════
# PingResultData
# ══════════════════════════════════════════════════════════════════


class TestPingResultData:

    def test_reachable(self):
        d = PingResultData(target="10.0.0.1", is_reachable=True)
        assert d.is_reachable is True

    def test_unreachable(self):
        d = PingResultData(target="10.0.0.1", is_reachable=False)
        assert d.is_reachable is False

    def test_ipv4_validation_valid(self):
        d = PingResultData(target="192.168.1.1", is_reachable=True)
        assert d.target == "192.168.1.1"

    def test_ipv4_validation_invalid_passes(self):
        """Invalid IPs are accepted (validator doesn't block)."""
        d = PingResultData(target="not-an-ip", is_reachable=False)
        assert d.target == "not-an-ip"

    def test_whitespace_stripped(self):
        d = PingResultData(target="  10.0.0.1  ", is_reachable=True)
        assert d.target == "10.0.0.1"

    @pytest.mark.parametrize("ip", [
        "10.0.0.1", "192.168.1.1", "172.16.0.1", "255.255.255.255", "0.0.0.0",
    ])
    def test_various_valid_ips(self, ip):
        d = PingResultData(target=ip, is_reachable=True)
        assert d.target == ip
