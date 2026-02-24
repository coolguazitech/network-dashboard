"""Integration tests: mock server generators → parser pipeline.

Verifies that each mock generator produces output that the corresponding
parser can successfully parse. This is the critical contract between
mock and production code.
"""
import pytest


class TestMacTablePipeline:
    """Mock mac_table generator → parser pipeline for all device types."""

    def test_hpe_pipeline(self):
        from mock_server.generators.mac_table import generate
        from app.parsers.plugins.get_mac_table_hpe_dna_parser import GetMacTableHpeDnaParser

        raw = generate("hpe")
        parser = GetMacTableHpeDnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.mac_address
            assert ":" in r.mac_address  # normalized
            assert r.interface_name
            assert 1 <= r.vlan_id <= 4094

    def test_ios_pipeline(self):
        from mock_server.generators.mac_table import generate
        from app.parsers.plugins.get_mac_table_ios_dna_parser import GetMacTableIosDnaParser

        raw = generate("ios")
        parser = GetMacTableIosDnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert ":" in r.mac_address
            assert 1 <= r.vlan_id <= 4094

    def test_nxos_pipeline(self):
        from mock_server.generators.mac_table import generate
        from app.parsers.plugins.get_mac_table_nxos_dna_parser import GetMacTableNxosDnaParser

        raw = generate("nxos")
        parser = GetMacTableNxosDnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert ":" in r.mac_address
            assert 1 <= r.vlan_id <= 4094

    def test_hpe_empty_table(self):
        """Device fails → empty table → parser returns []."""
        from mock_server.generators.mac_table import generate
        from app.parsers.plugins.get_mac_table_hpe_dna_parser import GetMacTableHpeDnaParser

        raw = generate("hpe", fails=True)
        parser = GetMacTableHpeDnaParser()
        results = parser.parse(raw)
        assert results == []

    def test_hpe_with_mac_list(self):
        """MAC list from DB → generator produces matching MACs."""
        from mock_server.generators.mac_table import generate
        from app.parsers.plugins.get_mac_table_hpe_dna_parser import GetMacTableHpeDnaParser

        mac_list = [
            {"mac_address": f"AA:BB:CC:DD:EE:{i:02X}"}
            for i in range(1, 20)
        ]
        raw = generate("hpe", switch_ip="10.0.0.1", mac_list=mac_list)
        parser = GetMacTableHpeDnaParser()
        results = parser.parse(raw)

        # With 19 MACs and ~1/3 hash selection, expect some results
        assert len(results) >= 1


class TestInterfaceStatusPipeline:
    """Mock interface_status generator → parser pipeline."""

    def test_hpe_pipeline(self):
        from mock_server.generators.interface_status import generate
        from app.parsers.plugins.get_interface_status_hpe_dna_parser import GetInterfaceStatusHpeDnaParser

        raw = generate("hpe")
        parser = GetInterfaceStatusHpeDnaParser()
        results = parser.parse(raw)

        assert len(results) >= 10
        statuses = {r.link_status for r in results}
        assert "up" in statuses

    def test_ios_pipeline(self):
        from mock_server.generators.interface_status import generate
        from app.parsers.plugins.get_interface_status_ios_dna_parser import GetInterfaceStatusIosDnaParser

        raw = generate("ios")
        parser = GetInterfaceStatusIosDnaParser()
        results = parser.parse(raw)

        assert len(results) >= 10

    def test_nxos_pipeline(self):
        from mock_server.generators.interface_status import generate
        from app.parsers.plugins.get_interface_status_nxos_dna_parser import GetInterfaceStatusNxosDnaParser

        raw = generate("nxos")
        parser = GetInterfaceStatusNxosDnaParser()
        results = parser.parse(raw)

        assert len(results) >= 10

    def test_hpe_fail_mode(self):
        """Failed device → some interfaces DOWN."""
        from mock_server.generators.interface_status import generate
        from app.parsers.plugins.get_interface_status_hpe_dna_parser import GetInterfaceStatusHpeDnaParser

        raw = generate("hpe", fails=True)
        parser = GetInterfaceStatusHpeDnaParser()
        results = parser.parse(raw)

        down_count = sum(1 for r in results if r.link_status == "down")
        assert down_count >= 1


class TestFanPipeline:
    def test_hpe(self):
        from mock_server.generators.fan import generate
        from app.parsers.plugins.get_fan_hpe_dna_parser import GetFanHpeDnaParser

        raw = generate("hpe")
        parser = GetFanHpeDnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.fan_id
            assert r.status in ("ok", "good", "normal", "online", "active", "fail", "absent", "unknown")

    def test_ios(self):
        from mock_server.generators.fan import generate
        from app.parsers.plugins.get_fan_ios_dna_parser import GetFanIosDnaParser

        raw = generate("ios")
        parser = GetFanIosDnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1

    def test_nxos(self):
        from mock_server.generators.fan import generate
        from app.parsers.plugins.get_fan_nxos_dna_parser import GetFanNxosDnaParser

        raw = generate("nxos")
        parser = GetFanNxosDnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1


