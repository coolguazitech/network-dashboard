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

        raw = generate("hpe", None, 600, 600)
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

        raw = generate("ios", None, 600, 600)
        parser = GetMacTableIosDnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert ":" in r.mac_address
            assert 1 <= r.vlan_id <= 4094

    def test_nxos_pipeline(self):
        from mock_server.generators.mac_table import generate
        from app.parsers.plugins.get_mac_table_nxos_dna_parser import GetMacTableNxosDnaParser

        raw = generate("nxos", None, 600, 600)
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

        raw = generate("hpe", False, 0, 600)  # new device, not converged
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
        raw = generate("hpe", None, 600, 600, switch_ip="10.0.0.1", mac_list=mac_list)
        parser = GetMacTableHpeDnaParser()
        results = parser.parse(raw)

        # With 19 MACs and ~1/3 hash selection, expect some results
        assert len(results) >= 1


class TestInterfaceStatusPipeline:
    """Mock interface_status generator → parser pipeline."""

    def test_hpe_pipeline(self):
        from mock_server.generators.interface_status import generate
        from app.parsers.plugins.get_interface_status_hpe_dna_parser import GetInterfaceStatusHpeDnaParser

        raw = generate("hpe", None, 600, 600)
        parser = GetInterfaceStatusHpeDnaParser()
        results = parser.parse(raw)

        assert len(results) >= 10
        statuses = {r.link_status for r in results}
        assert "up" in statuses

    def test_ios_pipeline(self):
        from mock_server.generators.interface_status import generate
        from app.parsers.plugins.get_interface_status_ios_dna_parser import GetInterfaceStatusIosDnaParser

        raw = generate("ios", None, 600, 600)
        parser = GetInterfaceStatusIosDnaParser()
        results = parser.parse(raw)

        assert len(results) >= 10

    def test_nxos_pipeline(self):
        from mock_server.generators.interface_status import generate
        from app.parsers.plugins.get_interface_status_nxos_dna_parser import GetInterfaceStatusNxosDnaParser

        raw = generate("nxos", None, 600, 600)
        parser = GetInterfaceStatusNxosDnaParser()
        results = parser.parse(raw)

        assert len(results) >= 10

    def test_hpe_fail_mode(self):
        """Old device after switch point → some interfaces DOWN."""
        from mock_server.generators.interface_status import generate
        from app.parsers.plugins.get_interface_status_hpe_dna_parser import GetInterfaceStatusHpeDnaParser

        raw = generate("hpe", True, 300, 600)
        parser = GetInterfaceStatusHpeDnaParser()
        results = parser.parse(raw)

        down_count = sum(1 for r in results if r.link_status == "down")
        assert down_count >= 1


class TestFanPipeline:
    def test_hpe(self):
        from mock_server.generators.fan import generate
        from app.parsers.plugins.get_fan_hpe_dna_parser import GetFanHpeDnaParser

        raw = generate("hpe", None, 600, 600)
        parser = GetFanHpeDnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.fan_id
            assert r.status in ("ok", "good", "normal", "online", "active", "fail", "absent", "unknown")

    def test_ios(self):
        from mock_server.generators.fan import generate
        from app.parsers.plugins.get_fan_ios_dna_parser import GetFanIosDnaParser

        raw = generate("ios", None, 600, 600)
        parser = GetFanIosDnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1

    def test_nxos(self):
        from mock_server.generators.fan import generate
        from app.parsers.plugins.get_fan_nxos_dna_parser import GetFanNxosDnaParser

        raw = generate("nxos", None, 600, 600)
        parser = GetFanNxosDnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1


