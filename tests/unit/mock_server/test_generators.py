"""Tests for mock_server.generators — all 13 generators."""


class TestMacTableGenerator:
    def test_hpe_format(self):
        from mock_server.generators.mac_table import generate

        output = generate("hpe")
        assert "MAC ADDR" in output
        assert "VLAN ID" in output
        assert "AGING" in output
        lines = output.strip().splitlines()
        assert len(lines) >= 2  # header + at least 1 data row

    def test_ios_format(self):
        from mock_server.generators.mac_table import generate

        output = generate("ios")
        assert "Mac Address Table" in output
        assert "DYNAMIC" in output

    def test_nxos_format(self):
        from mock_server.generators.mac_table import generate

        output = generate("nxos")
        assert "Legend:" in output
        assert "dynamic" in output

    def test_device_fail_returns_empty(self):
        from mock_server.generators.mac_table import generate

        output = generate("hpe", fails=True)
        assert "MAC ADDR" in output
        # Should be header only (empty table)
        lines = [line for line in output.strip().splitlines() if line.strip()]
        assert len(lines) == 1  # only header

    def test_port_names_match_interface_status(self):
        """Port names must match interface_status generator for join."""
        from mock_server.generators.mac_table import _port_name

        assert _port_name("hpe", 1) == "GE1/0/1"
        assert _port_name("ios", 1) == "Gi1/0/1"
        assert _port_name("nxos", 1) == "Eth1/1"

    def test_mac_format_per_device(self):
        from mock_server.generators.mac_table import _format_mac

        raw = "00:0C:29:AA:BB:01"
        assert _format_mac(raw, "hpe") == "000c-29aa-bb01"
        assert _format_mac(raw, "ios") == "000c.29aa.bb01"
        assert _format_mac(raw, "nxos") == "000c.29aa.bb01"

    def test_with_mac_list(self):
        from mock_server.generators.mac_table import generate

        mac_list = [
            {"mac_address": "AA:BB:CC:DD:EE:01"},
            {"mac_address": "AA:BB:CC:DD:EE:02"},
            {"mac_address": "AA:BB:CC:DD:EE:03"},
        ]
        output = generate("hpe", switch_ip="10.0.0.1", mac_list=mac_list)
        assert "MAC ADDR" in output


class TestInterfaceStatusGenerator:
    def test_hpe_format(self):
        from mock_server.generators.interface_status import generate

        output = generate("hpe")
        assert "Interface" in output
        assert "Link" in output
        lines = output.strip().splitlines()
        assert len(lines) >= 7  # header lines + data

    def test_ios_format(self):
        from mock_server.generators.interface_status import generate

        output = generate("ios")
        assert "Port" in output
        assert "Status" in output

    def test_nxos_format(self):
        from mock_server.generators.interface_status import generate

        output = generate("nxos")
        assert "Port" in output
        assert "Status" in output

    def test_hpe_interfaces_count(self):
        from mock_server.generators.interface_status import _HPE_INTERFACES

        assert len(_HPE_INTERFACES) == 20

    def test_ios_interfaces_count(self):
        from mock_server.generators.interface_status import _IOS_INTERFACES

        assert len(_IOS_INTERFACES) == 20

    def test_nxos_interfaces_count(self):
        from mock_server.generators.interface_status import _NXOS_INTERFACES

        assert len(_NXOS_INTERFACES) == 20

    def test_fail_mode_produces_down_interfaces(self):
        from mock_server.generators.interface_status import generate

        output = generate("hpe", fails=True)
        assert "DOWN" in output


class TestGnmsPingGenerator:
    def test_csv_format(self):
        from mock_server.generators.gnms_ping import generate

        output = generate(
            "hpe",
            switch_ips="10.0.0.1,10.0.0.2,10.0.0.3",
        )
        lines = output.strip().splitlines()
        assert lines[0] == "IP,Reachable,Latency_ms"
        assert len(lines) == 4  # header + 3 IPs

    def test_no_ips(self):
        from mock_server.generators.gnms_ping import generate

        output = generate("hpe")
        assert "IP,Reachable,Latency_ms" in output

    def test_deterministic_with_seed(self):
        import random
        from mock_server.generators.gnms_ping import generate

        random.seed(42)
        output1 = generate(
            "hpe",
            switch_ips="10.0.0.1,10.0.0.2",
            failure_rate=0.05,
        )
        random.seed(42)
        output2 = generate(
            "hpe",
            switch_ips="10.0.0.1,10.0.0.2",
            failure_rate=0.05,
        )
        assert output1 == output2

    def test_high_failure_rate(self):
        from mock_server.generators.gnms_ping import generate

        output = generate(
            "hpe",
            switch_ips="10.0.0.1,10.0.0.2,10.0.0.3",
            failure_rate=1.0,
        )
        assert "False" in output