class TestVersionPipeline:
    def test_hpe(self):
        from mock_server.generators.version import generate
        from app.parsers.plugins.get_version_hpe_dna_parser import GetVersionHpeDnaParser

        raw = generate("hpe")
        parser = GetVersionHpeDnaParser()
        results = parser.parse(raw)

        assert len(results) == 1
        assert results[0].version

    def test_ios(self):
        from mock_server.generators.version import generate
        from app.parsers.plugins.get_version_ios_dna_parser import GetVersionIosDnaParser

        raw = generate("ios")
        parser = GetVersionIosDnaParser()
        results = parser.parse(raw)

        assert len(results) == 1
        assert results[0].version

    def test_nxos(self):
        from mock_server.generators.version import generate
        from app.parsers.plugins.get_version_nxos_dna_parser import GetVersionNxosDnaParser

        raw = generate("nxos")
        parser = GetVersionNxosDnaParser()
        results = parser.parse(raw)

        assert len(results) == 1
        assert results[0].version


class TestPowerPipeline:
    def test_hpe(self):
        from mock_server.generators.power import generate
        from app.parsers.plugins.get_power_hpe_dna_parser import GetPowerHpeDnaParser

        raw = generate("hpe")
        parser = GetPowerHpeDnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.ps_id
            assert r.status

    def test_ios(self):
        from mock_server.generators.power import generate
        from app.parsers.plugins.get_power_ios_dna_parser import GetPowerIosDnaParser

        raw = generate("ios")
        parser = GetPowerIosDnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1

    def test_nxos(self):
        from mock_server.generators.power import generate
        from app.parsers.plugins.get_power_nxos_dna_parser import GetPowerNxosDnaParser

        raw = generate("nxos")
        parser = GetPowerNxosDnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1


class TestErrorCountPipeline:
    def test_hpe(self):
        from mock_server.generators.error_count import generate
        from app.parsers.plugins.get_error_count_hpe_fna_parser import GetErrorCountHpeFnaParser

        raw = generate("hpe")
        parser = GetErrorCountHpeFnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.interface_name
            assert r.crc_errors >= 0

    def test_ios(self):
        from mock_server.generators.error_count import generate
        from app.parsers.plugins.get_error_count_ios_fna_parser import GetErrorCountIosFnaParser

        raw = generate("ios")
        parser = GetErrorCountIosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1

    def test_nxos(self):
        from mock_server.generators.error_count import generate
        from app.parsers.plugins.get_error_count_nxos_fna_parser import GetErrorCountNxosFnaParser

        raw = generate("nxos")
        parser = GetErrorCountNxosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1


class TestUplinkLldpPipeline:
    def test_hpe_lldp(self):
        from mock_server.generators.uplink import generate_lldp
        from app.parsers.plugins.get_uplink_lldp_hpe_dna_parser import GetUplinkLldpHpeDnaParser

        raw = generate_lldp("hpe")
        parser = GetUplinkLldpHpeDnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.local_interface
            assert r.remote_hostname

    def test_ios_lldp(self):
        from mock_server.generators.uplink import generate_lldp
        from app.parsers.plugins.get_uplink_lldp_ios_dna_parser import GetUplinkLldpIosDnaParser

        raw = generate_lldp("ios")
        parser = GetUplinkLldpIosDnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1

    def test_nxos_lldp(self):
        from mock_server.generators.uplink import generate_lldp
        from app.parsers.plugins.get_uplink_lldp_nxos_dna_parser import GetUplinkLldpNxosDnaParser

        raw = generate_lldp("nxos")
        parser = GetUplinkLldpNxosDnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1


class TestUplinkCdpPipeline:
    def test_ios_cdp(self):
        from mock_server.generators.uplink import generate_cdp
        from app.parsers.plugins.get_uplink_cdp_ios_dna_parser import GetUplinkCdpIosDnaParser

        raw = generate_cdp("ios")
        parser = GetUplinkCdpIosDnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1
        for r in results:
            assert r.local_interface
            assert r.remote_hostname

    def test_nxos_cdp(self):
        from mock_server.generators.uplink import generate_cdp
        from app.parsers.plugins.get_uplink_cdp_nxos_dna_parser import GetUplinkCdpNxosDnaParser

        raw = generate_cdp("nxos")
        parser = GetUplinkCdpNxosDnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1


class TestChannelGroupPipeline:
    def test_hpe(self):
        from mock_server.generators.channel_group import generate
        from app.parsers.plugins.get_channel_group_hpe_fna_parser import GetChannelGroupHpeFnaParser

        raw = generate("hpe")
        parser = GetChannelGroupHpeFnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.interface_name
            assert len(r.members) >= 1

    def test_ios(self):
        from mock_server.generators.channel_group import generate
        from app.parsers.plugins.get_channel_group_ios_fna_parser import GetChannelGroupIosFnaParser

        raw = generate("ios")
        parser = GetChannelGroupIosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1

    def test_nxos(self):
        from mock_server.generators.channel_group import generate
        from app.parsers.plugins.get_channel_group_nxos_fna_parser import GetChannelGroupNxosFnaParser

        raw = generate("nxos")
        parser = GetChannelGroupNxosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1


