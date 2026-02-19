"""Tests for all parsers using real raw test data files.

Each parser is tested against the actual CLI output samples in test_data/raw/.
"""
from pathlib import Path

import pytest

from tests.conftest import load_raw


# ── HPE Parsers ──


class TestGetFanHpeDnaParser:
    def test_parse_real_data(self):
        from app.parsers.plugins.get_fan_hpe_dna_parser import GetFanHpeDnaParser

        parser = GetFanHpeDnaParser()
        raw = load_raw("get_fan_hpe_10.10.1.1.txt")
        results = parser.parse(raw)

        assert len(results) == 6
        assert results[0].fan_id == "Fan 1/1"
        assert results[0].status == "normal"

    def test_empty_input(self):
        from app.parsers.plugins.get_fan_hpe_dna_parser import GetFanHpeDnaParser

        parser = GetFanHpeDnaParser()
        assert parser.parse("") == []
        assert parser.parse("   ") == []


class TestGetVersionHpeDnaParser:
    def test_parse_real_data(self):
        from app.parsers.plugins.get_version_hpe_dna_parser import GetVersionHpeDnaParser

        parser = GetVersionHpeDnaParser()
        raw = load_raw("get_version_hpe_10.10.1.1.txt")
        results = parser.parse(raw)

        assert len(results) == 1
        v = results[0]
        assert "7.1.070" in v.version
        assert v.model is not None
        assert v.serial_number is not None

    def test_empty_input(self):
        from app.parsers.plugins.get_version_hpe_dna_parser import GetVersionHpeDnaParser

        parser = GetVersionHpeDnaParser()
        assert parser.parse("") == []


class TestGetVersionIosDnaParser:
    def test_parse_real_data(self):
        from app.parsers.plugins.get_version_ios_dna_parser import GetVersionIosDnaParser

        parser = GetVersionIosDnaParser()
        raw = load_raw("get_version_ios_10.10.2.1.txt")
        results = parser.parse(raw)

        assert len(results) == 1
        v = results[0]
        assert "15.2(4)E10" in v.version
        assert v.model == "WS-C3750X-48PF-L"
        assert v.serial_number == "FDO1234A5BC"
        assert "30 weeks" in v.uptime


class TestGetVersionNxosDnaParser:
    def test_parse_real_data(self):
        from app.parsers.plugins.get_version_nxos_dna_parser import GetVersionNxosDnaParser

        parser = GetVersionNxosDnaParser()
        raw = load_raw("get_version_nxos_10.10.3.1.txt")
        results = parser.parse(raw)

        assert len(results) == 1
        assert results[0].version  # version string present


class TestGetErrorCountHpeFnaParser:
    def test_parse_real_data(self):
        from app.parsers.plugins.get_error_count_hpe_fna_parser import GetErrorCountHpeFnaParser

        parser = GetErrorCountHpeFnaParser()
        raw = load_raw("get_error_count_hpe_10.10.1.1.txt")
        results = parser.parse(raw)

        assert len(results) >= 1
        # All results should have interface_name
        for r in results:
            assert r.interface_name
            assert r.crc_errors >= 0

    def test_empty_input(self):
        from app.parsers.plugins.get_error_count_hpe_fna_parser import GetErrorCountHpeFnaParser

        parser = GetErrorCountHpeFnaParser()
        assert parser.parse("") == []


class TestGetUplinkHpeFnaParser:
    def test_parse_real_data(self):
        from app.parsers.plugins.get_uplink_hpe_fna_parser import GetUplinkHpeFnaParser

        parser = GetUplinkHpeFnaParser()
        raw = load_raw("get_uplink_hpe_10.10.1.1.txt")
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.local_interface
            assert r.remote_hostname
            assert r.remote_interface


class TestGetStaticAclHpeFnaParser:
    def test_parse_real_data(self):
        from app.parsers.plugins.get_static_acl_hpe_fna_parser import GetStaticAclHpeFnaParser

        parser = GetStaticAclHpeFnaParser()
        raw = load_raw("get_static_acl_hpe_10.10.1.1.txt")
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.interface_name

    def test_empty_input(self):
        from app.parsers.plugins.get_static_acl_hpe_fna_parser import GetStaticAclHpeFnaParser

        parser = GetStaticAclHpeFnaParser()
        assert parser.parse("") == []


class TestGetGbicDetailsHpeFnaParser:
    def test_parse_real_data(self):
        from app.parsers.plugins.get_gbic_details_hpe_fna_parser import GetGbicDetailsHpeFnaParser

        parser = GetGbicDetailsHpeFnaParser()
        raw = load_raw("get_gbic_details_hpe_10.10.1.1.txt")
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.interface_name