class TestFanGenerator:
    def test_hpe(self):
        from mock_server.generators.fan import generate

        output = generate("hpe")
        assert "Slot" in output or "FanID" in output

    def test_ios(self):
        from mock_server.generators.fan import generate

        output = generate("ios")
        assert len(output.strip()) > 0

    def test_nxos(self):
        from mock_server.generators.fan import generate

        output = generate("nxos")
        assert len(output.strip()) > 0

    def test_fail_mode(self):
        from mock_server.generators.fan import generate

        output = generate("hpe", fails=True)
        assert "Absent" in output


class TestVersionGenerator:
    def test_hpe(self):
        from mock_server.generators.version import generate

        output = generate("hpe")
        assert "Version" in output or "version" in output

    def test_ios(self):
        from mock_server.generators.version import generate

        output = generate("ios")
        assert "Version" in output

    def test_nxos(self):
        from mock_server.generators.version import generate

        output = generate("nxos")
        assert len(output.strip()) > 0

    def test_fail_mode_different_version(self):
        from mock_server.generators.version import generate

        healthy = generate("hpe")
        failed = generate("hpe", fails=True)
        assert healthy != failed


class TestPowerGenerator:
    def test_hpe(self):
        from mock_server.generators.power import generate

        output = generate("hpe")
        assert len(output.strip()) > 0

    def test_ios(self):
        from mock_server.generators.power import generate

        output = generate("ios")
        assert len(output.strip()) > 0

    def test_nxos(self):
        from mock_server.generators.power import generate

        output = generate("nxos")
        assert len(output.strip()) > 0

    def test_fail_mode(self):
        from mock_server.generators.power import generate

        output = generate("hpe", fails=True)
        assert "Absent" in output


class TestErrorCountGenerator:
    def test_hpe(self):
        from mock_server.generators.error_count import generate

        output = generate("hpe")
        assert len(output.strip()) > 0

    def test_ios(self):
        from mock_server.generators.error_count import generate

        output = generate("ios")
        assert len(output.strip()) > 0


class TestUplinkGenerator:
    def test_hpe(self):
        from mock_server.generators.uplink import generate

        output = generate("hpe")
        assert len(output.strip()) > 0

    def test_ios(self):
        from mock_server.generators.uplink import generate

        output = generate("ios")
        assert len(output.strip()) > 0

    def test_fail_mode_reduces_neighbors(self):
        from mock_server.generators.uplink import generate

        healthy = generate("hpe")
        failed = generate("hpe", fails=True)
        assert healthy.count("LLDP neighbor") > failed.count("LLDP neighbor")


class TestChannelGroupGenerator:
    def test_hpe(self):
        from mock_server.generators.channel_group import generate

        output = generate("hpe")
        assert len(output.strip()) > 0

    def test_ios(self):
        from mock_server.generators.channel_group import generate

        output = generate("ios")
        assert len(output.strip()) > 0

    def test_fail_mode(self):
        from mock_server.generators.channel_group import generate

        output = generate("hpe", fails=True)
        assert "U" in output  # member status changes on failure


class TestGbicDetailsGenerator:
    def test_hpe(self):
        from mock_server.generators.gbic_details import generate

        output = generate("hpe")
        assert len(output.strip()) > 0

    def test_ios(self):
        from mock_server.generators.gbic_details import generate

        output = generate("ios")
        assert "Tx Power" in output or "dBm" in output

    def test_nxos(self):
        from mock_server.generators.gbic_details import generate

        output = generate("nxos")
        assert "Tx Power" in output


class TestStaticAclGenerator:
    def test_hpe(self):
        from mock_server.generators.static_acl import generate

        output = generate("hpe")
        assert "Interface,ACL" in output
        assert "3001" in output


class TestDynamicAclGenerator:
    def test_hpe(self):
        from mock_server.generators.dynamic_acl import generate

        output = generate("hpe")
        assert "Interface,ACL" in output
        # Generator produces CSV with numeric ACL numbers (e.g. "GE1/0/1,3561")
        lines = output.strip().splitlines()
        assert len(lines) > 1  # header + data rows
        assert "GE1/0/1" in output


class TestPingBatchGenerator:
    def test_reachable(self):
        import json
        from mock_server.generators.ping_batch import generate

        output = generate("hpe", switch_ip="10.0.0.1")
        data = json.loads(output)
        assert "result" in data
        stats = data["result"]["10.0.0.1"]
        assert stats["is_alive"] is True
        assert stats["packet_loss"] == 0
        assert stats["packets_received"] == 3

    def test_unreachable(self):
        import json
        from mock_server.generators.ping_batch import generate

        output = generate("hpe", fails=True, switch_ip="10.0.0.1")
        data = json.loads(output)
        stats = data["result"]["10.0.0.1"]
        assert stats["is_alive"] is False
        assert stats["packet_loss"] == 100.0
        assert stats["packets_received"] == 0