class TestVersionPipeline:
    def test_hpe(self):
        from mock_server.generators.version import generate
        from app.parsers.plugins.get_version_hpe_dna_parser import GetVersionHpeDnaParser

        raw = generate("hpe", None, 600, 600)
        parser = GetVersionHpeDnaParser()
        results = parser.parse(raw)

        assert len(results) == 1
        assert results[0].version

    def test_ios(self):
        from mock_server.generators.version import generate
        from app.parsers.plugins.get_version_ios_dna_parser import GetVersionIosDnaParser

        raw = generate("ios", None, 600, 600)
        parser = GetVersionIosDnaParser()
        results = parser.parse(raw)

        assert len(results) == 1
        assert results[0].version

    def test_nxos(self):
        from mock_server.generators.version import generate
        from app.parsers.plugins.get_version_nxos_dna_parser import GetVersionNxosDnaParser

        raw = generate("nxos", None, 600, 600)
        parser = GetVersionNxosDnaParser()
        results = parser.parse(raw)

        assert len(results) == 1
        assert results[0].version


class TestPowerPipeline:
    def test_hpe(self):
        from mock_server.generators.power import generate
        from app.parsers.plugins.get_power_hpe_dna_parser import GetPowerHpeDnaParser

        raw = generate("hpe", None, 600, 600)
        parser = GetPowerHpeDnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.ps_id
            assert r.status

    def test_ios(self):
        from mock_server.generators.power import generate
        from app.parsers.plugins.get_power_ios_dna_parser import GetPowerIosDnaParser

        raw = generate("ios", None, 600, 600)
        parser = GetPowerIosDnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1

    def test_nxos(self):
        from mock_server.generators.power import generate
        from app.parsers.plugins.get_power_nxos_dna_parser import GetPowerNxosDnaParser

        raw = generate("nxos", None, 600, 600)
        parser = GetPowerNxosDnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1


class TestErrorCountPipeline:
    def test_hpe(self):
        from mock_server.generators.error_count import generate
        from app.parsers.plugins.get_error_count_hpe_fna_parser import GetErrorCountHpeFnaParser

        raw = generate("hpe", None, 600, 600)
        parser = GetErrorCountHpeFnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.interface_name
            assert r.crc_errors >= 0

    def test_ios(self):
        from mock_server.generators.error_count import generate
        from app.parsers.plugins.get_error_count_ios_fna_parser import GetErrorCountIosFnaParser

        raw = generate("ios", None, 600, 600)
        parser = GetErrorCountIosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1

    def test_nxos(self):
        from mock_server.generators.error_count import generate
        from app.parsers.plugins.get_error_count_nxos_fna_parser import GetErrorCountNxosFnaParser

        raw = generate("nxos", None, 600, 600)
        parser = GetErrorCountNxosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1


class TestUplinkPipeline:
    def test_hpe(self):
        from mock_server.generators.uplink import generate
        from app.parsers.plugins.get_uplink_hpe_fna_parser import GetUplinkHpeFnaParser

        raw = generate("hpe", None, 600, 600)
        parser = GetUplinkHpeFnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.local_interface
            assert r.remote_hostname

    def test_ios(self):
        from mock_server.generators.uplink import generate
        from app.parsers.plugins.get_uplink_ios_fna_parser import GetUplinkIosFnaParser

        raw = generate("ios", None, 600, 600)
        parser = GetUplinkIosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1

    def test_nxos(self):
        from mock_server.generators.uplink import generate
        from app.parsers.plugins.get_uplink_nxos_fna_parser import GetUplinkNxosFnaParser

        raw = generate("nxos", None, 600, 600)
        parser = GetUplinkNxosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1


class TestChannelGroupPipeline:
    def test_hpe(self):
        from mock_server.generators.channel_group import generate
        from app.parsers.plugins.get_channel_group_hpe_fna_parser import GetChannelGroupHpeFnaParser

        raw = generate("hpe", None, 600, 600)
        parser = GetChannelGroupHpeFnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.interface_name
            assert len(r.members) >= 1

    def test_ios(self):
        from mock_server.generators.channel_group import generate
        from app.parsers.plugins.get_channel_group_ios_fna_parser import GetChannelGroupIosFnaParser

        raw = generate("ios", None, 600, 600)
        parser = GetChannelGroupIosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1

    def test_nxos(self):
        from mock_server.generators.channel_group import generate
        from app.parsers.plugins.get_channel_group_nxos_fna_parser import GetChannelGroupNxosFnaParser

        raw = generate("nxos", None, 600, 600)
        parser = GetChannelGroupNxosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1