class TestGetPowerHpeDnaParser:
    def test_parse_real_data(self):
        from app.parsers.plugins.get_power_hpe_dna_parser import GetPowerHpeDnaParser

        parser = GetPowerHpeDnaParser()
        raw = load_raw("get_power_hpe_10.10.1.1.txt")
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.ps_id
            assert r.status



class TestGetMacTableHpeDnaParser:
    def test_parse_real_data(self):
        from app.parsers.plugins.get_mac_table_hpe_dna_parser import GetMacTableHpeDnaParser

        parser = GetMacTableHpeDnaParser()
        raw = load_raw("get_mac_table_hpe_10.10.1.1.txt")
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.mac_address
            assert ":" in r.mac_address  # normalized
            assert r.interface_name
            assert 1 <= r.vlan_id <= 4094

    def test_empty_input(self):
        from app.parsers.plugins.get_mac_table_hpe_dna_parser import GetMacTableHpeDnaParser

        parser = GetMacTableHpeDnaParser()
        assert parser.parse("") == []

    def test_csv_format(self):
        from app.parsers.plugins.get_mac_table_hpe_dna_parser import GetMacTableHpeDnaParser

        parser = GetMacTableHpeDnaParser()
        csv_input = "MAC,Interface,VLAN\nAA:BB:CC:DD:EE:01,GE1/0/1,10\n"
        results = parser.parse(csv_input)
        assert len(results) == 1
        assert results[0].interface_name == "GE1/0/1"
        assert results[0].vlan_id == 10


# ── IOS Parsers ──


class TestGetMacTableIosDnaParser:
    def test_parse_real_data(self):
        from app.parsers.plugins.get_mac_table_ios_dna_parser import GetMacTableIosDnaParser

        parser = GetMacTableIosDnaParser()
        raw = load_raw("get_mac_table_ios_10.10.2.1.txt")
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.mac_address
            assert ":" in r.mac_address
            assert r.interface_name
            assert 1 <= r.vlan_id <= 4094


class TestGetChannelGroupIosFnaParser:
    def test_parse_real_data(self):
        from app.parsers.plugins.get_channel_group_ios_fna_parser import GetChannelGroupIosFnaParser

        parser = GetChannelGroupIosFnaParser()
        raw = load_raw("get_channel_group_ios_10.10.2.1.txt")
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.interface_name
            assert r.status in ("up", "down", "unknown")
            assert len(r.members) >= 1


# ── NXOS Parsers ──


class TestGetMacTableNxosDnaParser:
    def test_parse_real_data(self):
        from app.parsers.plugins.get_mac_table_nxos_dna_parser import GetMacTableNxosDnaParser

        parser = GetMacTableNxosDnaParser()
        raw = load_raw("get_mac_table_nxos_10.10.3.1.txt")
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.mac_address
            assert ":" in r.mac_address
            assert 1 <= r.vlan_id <= 4094


# ── Inline CLI tests (no raw data file dependency) ──


class TestGetMacTableHpeInline:
    """Test HPE MAC table parser with inline CLI text."""

    def test_cli_format(self):
        from app.parsers.plugins.get_mac_table_hpe_dna_parser import GetMacTableHpeDnaParser

        parser = GetMacTableHpeDnaParser()
        cli = (
            "MAC ADDR          VLAN ID  STATE          PORT INDEX               AGING TIME(s)\n"
            "000c-29aa-bb01    100      Learned        GigabitEthernet1/0/1     AGING\n"
            "000c-29aa-bb02    200      Learned        GigabitEthernet1/0/2     AGING\n"
        )
        results = parser.parse(cli)
        assert len(results) == 2
        assert results[0].mac_address == "00:0C:29:AA:BB:01"
        assert results[0].vlan_id == 100
        assert results[0].interface_name == "GigabitEthernet1/0/1"
        assert results[1].vlan_id == 200

    def test_header_only(self):
        from app.parsers.plugins.get_mac_table_hpe_dna_parser import GetMacTableHpeDnaParser

        parser = GetMacTableHpeDnaParser()
        cli = "MAC ADDR          VLAN ID  STATE          PORT INDEX               AGING TIME(s)\n"
        results = parser.parse(cli)
        assert results == []


