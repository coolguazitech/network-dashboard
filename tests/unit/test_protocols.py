"""Tests for app.parsers.protocols — ParsedData models and helpers."""
import pytest

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
    TransceiverData,
    VersionData,
    _normalize_mac,
    _normalize_operational_status,
    _normalize_link_status,
    _validate_ipv4,
)


class TestNormalizeMac:
    """Test MAC address normalization helper."""

    def test_colon_format(self):
        assert _normalize_mac("aa:bb:cc:dd:ee:ff") == "AA:BB:CC:DD:EE:FF"

    def test_hyphen_format(self):
        assert _normalize_mac("AA-BB-CC-DD-EE-FF") == "AA:BB:CC:DD:EE:FF"

    def test_dot_format_cisco(self):
        assert _normalize_mac("aabb.ccdd.eeff") == "AA:BB:CC:DD:EE:FF"

    def test_hpe_format(self):
        assert _normalize_mac("aabb-ccdd-eeff") == "AA:BB:CC:DD:EE:FF"

    def test_no_separator(self):
        assert _normalize_mac("aabbccddeeff") == "AA:BB:CC:DD:EE:FF"

    def test_invalid_length(self):
        result = _normalize_mac("aabb")
        assert result == "AABB"  # returned upper, not normalized

    def test_non_hex(self):
        result = _normalize_mac("gggg.hhhh.iiii")
        assert result == "GGGG.HHHH.IIII"  # returned upper, not normalized

    def test_mixed_case(self):
        assert _normalize_mac("Aa:Bb:Cc:Dd:Ee:Ff") == "AA:BB:CC:DD:EE:FF"


class TestNormalizeOperationalStatus:
    def test_normal_values(self):
        assert _normalize_operational_status("Normal") == "normal"
        assert _normalize_operational_status("OK") == "ok"
        assert _normalize_operational_status("ok") == "ok"

    def test_none(self):
        assert _normalize_operational_status(None) == "unknown"

    def test_unknown_value(self):
        assert _normalize_operational_status("bogus") == "unknown"

    def test_whitespace(self):
        assert _normalize_operational_status("  ok  ") == "ok"


class TestNormalizeLinkStatus:
    def test_up(self):
        assert _normalize_link_status("UP") == "up"
        assert _normalize_link_status("up") == "up"

    def test_down(self):
        assert _normalize_link_status("down") == "down"

    def test_none(self):
        assert _normalize_link_status(None) == "unknown"

    def test_unknown(self):
        assert _normalize_link_status("bogus") == "unknown"


class TestValidateIpv4:
    def test_valid(self):
        assert _validate_ipv4("192.168.1.1") == "192.168.1.1"

    def test_whitespace(self):
        assert _validate_ipv4("  10.0.0.1  ") == "10.0.0.1"

    def test_invalid_returns_as_is(self):
        assert _validate_ipv4("not-an-ip") == "not-an-ip"


# ── ParsedData model tests ──


class TestMacTableData:
    def test_mac_normalization(self):
        d = MacTableData(
            mac_address="aabb.ccdd.eeff",
            interface_name="Gi1/0/1",
            vlan_id=10,
        )
        assert d.mac_address == "AA:BB:CC:DD:EE:FF"

    def test_hpe_mac_normalization(self):
        d = MacTableData(
            mac_address="000c-29aa-bb01",
            interface_name="GE1/0/1",
            vlan_id=100,
        )
        assert d.mac_address == "00:0C:29:AA:BB:01"

    def test_vlan_range(self):
        with pytest.raises(Exception):
            MacTableData(mac_address="AA:BB:CC:DD:EE:FF", interface_name="Gi1/0/1", vlan_id=0)
        with pytest.raises(Exception):
            MacTableData(mac_address="AA:BB:CC:DD:EE:FF", interface_name="Gi1/0/1", vlan_id=4095)

    def test_valid_vlan_boundaries(self):
        d1 = MacTableData(mac_address="AA:BB:CC:DD:EE:FF", interface_name="Gi1/0/1", vlan_id=1)
        assert d1.vlan_id == 1
        d2 = MacTableData(mac_address="AA:BB:CC:DD:EE:FF", interface_name="Gi1/0/1", vlan_id=4094)
        assert d2.vlan_id == 4094