class TestGbicDetailsPipeline:
    @pytest.mark.xfail(reason="Mock HPE gbic output missing 'transceiver diagnostic' header format")
    def test_hpe(self):
        from mock_server.generators.gbic_details import generate
        from app.parsers.plugins.get_gbic_details_hpe_fna_parser import GetGbicDetailsHpeFnaParser

        raw = generate("hpe")
        parser = GetGbicDetailsHpeFnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.interface_name

    @pytest.mark.xfail(reason="Mock IOS gbic output missing Current(mA) column")
    def test_ios(self):
        from mock_server.generators.gbic_details import generate
        from app.parsers.plugins.get_gbic_details_ios_fna_parser import GetGbicDetailsIosFnaParser

        raw = generate("ios")
        parser = GetGbicDetailsIosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1

    def test_nxos(self):
        from mock_server.generators.gbic_details import generate
        from app.parsers.plugins.get_gbic_details_nxos_fna_parser import GetGbicDetailsNxosFnaParser

        raw = generate("nxos")
        parser = GetGbicDetailsNxosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1



class TestStaticAclPipeline:
    def test_hpe(self):
        from mock_server.generators.static_acl import generate
        from app.parsers.plugins.get_static_acl_hpe_fna_parser import GetStaticAclHpeFnaParser

        raw = generate("hpe")
        parser = GetStaticAclHpeFnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.interface_name

    def test_ios(self):
        from mock_server.generators.static_acl import generate
        from app.parsers.plugins.get_static_acl_ios_fna_parser import GetStaticAclIosFnaParser

        raw = generate("ios")
        parser = GetStaticAclIosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1

    def test_nxos(self):
        from mock_server.generators.static_acl import generate
        from app.parsers.plugins.get_static_acl_nxos_fna_parser import GetStaticAclNxosFnaParser

        raw = generate("nxos")
        parser = GetStaticAclNxosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1


class TestDynamicAclPipeline:
    def test_hpe(self):
        from mock_server.generators.dynamic_acl import generate
        from app.parsers.plugins.get_dynamic_acl_hpe_fna_parser import GetDynamicAclHpeFnaParser

        raw = generate("hpe")
        parser = GetDynamicAclHpeFnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1

    def test_ios(self):
        from mock_server.generators.dynamic_acl import generate
        from app.parsers.plugins.get_dynamic_acl_ios_fna_parser import GetDynamicAclIosFnaParser

        raw = generate("ios")
        parser = GetDynamicAclIosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1

    def test_nxos(self):
        from mock_server.generators.dynamic_acl import generate
        from app.parsers.plugins.get_dynamic_acl_nxos_fna_parser import GetDynamicAclNxosFnaParser

        raw = generate("nxos")
        parser = GetDynamicAclNxosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1


class TestPingBatchPipeline:
    def test_default(self):
        from mock_server.generators.ping_batch import generate
        from app.parsers.plugins.ping_batch_parser import PingBatchParser

        raw = generate("hpe", switch_ip="10.0.0.1")
        parser = PingBatchParser()
        results = parser.parse(raw)

        assert len(results) == 1
        r = results[0]
        assert r.target == "10.0.0.1"
        assert r.is_reachable is True

    def test_unreachable(self):
        from mock_server.generators.ping_batch import generate
        from app.parsers.plugins.ping_batch_parser import PingBatchParser

        raw = generate("hpe", fails=True, switch_ip="10.0.0.1")
        parser = PingBatchParser()
        results = parser.parse(raw)

        assert len(results) == 1
        r = results[0]
        assert r.target == "10.0.0.1"
        assert r.is_reachable is False


class TestPortNameConsistency:
    """Verify port names are consistent between mac_table and interface_status.

    This is critical: ClientCollectionService joins on exact match of
    (switch_hostname, interface_name). If names don't match, speed/duplex
    will be NULL.
    """

    def test_hpe_port_names_in_interface_status(self):
        from mock_server.generators.mac_table import _port_name
        from mock_server.generators.interface_status import _HPE_INTERFACES

        hpe_interface_names = {name for name, _ in _HPE_INTERFACES}
        for idx in range(1, 19):
            port = _port_name("hpe", idx)
            assert port in hpe_interface_names, (
                f"mac_table port {port} not in interface_status HPE interfaces"
            )

    def test_ios_port_names_in_interface_status(self):
        from mock_server.generators.mac_table import _port_name
        from mock_server.generators.interface_status import _IOS_INTERFACES

        ios_interface_names = {name for name, _ in _IOS_INTERFACES}
        for idx in range(1, 19):
            port = _port_name("ios", idx)
            assert port in ios_interface_names, (
                f"mac_table port {port} not in interface_status IOS interfaces"
            )

    def test_nxos_port_names_in_interface_status(self):
        from mock_server.generators.mac_table import _port_name
        from mock_server.generators.interface_status import _NXOS_INTERFACES

        nxos_interface_names = {name for name, _ in _NXOS_INTERFACES}
        for idx in range(1, 19):
            port = _port_name("nxos", idx)
            assert port in nxos_interface_names, (
                f"mac_table port {port} not in interface_status NXOS interfaces"
            )