class TestGetMacTableIosInline:
    def test_cli_format(self):
        from app.parsers.plugins.get_mac_table_ios_dna_parser import GetMacTableIosDnaParser

        parser = GetMacTableIosDnaParser()
        cli = (
            "          Mac Address Table\n"
            "-------------------------------------------\n"
            "\n"
            "Vlan    Mac Address       Type        Ports\n"
            "----    -----------       --------    -----\n"
            "  10    aabb.ccdd.ee01    DYNAMIC     Gi1/0/1\n"
            "  20    aabb.ccdd.ee02    DYNAMIC     Gi1/0/2\n"
            "Total Mac Addresses for this criterion: 2\n"
        )
        results = parser.parse(cli)
        assert len(results) == 2
        assert results[0].vlan_id == 10
        assert results[0].mac_address == "AA:BB:CC:DD:EE:01"
        assert results[0].interface_name == "Gi1/0/1"


class TestGetMacTableNxosInline:
    def test_cli_format(self):
        from app.parsers.plugins.get_mac_table_nxos_dna_parser import GetMacTableNxosDnaParser

        parser = GetMacTableNxosDnaParser()
        cli = (
            "Legend:\n"
            "        * - primary entry, G - Gateway MAC\n"
            "        age - seconds since last seen\n"
            "\n"
            "   VLAN     MAC Address      Type      age     Secure   NTFY   Ports\n"
            "---------+-----------------+--------+---------+------+----+------------------\n"
            "*   10     aabb.ccdd.ee01   dynamic  0         F       F    Eth1/1\n"
            "*   20     aabb.ccdd.ee02   dynamic  0         F       F    Eth1/2\n"
        )
        results = parser.parse(cli)
        assert len(results) == 2
        assert results[0].vlan_id == 10
        assert results[0].mac_address == "AA:BB:CC:DD:EE:01"


class TestPingBatchParser:
    def test_json_format(self):
        from app.parsers.plugins.ping_batch_parser import PingBatchParser

        parser = PingBatchParser()
        json_input = '{"results": [{"ip": "10.0.0.1", "reachable": true}, {"ip": "10.0.0.2", "reachable": false}]}'
        results = parser.parse(json_input)
        assert len(results) == 2
        assert results[0].target == "10.0.0.1"
        assert results[0].is_reachable is True
        assert results[1].is_reachable is False

    def test_empty_input(self):
        from app.parsers.plugins.ping_batch_parser import PingBatchParser

        parser = PingBatchParser()
        assert parser.parse("") == []


class TestInterfaceStatusParsersInline:
    def test_hpe_parser(self):
        from app.parsers.plugins.get_interface_status_hpe_dna_parser import GetInterfaceStatusHpeDnaParser

        parser = GetInterfaceStatusHpeDnaParser()
        cli = (
            "Brief information on interfaces in route mode:\n"
            "Link: ADM - administratively down; Stby - standby\n"
            "Speed: (a) - auto\n"
            "Duplex: (a)/A - auto; H - half; F - full\n"
            "Type: A - access; T - trunk; H - hybrid\n"
            "Interface            Link Speed   Duplex Type  PVID Description\n"
            "GE1/0/1              UP   1G(a)   F(a)   A     1\n"
            "GE1/0/2              DOWN auto     A      A     1\n"
            "XGE1/0/1             UP   10G(a)  F(a)   T     1\n"
        )
        results = parser.parse(cli)
        assert len(results) >= 2
        up_intfs = [r for r in results if r.link_status == "up"]
        down_intfs = [r for r in results if r.link_status == "down"]
        assert len(up_intfs) >= 1
        assert len(down_intfs) >= 1

    def test_ios_parser(self):
        from app.parsers.plugins.get_interface_status_ios_dna_parser import GetInterfaceStatusIosDnaParser

        parser = GetInterfaceStatusIosDnaParser()
        cli = (
            "Port          Name               Status       Vlan       Duplex  Speed Type\n"
            "Gi1/0/1                          connected    1          a-full  a-1000 10/100/1000BaseTX\n"
            "Gi1/0/2                          notconnect   1          auto    auto   10/100/1000BaseTX\n"
            "Te1/1/1                          connected    trunk      full    10G    10GBase-SR\n"
        )
        results = parser.parse(cli)
        assert len(results) >= 2

    def test_nxos_parser(self):
        from app.parsers.plugins.get_interface_status_nxos_dna_parser import GetInterfaceStatusNxosDnaParser

        parser = GetInterfaceStatusNxosDnaParser()
        cli = (
            "Port          Name               Status    Vlan      Duplex  Speed   Type\n"
            "Eth1/1                            connected 1         full    1000    1000base-T\n"
            "Eth1/2                            notconnec 1         auto    auto    1000base-T\n"
        )
        results = parser.parse(cli)
        assert len(results) >= 1