class TestFanStatusData:
    def test_status_normalization(self):
        d = FanStatusData(fan_id="Fan 1/1", status="Normal")
        assert d.status == "normal"

    def test_unknown_status(self):
        d = FanStatusData(fan_id="Fan 1/1", status="SomeWeirdStatus")
        assert d.status == "unknown"

    def test_none_status(self):
        d = FanStatusData(fan_id="Fan 1/1", status=None)
        assert d.status == "unknown"


class TestVersionData:
    def test_basic(self):
        d = VersionData(version="15.2(4)E10", model="WS-C3750X", serial_number="FDO1234")
        assert d.version == "15.2(4)E10"
        assert d.model == "WS-C3750X"

    def test_optional_fields(self):
        d = VersionData(version="1.0")
        assert d.model is None
        assert d.serial_number is None
        assert d.uptime is None


class TestPortChannelData:
    def test_status_normalization(self):
        d = PortChannelData(
            interface_name="Po1", status="UP", members=["Gi1/0/1"]
        )
        assert d.status == "up"

    def test_protocol_normalization(self):
        d = PortChannelData(
            interface_name="Po1", status="up", protocol="LACP",
            members=["Gi1/0/1"],
        )
        assert d.protocol == "lacp"

    def test_unknown_protocol(self):
        d = PortChannelData(
            interface_name="Po1", status="up", protocol="WeirdProto",
            members=["Gi1/0/1"],
        )
        assert d.protocol == "none"

    def test_member_status_normalization(self):
        d = PortChannelData(
            interface_name="Po1", status="up", members=["Gi1/0/1"],
            member_status={"Gi1/0/1": "UP"},
        )
        assert d.member_status == {"Gi1/0/1": "up"}


class TestPowerData:
    def test_status_normalization(self):
        d = PowerData(ps_id="PS 1/1", status="Normal")
        assert d.status == "normal"

    def test_sub_status_normalization(self):
        d = PowerData(
            ps_id="PS 1/1", status="ok",
            input_status="OK", output_status="OK",
        )
        assert d.input_status == "ok"
        assert d.output_status == "ok"

    def test_none_sub_status(self):
        d = PowerData(ps_id="PS 1/1", status="ok")
        assert d.input_status is None
        assert d.output_status is None


class TestInterfaceStatusData:
    def test_link_status_normalization(self):
        d = InterfaceStatusData(
            interface_name="GE1/0/1", link_status="UP", speed="1G", duplex="Full",
        )
        assert d.link_status == "up"

    def test_duplex_normalization(self):
        d = InterfaceStatusData(
            interface_name="GE1/0/1", link_status="up", duplex="Full",
        )
        assert d.duplex == "full"

    def test_unknown_duplex(self):
        d = InterfaceStatusData(
            interface_name="GE1/0/1", link_status="up", duplex="WeirdMode",
        )
        assert d.duplex == "unknown"


class TestInterfaceErrorData:
    def test_defaults_to_zero(self):
        d = InterfaceErrorData(interface_name="GE1/0/1")
        assert d.crc_errors == 0
        assert d.input_errors == 0
        assert d.output_errors == 0

    def test_negative_rejected(self):
        with pytest.raises(Exception):
            InterfaceErrorData(interface_name="GE1/0/1", crc_errors=-1)


class TestNeighborData:
    def test_basic(self):
        d = NeighborData(
            local_interface="GE1/0/1",
            remote_hostname="CORE-SW-01",
            remote_interface="Gi0/0/1",
        )
        assert d.remote_platform is None


class TestAclData:
    def test_basic(self):
        d = AclData(interface_name="GE1/0/1", acl_number="3001")
        assert d.acl_number == "3001"

    def test_none_acl(self):
        d = AclData(interface_name="GE1/0/1")
        assert d.acl_number is None


class TestPingResultData:
    def test_reachable(self):
        d = PingResultData(target="10.0.0.1", is_reachable=True, success_rate=100.0)
        assert d.is_reachable is True

    def test_unreachable(self):
        d = PingResultData(target="10.0.0.1", is_reachable=False)
        assert d.success_rate == 0.0

    def test_ip_validation(self):
        d = PingResultData(target="192.168.1.1", is_reachable=True)
        assert d.target == "192.168.1.1"


class TestTransceiverData:
    def test_basic(self):
        d = TransceiverData(
            interface_name="GE1/0/1",
            tx_power=-2.5,
            rx_power=-3.1,
            temperature=36.0,
            voltage=3.3,
        )
        assert d.tx_power == -2.5
        assert d.temperature == 36.0