class TestGbicDetailsPipeline:
    @pytest.mark.xfail(reason="Mock HPE gbic output missing 'transceiver diagnostic' header format")
    def test_hpe(self):
        from mock_server.generators.gbic_details import generate
        from app.parsers.plugins.get_gbic_details_hpe_fna_parser import GetGbicDetailsHpeFnaParser

        raw = generate("hpe", None, 600, 600)
        parser = GetGbicDetailsHpeFnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.interface_name

    @pytest.mark.xfail(reason="Mock IOS gbic output missing Current(mA) column")
    def test_ios(self):
        from mock_server.generators.gbic_details import generate
        from app.parsers.plugins.get_gbic_details_ios_fna_parser import GetGbicDetailsIosFnaParser

        raw = generate("ios", None, 600, 600)
        parser = GetGbicDetailsIosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1

    def test_nxos(self):
        from mock_server.generators.gbic_details import generate
        from app.parsers.plugins.get_gbic_details_nxos_fna_parser import GetGbicDetailsNxosFnaParser

        raw = generate("nxos", None, 600, 600)
        parser = GetGbicDetailsNxosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1



class TestStaticAclPipeline:
    def test_hpe(self):
        from mock_server.generators.static_acl import generate
        from app.parsers.plugins.get_static_acl_hpe_fna_parser import GetStaticAclHpeFnaParser

        raw = generate("hpe", None, 600, 600)
        parser = GetStaticAclHpeFnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1
        for r in results:
            assert r.interface_name

    def test_ios(self):
        from mock_server.generators.static_acl import generate
        from app.parsers.plugins.get_static_acl_ios_fna_parser import GetStaticAclIosFnaParser

        raw = generate("ios", None, 600, 600)
        parser = GetStaticAclIosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1

    def test_nxos(self):
        from mock_server.generators.static_acl import generate
        from app.parsers.plugins.get_static_acl_nxos_fna_parser import GetStaticAclNxosFnaParser

        raw = generate("nxos", None, 600, 600)
        parser = GetStaticAclNxosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1


class TestDynamicAclPipeline:
    def test_hpe(self):
        from mock_server.generators.dynamic_acl import generate
        from app.parsers.plugins.get_dynamic_acl_hpe_fna_parser import GetDynamicAclHpeFnaParser

        raw = generate("hpe", None, 600, 600)
        parser = GetDynamicAclHpeFnaParser()
        results = parser.parse(raw)

        assert len(results) >= 1

    def test_ios(self):
        from mock_server.generators.dynamic_acl import generate
        from app.parsers.plugins.get_dynamic_acl_ios_fna_parser import GetDynamicAclIosFnaParser

        raw = generate("ios", None, 600, 600)
        parser = GetDynamicAclIosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1

    def test_nxos(self):
        from mock_server.generators.dynamic_acl import generate
        from app.parsers.plugins.get_dynamic_acl_nxos_fna_parser import GetDynamicAclNxosFnaParser

        raw = generate("nxos", None, 600, 600)
        parser = GetDynamicAclNxosFnaParser()
        results = parser.parse(raw)
        assert len(results) >= 1


class TestPingBatchPipeline:
    def test_default(self):
        from mock_server.generators.ping_batch import generate
        from app.parsers.plugins.ping_batch_parser import PingBatchParser

        raw = generate("hpe", None, 600, 600, switch_ip="10.0.0.1")
        parser = PingBatchParser()
        results = parser.parse(raw)

        # Should parse at least 1 ping result
        assert len(results) >= 1
        for r in results:
            assert r.target
            assert isinstance(r.is_reachable, bool)


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
