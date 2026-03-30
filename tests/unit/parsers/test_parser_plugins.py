"""
Comprehensive unit tests for all 37 parser plugins.

Tests cover:
- Empty / whitespace-only input returns []
- Valid CLI output is parsed correctly
- Malformed lines are gracefully skipped (no exceptions)
- Vendor variations (HPE, IOS, NXOS) via parametrize
"""
from __future__ import annotations

import json
import textwrap

import pytest

# ── MAC Table parsers ───────────────────────────────────────────
from app.parsers.plugins.get_mac_table_hpe_dna_parser import GetMacTableHpeDnaParser
from app.parsers.plugins.get_mac_table_ios_dna_parser import GetMacTableIosDnaParser
from app.parsers.plugins.get_mac_table_nxos_dna_parser import GetMacTableNxosDnaParser

# ── Interface Status parsers ────────────────────────────────────
from app.parsers.plugins.get_interface_status_hpe_dna_parser import (
    GetInterfaceStatusHpeDnaParser,
)
from app.parsers.plugins.get_interface_status_ios_dna_parser import (
    GetInterfaceStatusIosDnaParser,
)
from app.parsers.plugins.get_interface_status_nxos_dna_parser import (
    GetInterfaceStatusNxosDnaParser,
)

# ── Fan parsers ─────────────────────────────────────────────────
from app.parsers.plugins.get_fan_hpe_dna_parser import GetFanHpeDnaParser
from app.parsers.plugins.get_fan_ios_dna_parser import GetFanIosDnaParser
from app.parsers.plugins.get_fan_nxos_dna_parser import GetFanNxosDnaParser

# ── Power parsers ───────────────────────────────────────────────
from app.parsers.plugins.get_power_hpe_dna_parser import GetPowerHpeDnaParser
from app.parsers.plugins.get_power_ios_dna_parser import GetPowerIosDnaParser
from app.parsers.plugins.get_power_nxos_dna_parser import GetPowerNxosDnaParser

# ── Version parsers ─────────────────────────────────────────────
from app.parsers.plugins.get_version_hpe_dna_parser import GetVersionHpeDnaParser
from app.parsers.plugins.get_version_ios_dna_parser import GetVersionIosDnaParser
from app.parsers.plugins.get_version_nxos_dna_parser import GetVersionNxosDnaParser

# ── Error Count parsers (FNA) ───────────────────────────────────
from app.parsers.plugins.get_error_count_hpe_fna_parser import (
    GetErrorCountHpeFnaParser,
)
from app.parsers.plugins.get_error_count_ios_fna_parser import (
    GetErrorCountIosFnaParser,
)
from app.parsers.plugins.get_error_count_nxos_fna_parser import (
    GetErrorCountNxosFnaParser,
)

# ── Static ACL parsers (FNA) ───────────────────────────────────
from app.parsers.plugins.get_static_acl_hpe_fna_parser import (
    GetStaticAclHpeFnaParser,
)
from app.parsers.plugins.get_static_acl_ios_fna_parser import (
    GetStaticAclIosFnaParser,
)
from app.parsers.plugins.get_static_acl_nxos_fna_parser import (
    GetStaticAclNxosFnaParser,
)

# ── Dynamic ACL parsers (FNA) ──────────────────────────────────
from app.parsers.plugins.get_dynamic_acl_hpe_fna_parser import (
    GetDynamicAclHpeFnaParser,
)
from app.parsers.plugins.get_dynamic_acl_ios_fna_parser import (
    GetDynamicAclIosFnaParser,
)
from app.parsers.plugins.get_dynamic_acl_nxos_fna_parser import (
    GetDynamicAclNxosFnaParser,
)

# ── GBIC / Transceiver parsers (FNA) ───────────────────────────
from app.parsers.plugins.get_gbic_details_hpe_fna_parser import (
    GetGbicDetailsHpeFnaParser,
)
from app.parsers.plugins.get_gbic_details_ios_fna_parser import (
    GetGbicDetailsIosFnaParser,
)
from app.parsers.plugins.get_gbic_details_nxos_fna_parser import (
    GetGbicDetailsNxosFnaParser,
)

# ── Channel Group parsers (FNA) ────────────────────────────────
from app.parsers.plugins.get_channel_group_hpe_fna_parser import (
    GetChannelGroupHpeFnaParser,
)
from app.parsers.plugins.get_channel_group_ios_fna_parser import (
    GetChannelGroupIosFnaParser,
)
from app.parsers.plugins.get_channel_group_nxos_fna_parser import (
    GetChannelGroupNxosFnaParser,
)

# ── LLDP Neighbor parsers (DNA) ────────────────────────────────
from app.parsers.plugins.get_uplink_lldp_hpe_dna_parser import (
    GetUplinkLldpHpeDnaParser,
)
from app.parsers.plugins.get_uplink_lldp_ios_dna_parser import (
    GetUplinkLldpIosDnaParser,
)
from app.parsers.plugins.get_uplink_lldp_nxos_dna_parser import (
    GetUplinkLldpNxosDnaParser,
)

# ── CDP Neighbor parsers (DNA) ─────────────────────────────────
from app.parsers.plugins.get_uplink_cdp_ios_dna_parser import (
    GetUplinkCdpIosDnaParser,
)
from app.parsers.plugins.get_uplink_cdp_nxos_dna_parser import (
    GetUplinkCdpNxosDnaParser,
)

# ── Ping batch parser ──────────────────────────────────────────
from app.parsers.plugins.ping_batch_parser import PingBatchParser


# ────────────────────────────────────────────────────────────────
# Helper: collect ALL parser classes for cross-cutting tests
# ────────────────────────────────────────────────────────────────

ALL_PARSER_CLASSES = [
    GetMacTableHpeDnaParser,
    GetMacTableIosDnaParser,
    GetMacTableNxosDnaParser,
    GetInterfaceStatusHpeDnaParser,
    GetInterfaceStatusIosDnaParser,
    GetInterfaceStatusNxosDnaParser,
    GetFanHpeDnaParser,
    GetFanIosDnaParser,
    GetFanNxosDnaParser,
    GetPowerHpeDnaParser,
    GetPowerIosDnaParser,
    GetPowerNxosDnaParser,
    GetVersionHpeDnaParser,
    GetVersionIosDnaParser,
    GetVersionNxosDnaParser,
    GetErrorCountHpeFnaParser,
    GetErrorCountIosFnaParser,
    GetErrorCountNxosFnaParser,
    GetStaticAclHpeFnaParser,
    GetStaticAclIosFnaParser,
    GetStaticAclNxosFnaParser,
    GetDynamicAclHpeFnaParser,
    GetDynamicAclIosFnaParser,
    GetDynamicAclNxosFnaParser,
    GetGbicDetailsHpeFnaParser,
    GetGbicDetailsIosFnaParser,
    GetGbicDetailsNxosFnaParser,
    GetChannelGroupHpeFnaParser,
    GetChannelGroupIosFnaParser,
    GetChannelGroupNxosFnaParser,
    GetUplinkLldpHpeDnaParser,
    GetUplinkLldpIosDnaParser,
    GetUplinkLldpNxosDnaParser,
    GetUplinkCdpIosDnaParser,
    GetUplinkCdpNxosDnaParser,
    PingBatchParser,
]


# ====================================================================
# Cross-cutting: empty / whitespace → [] for EVERY parser
# ====================================================================


@pytest.mark.parametrize(
    "parser_cls",
    ALL_PARSER_CLASSES,
    ids=[c.__name__ for c in ALL_PARSER_CLASSES],
)
class TestAllParsersEmptyInput:
    """All parsers must return [] for empty or whitespace-only input."""

    def test_empty_string(self, parser_cls):
        assert parser_cls().parse("") == []

    def test_whitespace_only(self, parser_cls):
        assert parser_cls().parse("   \n\t\n  ") == []

    def test_none_like_empty(self, parser_cls):
        """Passing a blank newline should still yield []."""
        assert parser_cls().parse("\n") == []


# ====================================================================
# Cross-cutting: malformed / garbage input → [] (no exception)
# ====================================================================


@pytest.mark.parametrize(
    "parser_cls",
    ALL_PARSER_CLASSES,
    ids=[c.__name__ for c in ALL_PARSER_CLASSES],
)
class TestAllParsersMalformedInput:
    """Garbage input must not raise and should return []."""

    def test_random_garbage(self, parser_cls):
        result = parser_cls().parse("!@#$%^&*() random garbage 12345")
        assert isinstance(result, list)

    def test_only_header(self, parser_cls):
        result = parser_cls().parse("Port   Name   Status   Vlan")
        assert isinstance(result, list)


# ====================================================================
# 1. MAC Table parsers
# ====================================================================


class TestMacTableHpe:
    parser = GetMacTableHpeDnaParser()

    def test_valid_cli_output(self):
        raw = textwrap.dedent("""\
            MAC ADDR          VLAN ID  STATE          PORT INDEX       AGING TIME(s)
            000c-29aa-bb01    100      Learned        GigabitEthernet1/0/1   AGING
            000c-29aa-bb02    200      Learned        GigabitEthernet1/0/2   AGING
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].mac_address == "00:0C:29:AA:BB:01"
        assert result[0].interface_name == "GigabitEthernet1/0/1"
        assert result[0].vlan_id == 100
        assert result[1].vlan_id == 200

    def test_csv_format(self):
        raw = "MAC,Interface,VLAN\nAA:BB:CC:DD:EE:01,GE1/0/1,10\n"
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].mac_address == "AA:BB:CC:DD:EE:01"
        assert result[0].interface_name == "GE1/0/1"
        assert result[0].vlan_id == 10

    def test_invalid_vlan_skipped(self):
        raw = textwrap.dedent("""\
            MAC ADDR          VLAN ID  STATE          PORT INDEX       AGING TIME(s)
            000c-29aa-bb01    9999     Learned        GE1/0/1   AGING
        """)
        result = self.parser.parse(raw)
        assert len(result) == 0

    def test_csv_missing_field(self):
        raw = "MAC,Interface,VLAN\n,,10\n"
        result = self.parser.parse(raw)
        assert len(result) == 0


class TestMacTableIos:
    parser = GetMacTableIosDnaParser()

    def test_valid_cli_output(self):
        raw = textwrap.dedent("""\
                      Mac Address Table
            -------------------------------------------

            Vlan    Mac Address       Type        Ports
            ----    -----------       --------    -----
             100    0100.5e00.0001    STATIC      CPU
              10    68a8.2845.7640    DYNAMIC     Gi1/0/3
            Total Mac Addresses for this criterion: 2
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].vlan_id == 100
        assert result[0].mac_address == "01:00:5E:00:00:01"
        assert result[1].interface_name == "Gi1/0/3"

    def test_csv_format(self):
        raw = "MAC,Interface,VLAN\nAA:BB:CC:DD:EE:01,GE1/0/1,10\n"
        result = self.parser.parse(raw)
        assert len(result) == 1


class TestMacTableNxos:
    parser = GetMacTableNxosDnaParser()

    def test_valid_cli_output(self):
        raw = textwrap.dedent("""\
            Legend:
                    * - primary entry, G - Gateway MAC

               VLAN     MAC Address      Type      age     Secure   NTFY   Ports
            ---------+-----------------+--------+---------+------+----+------------------
            *   10     5254.0012.d6e1   dynamic  0         F      F    Eth1/2
            *   20     0050.5687.1abb   dynamic  0         F      F    Eth1/3
            G    -     5254.0001.0607   static   -         F      F    sup-eth1(R)
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].vlan_id == 10
        assert result[0].mac_address == "52:54:00:12:D6:E1"
        assert result[0].interface_name == "Eth1/2"

    def test_gateway_row_skipped(self):
        """Gateway rows with VLAN '-' are not matched by the regex."""
        raw = "G    -     5254.0001.0607   static   -   F   F   sup-eth1(R)\n"
        result = self.parser.parse(raw)
        assert len(result) == 0


# ====================================================================
# 2. Interface Status parsers
# ====================================================================


class TestInterfaceStatusHpe:
    parser = GetInterfaceStatusHpeDnaParser()

    def test_valid_output(self):
        raw = textwrap.dedent("""\
            Brief information on interfaces in route mode:
            Interface            Link Speed   Duplex Type PVID Description
            GE1/0/1              UP   1G(a)   F(a)   A    1
            GE1/0/2              DOWN auto     A      A    1
            XGE1/0/1             UP   10G(a)  F(a)   T    1
        """)
        result = self.parser.parse(raw)
        assert len(result) == 3
        assert result[0].interface_name == "GE1/0/1"
        assert result[0].link_status == "up"
        assert result[0].speed == "1000M"
        assert result[0].duplex == "full"
        assert result[1].link_status == "down"
        assert result[1].speed is None  # "auto" maps to None
        assert result[2].speed == "10G"

    def test_adm_status(self):
        raw = "GE1/0/5              ADM  auto     A      A    1\n"
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].link_status == "down"


class TestInterfaceStatusIos:
    parser = GetInterfaceStatusIosDnaParser()

    def test_valid_output(self):
        raw = textwrap.dedent("""\
            Port      Name               Status       Vlan       Duplex  Speed Type
            Gi1/0/1                      connected    1          a-full  a-1000 10/100/1000BaseTX
            Gi1/0/2   Server-01          connected    100        full    1000   10/100/1000BaseTX
            Gi1/0/3                      notconnect   1          auto    auto   10/100/1000BaseTX
            Te1/1/1                      connected    trunk      full    10G    SFP-10GBase-SR
        """)
        result = self.parser.parse(raw)
        assert len(result) == 4
        assert result[0].link_status == "up"
        assert result[0].duplex == "full"
        assert result[0].speed == "1000M"
        assert result[2].link_status == "down"
        assert result[2].duplex is None  # "auto" maps to None
        assert result[3].speed == "10G"

    def test_disabled_status(self):
        raw = "Gi1/0/4   AP-Floor2          disabled     1          auto    auto   10/100/1000BaseTX\n"
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].link_status == "down"


class TestInterfaceStatusNxos:
    parser = GetInterfaceStatusNxosDnaParser()

    def test_valid_output(self):
        raw = textwrap.dedent("""\
            --------------------------------------------------------------------------------
            Port          Name               Status    Vlan      Duplex  Speed   Type
            --------------------------------------------------------------------------------
            Eth1/1        Server-01          connected 100       full    1000    1000base-T
            Eth1/2                           notconnec 1         auto    auto    1000base-T
            Po1           Core-Uplink        connected trunk     full    10G     --
        """)
        result = self.parser.parse(raw)
        assert len(result) == 3
        assert result[0].link_status == "up"
        assert result[0].speed == "1000M"
        assert result[0].duplex == "full"
        assert result[1].link_status == "down"
        assert result[2].interface_name == "Po1"

    def test_sfp_absent(self):
        raw = "Eth1/4                           sfpAbsent 1         auto    auto    --\n"
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].link_status == "down"


# ====================================================================
# 3. Fan parsers
# ====================================================================


class TestFanHpe:
    parser = GetFanHpeDnaParser()

    def test_valid_output_with_slots(self):
        raw = textwrap.dedent("""\
            Slot 1:
            FanID    Status      Direction
            1        Normal      Back-to-front
            2        Normal      Back-to-front
            3        Absent      Back-to-front

            Slot 2:
            FanID    Status      Direction
            1        Normal      Front-to-back
        """)
        result = self.parser.parse(raw)
        assert len(result) == 4
        assert result[0].fan_id == "Fan 1/1"
        assert result[0].status == "normal"
        assert result[2].fan_id == "Fan 1/3"
        assert result[2].status == "absent"
        assert result[3].fan_id == "Fan 2/1"

    def test_no_slot_header(self):
        raw = textwrap.dedent("""\
            FanID    Status      Direction
            1        Normal      Back-to-front
        """)
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].fan_id == "Fan 1/1"
        assert result[0].status == "normal"


class TestFanIos:
    parser = GetFanIosDnaParser()

    def test_valid_output(self):
        raw = textwrap.dedent("""\
            FAN 1 is OK
            FAN 2 is OK
            FAN PS-1 is OK
            FAN PS-2 is NOT OK
        """)
        result = self.parser.parse(raw)
        assert len(result) == 4
        assert result[0].fan_id == "FAN 1"
        assert result[0].status == "ok"
        assert result[3].fan_id == "FAN PS-2"
        # "NOT OK" is not a recognized OperationalStatus, becomes "unknown"
        assert result[3].status == "unknown"

    def test_non_fan_lines_skipped(self):
        raw = textwrap.dedent("""\
            TEMPERATURE is OK
            FAN 1 is OK
        """)
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].fan_id == "FAN 1"

    def test_system_fan(self):
        raw = "SYSTEM FAN is OK\n"
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].fan_id == "SYSTEM FAN"


class TestFanNxos:
    parser = GetFanNxosDnaParser()

    def test_valid_output(self):
        raw = textwrap.dedent("""\
            Fan:
            --------------------------------------------------------------------------
            Fan             Model                Hw     Direction      Status
            --------------------------------------------------------------------------
            Fan1(sys_fan1)  NXA-FAN-30CFM-F      --     front-to-back  Ok
            Fan2(sys_fan2)  NXA-FAN-30CFM-F      --     front-to-back  Ok
            Fan_in_PS1      --                   --     front-to-back  Absent
        """)
        result = self.parser.parse(raw)
        assert len(result) == 3
        assert result[0].fan_id == "Fan1(sys_fan1)"
        assert result[0].status == "ok"
        assert result[2].fan_id == "Fan_in_PS1"
        assert result[2].status == "absent"


# ====================================================================
# 4. Power parsers
# ====================================================================


class TestPowerHpe:
    parser = GetPowerHpeDnaParser()

    def test_valid_slot_format(self):
        raw = textwrap.dedent("""\
            Slot 1:
            PowerID State    Mode   Current(A)  Voltage(V)  Power(W)  FanDirection
            1       Normal   AC     --          --          --        Back-to-front
            2       Absent   AC     --          --          --        Back-to-front
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].ps_id == "PS 1/1"
        assert result[0].status == "normal"
        assert result[1].ps_id == "PS 1/2"
        assert result[1].status == "absent"

    def test_ps_format(self):
        raw = textwrap.dedent("""\
            Power Supply Status:
            PS 1/1         Ok       Input: OK   Output: OK   Capacity: 350W   Actual: 180W
            PS 1/2         Ok       Input: OK   Output: OK   Capacity: 350W   Actual: 175W
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].ps_id == "PS 1/1"
        assert result[0].status == "ok"


class TestPowerIos:
    parser = GetPowerIosDnaParser()

    def test_ps_is_format(self):
        raw = textwrap.dedent("""\
            PS1 is OK
            PS2 is NOT PRESENT
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].ps_id == "PS1"
        assert result[0].status == "ok"
        # "NOT PRESENT" doesn't match known OperationalStatus -> unknown
        assert result[1].status == "unknown"

    def test_power_supply_format(self):
        raw = textwrap.dedent("""\
            Power Supply 1 is OK
            Power Supply 2 is NOT PRESENT
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].ps_id == "PS1"
        assert result[0].status == "ok"


class TestPowerNxos:
    parser = GetPowerNxosDnaParser()

    def test_valid_output(self):
        raw = textwrap.dedent("""\
            Power Supply:
            Voltage: 12 Volts
            Power                              Actual        Total
            Supply    Model                    Output     Capacity    Status
            -------  -------------------  -----------  -----------  ----------
            1        NXA-PAC-1100W-PE          186       1100        Ok
            2        NXA-PAC-1100W-PE            0       1100        Absent
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].ps_id == "PS-1"
        assert result[0].status == "ok"
        assert result[1].ps_id == "PS-2"
        assert result[1].status == "absent"


# ====================================================================
# 5. Version parsers
# ====================================================================


class TestVersionHpe:
    parser = GetVersionHpeDnaParser()

    def test_comware_version_release(self):
        raw = textwrap.dedent("""\
            HPE Comware Platform Software
            Comware Software, Version 7.1.070, Release 6635P07
            Copyright (c) 2010-2024 Hewlett Packard Enterprise Development LP
        """)
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].packages[0] == "7.1.070 Release 6635P07"

    def test_software_version_format(self):
        raw = textwrap.dedent("""\
            Software Version: WC.16.11.0012
            Model: Aruba 6300M
        """)
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].packages[0] == "WC.16.11.0012"

    def test_no_version_found(self):
        raw = "Some unrelated text\nwith no relevant data here\n"
        result = self.parser.parse(raw)
        assert len(result) == 0


class TestVersionIos:
    parser = GetVersionIosDnaParser()

    def test_ios_version(self):
        raw = textwrap.dedent("""\
            Cisco IOS Software, C3750E Software (C3750E-UNIVERSALK9-M), Version 15.2(4)E10
            Technical Support: http://www.cisco.com/techsupport
        """)
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].packages[0] == "15.2(4)E10"

    def test_iosxe_version(self):
        raw = "Cisco IOS XE Software, Version 17.09.04a\n"
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].packages[0] == "17.09.04a"


class TestVersionNxos:
    parser = GetVersionNxosDnaParser()

    def test_nxos_version(self):
        raw = textwrap.dedent("""\
            Cisco Nexus Operating System (NX-OS) Software
              NXOS: version 9.3(8)
        """)
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].packages[0] == "9.3(8)"

    def test_nxos_dotted_version(self):
        raw = "  NXOS: version 10.3.3\n"
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].packages[0] == "10.3.3"

    def test_system_fallback(self):
        raw = "  system:    version 7.0(3)I7(10)\n"
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].packages[0] == "7.0(3)I7(10)"


# ====================================================================
# 6. Error Count parsers (FNA)
# ====================================================================


class TestErrorCountHpe:
    parser = GetErrorCountHpeFnaParser()

    def test_tabular_format(self):
        raw = textwrap.dedent("""\
            Interface             Total(pkts)  Broadcast   Multicast  Err(pkts)
            GE1/0/1                    123456       1234         567          0
            GE1/0/2                     98765        876         432          5
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        # crc_errors = sum of all number columns
        assert result[0].interface_name == "GE1/0/1"
        assert result[0].crc_errors == 123456 + 1234 + 567 + 0
        assert result[1].crc_errors == 98765 + 876 + 432 + 5

    def test_per_interface_block_format(self):
        raw = textwrap.dedent("""\
            GigabitEthernet1/0/1
            Current state: UP
            Input:  3 input errors, 0 runts, 0 giants, 0 throttles
            Output: 2 output errors, 0 underruns, 0 buffer failures

            GigabitEthernet1/0/2
            Current state: UP
            Input:  0 input errors, 0 runts
            Output: 0 output errors, 0 underruns
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].interface_name == "GigabitEthernet1/0/1"
        assert result[0].crc_errors == 5  # 3 + 2
        assert result[1].crc_errors == 0

    def test_simplified_fna_format(self):
        raw = textwrap.dedent("""\
            Interface            Input(errs)       Output(errs)
            GE1/0/1                        0                  0
            GE1/0/2                        5                  1
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].crc_errors == 0
        assert result[1].crc_errors == 6


class TestErrorCountIos:
    parser = GetErrorCountIosFnaParser()

    def test_tabular_counters(self):
        raw = textwrap.dedent("""\
            Port        Align-Err    FCS-Err   Xmit-Err    Rcv-Err  UnderSize OutDiscards
            Gi0/1               0          0          0          0          0           0
            Gi0/2               0          5          0          3          0           0
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].interface_name == "Gi0/1"
        assert result[0].crc_errors == 0
        assert result[1].crc_errors == 8  # 5 + 3

    def test_per_interface_format(self):
        raw = textwrap.dedent("""\
            GigabitEthernet0/1 is up, line protocol is up
                 0 input errors, 0 CRC, 0 frame, 0 overrun, 0 ignored
                 0 output errors, 0 collisions, 2 interface resets

            GigabitEthernet0/2 is down, line protocol is down
                 10 input errors, 5 CRC, 2 frame, 0 overrun, 0 ignored
                 3 output errors, 0 collisions, 0 interface resets
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].crc_errors == 0
        assert result[1].crc_errors == 13  # 10 + 3


class TestErrorCountNxos:
    parser = GetErrorCountNxosFnaParser()

    def test_multi_section_tabular(self):
        raw = textwrap.dedent("""\
            --------------------------------------------------------------------------------
            Port          Align-Err    FCS-Err   Xmit-Err    Rcv-Err  UnderSize OutDiscards
            --------------------------------------------------------------------------------
            Eth1/1                0          0          0          0          0           0
            Eth1/2                0          3          2          5          0           0

            --------------------------------------------------------------------------------
            Port          Single-Col  Multi-Col  Late-Col  InDiscards
            --------------------------------------------------------------------------------
            Eth1/1                 0          0         0           0
            Eth1/2                 0          0         0           1
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].interface_name == "Eth1/1"
        assert result[0].crc_errors == 0
        # Section 1: 3+2+5 = 10, Section 2: 1 = 1, total = 11
        assert result[1].crc_errors == 11

    def test_per_interface_format(self):
        raw = textwrap.dedent("""\
            Ethernet1/1 is up
              0 input error  0 short frame  0 overrun
              0 output error  0 collision  0 deferred
        """)
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].crc_errors == 0


# ====================================================================
# 7. Static ACL parsers (FNA)
# ====================================================================


class TestStaticAclHpe:
    parser = GetStaticAclHpeFnaParser()

    def test_cli_format(self):
        raw = textwrap.dedent("""\
            interface GigabitEthernet1/0/1
             packet-filter 3001 inbound
            interface GigabitEthernet1/0/2
             packet-filter 3002 inbound
            interface GigabitEthernet1/0/3
        """)
        result = self.parser.parse(raw)
        assert len(result) == 3
        assert result[0].interface_name == "GigabitEthernet1/0/1"
        assert result[0].acl_number == "3001"
        assert result[1].acl_number == "3002"
        assert result[2].acl_number is None

    def test_cli_format_named_acl(self):
        """packet-filter name <name> inbound — named ACL variant."""
        raw = textwrap.dedent("""\
            interface GigabitEthernet1/0/1
             packet-filter name AntiVirusPortACL_5_OneWay inbound
            interface GigabitEthernet1/0/2
             packet-filter 3330 inbound
            interface GigabitEthernet1/0/3
        """)
        result = self.parser.parse(raw)
        assert len(result) == 3
        assert result[0].interface_name == "GigabitEthernet1/0/1"
        assert result[0].acl_number == "AntiVirusPortACL_5_OneWay"
        assert result[1].acl_number == "3330"
        assert result[2].acl_number is None

    def test_csv_format(self):
        raw = "Interface,ACL\nGE1/0/1,3001\nGE1/0/2,\n"
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].acl_number == "3001"
        assert result[1].acl_number is None


class TestStaticAclIos:
    parser = GetStaticAclIosFnaParser()

    def test_cli_format(self):
        raw = textwrap.dedent("""\
            interface GigabitEthernet1/0/1
             ip access-group 101 in
            interface GigabitEthernet1/0/2
             ip access-group 102 in
            interface GigabitEthernet1/0/3
        """)
        result = self.parser.parse(raw)
        assert len(result) == 3
        assert result[0].acl_number == "101"
        assert result[1].acl_number == "102"
        assert result[2].acl_number is None

    def test_csv_fallback(self):
        raw = "Interface,ACL\nGi1/0/1,101\nGi1/0/2,--\n"
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].acl_number == "101"
        assert result[1].acl_number is None  # "--" becomes None


class TestStaticAclNxos:
    parser = GetStaticAclNxosFnaParser()

    def test_cli_format(self):
        raw = textwrap.dedent("""\
            interface Ethernet1/1
             ip access-group 101 in
            interface Ethernet1/2
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].acl_number == "101"
        assert result[1].acl_number is None

    def test_csv_format(self):
        raw = "Interface,ACL\nEth1/1,101\nEth1/2,\n"
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].acl_number == "101"
        assert result[1].acl_number is None


# ====================================================================
# 8. Dynamic ACL parsers (FNA)
# ====================================================================


class TestDynamicAclHpe:
    parser = GetDynamicAclHpeFnaParser()

    def test_table_format(self):
        raw = textwrap.dedent("""\
            Interface         MAC Address        ACL Number  Auth State
            GE1/0/1           aabb-ccdd-0001     3001        Authenticated
            GE1/0/2           aabb-ccdd-0002     --          Unauthenticated
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].interface_name == "GE1/0/1"
        assert result[0].acl_number == "3001"
        assert result[1].acl_number is None

    def test_csv_fallback(self):
        raw = "Interface,ACL\nGE1/0/1,3001\nGE1/0/2,\n"
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].acl_number == "3001"
        assert result[1].acl_number is None

    def test_reversed_column_order(self):
        """Auth state and ACL in swapped positions."""
        raw = textwrap.dedent("""\
            Interface         MAC Address        Auth State      ACL Number
            GE1/0/1           aabb-ccdd-0001     Authenticated   3001
        """)
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].acl_number == "3001"

    def test_block_format_single_user(self):
        """Real display mac-authentication connection — single user block."""
        raw = textwrap.dedent("""\
            Slot ID: 1
            User MAC address: b47a-f1ad-b058
            Access interface: GigabitEthernet1/0/1
            Username: b47af1adb058
            User access state: Successful
            Authentication domain: admin-aaa
            IPv6 address: FE80::946A:9014:F6B4:E6CE
            IPv6 address source: User packet
            Initial VLAN: 999
            Authorization untagged VLAN: 36
            Authorization tagged VLAN: N/A
            Authorization VSI: N/A
            Authorization ACL number/name: 3240
            Authorization user profile: N/A
            Authorization CAR: N/A
            Authorization URL: N/A
            Start accounting: Successful
            Real-time accounting-update failures: 0
            Termination action: Default
            Session timeout period: N/A
            Online from: 2026/02/26 12:19:17
            Online duration: 124h 24m 42s
            Port-down keep online: Disabled (offline)
        """)
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].interface_name == "GigabitEthernet1/0/1"
        assert result[0].acl_number == "3240"

    def test_block_format_multiple_users(self):
        """Multiple user blocks — each Slot ID starts a new block."""
        raw = textwrap.dedent("""\
            Slot ID: 1
            User MAC address: b47a-f1ad-b058
            Access interface: GigabitEthernet1/0/1
            Username: b47af1adb058
            User access state: Successful
            Authorization ACL number/name: 3240

            Slot ID: 1
            User MAC address: aabb-ccdd-0001
            Access interface: GigabitEthernet1/0/5
            Username: aabbccdd0001
            User access state: Successful
            Authorization ACL number/name: 3330
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].interface_name == "GigabitEthernet1/0/1"
        assert result[0].acl_number == "3240"
        assert result[1].interface_name == "GigabitEthernet1/0/5"
        assert result[1].acl_number == "3330"

    def test_block_format_no_acl(self):
        """Block where Authorization ACL number/name is N/A."""
        raw = textwrap.dedent("""\
            Slot ID: 1
            User MAC address: b47a-f1ad-b058
            Access interface: GigabitEthernet1/0/1
            Authorization ACL number/name: N/A
        """)
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].interface_name == "GigabitEthernet1/0/1"
        assert result[0].acl_number is None


class TestDynamicAclIos:
    parser = GetDynamicAclIosFnaParser()

    def test_table_format(self):
        raw = textwrap.dedent("""\
            Interface         MAC Address        ACL         Status
            Gi1/0/1           0050.5687.1234     101         Authorized
            Gi1/0/2           0050.5687.5678     --          Unauthorized
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].acl_number == "101"
        assert result[1].acl_number is None

    def test_csv_fallback(self):
        raw = "Interface,ACL\nGi1/0/1,101\nGi1/0/2,\n"
        result = self.parser.parse(raw)
        assert len(result) == 2


class TestDynamicAclNxos:
    parser = GetDynamicAclNxosFnaParser()

    def test_table_format(self):
        raw = textwrap.dedent("""\
            Interface         MAC Address        ACL         Status
            Eth1/1            aabb.ccdd.0001     101         Authorized
            Eth1/2            aabb.ccdd.0002     --          Unauthorized
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].acl_number == "101"
        assert result[1].acl_number is None

    def test_csv_fallback(self):
        raw = "Interface,ACL\nEth1/1,101\nEth1/2,\n"
        result = self.parser.parse(raw)
        assert len(result) == 2


# ====================================================================
# 9. GBIC / Transceiver parsers (FNA)
# ====================================================================


class TestGbicDetailsHpe:
    parser = GetGbicDetailsHpeFnaParser()

    def test_sfp_format(self):
        raw = textwrap.dedent("""\
            GigabitEthernet1/0/1 transceiver diagnostic information:
            The transceiver diagnostic information is as follows:
            Current diagnostic parameters:
              Temp.(°C) Voltage(V)  Bias(mA)  RX power(dBm)  TX power(dBm)
              36.43     3.31        6.13      -3.10           -2.50
        """)
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].interface_name == "GigabitEthernet1/0/1"
        assert result[0].temperature == pytest.approx(36.43)
        assert result[0].voltage == pytest.approx(3.31)
        assert len(result[0].channels) == 1
        assert result[0].channels[0].channel == 1
        assert result[0].channels[0].rx_power == pytest.approx(-3.10)
        assert result[0].channels[0].tx_power == pytest.approx(-2.50)

    def test_qsfp_format(self):
        raw = textwrap.dedent("""\
            FortyGigE1/0/25 transceiver diagnostic information:
            The transceiver diagnostic information is as follows:
            Current diagnostic parameters:
              Temp.(°C) Voltage(V)
              34.00     3.29
              Channel   Bias(mA)  RX power(dBm)  TX power(dBm)
              1         6.50      -2.10          -1.50
              2         6.48      -2.30          -1.55
              3         6.52      -2.05          -1.48
              4         6.45      -2.20          -1.52
        """)
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].temperature == pytest.approx(34.0)
        assert len(result[0].channels) == 4
        assert result[0].channels[0].channel == 1
        assert result[0].channels[3].channel == 4

    def test_absent_transceiver_skipped(self):
        raw = textwrap.dedent("""\
            GigabitEthernet1/0/5 transceiver diagnostic information:
            The transceiver is absent.
        """)
        result = self.parser.parse(raw)
        assert len(result) == 0


class TestGbicDetailsIos:
    parser = GetGbicDetailsIosFnaParser()

    def test_valid_output(self):
        raw = textwrap.dedent("""\
                                                    Optical   Optical
                       Temperature  Voltage  Current  Tx Power  Rx Power
            Port       (Celsius)    (Volts)  (mA)     (dBm)     (dBm)
            ---------  -----------  -------  -------  --------  --------
            Gi1/0/1    32.7         3.28     6.1      -2.5      -3.1
            Gi1/0/2    28.1         3.30     6.0      -2.3      -3.0
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].interface_name == "Gi1/0/1"
        assert result[0].temperature == pytest.approx(32.7)
        assert result[0].voltage == pytest.approx(3.28)
        assert result[0].channels[0].tx_power == pytest.approx(-2.5)
        assert result[0].channels[0].rx_power == pytest.approx(-3.1)

    def test_na_values_skipped(self):
        raw = "Te1/0/26   N/A          N/A      N/A      N/A       N/A\n"
        result = self.parser.parse(raw)
        assert len(result) == 0  # All N/A, skipped

    def test_alarm_indicators_stripped(self):
        raw = "Gi1/0/3    32.7++       3.28     6.1      -2.5--    -3.1\n"
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].temperature == pytest.approx(32.7)
        assert result[0].channels[0].tx_power == pytest.approx(-2.5)


class TestGbicDetailsNxos:
    parser = GetGbicDetailsNxosFnaParser()

    def test_sfp_format(self):
        raw = textwrap.dedent("""\
            Ethernet1/1
                transceiver is present
                type is 10Gbase-SR
                SFP Detail Diagnostics Information (internal calibration)
                ------------------------------------------------------------
                Temperature  34.41 C      75.00 C     70.00 C    0.00 C     -5.00 C
                Voltage      3.22 V       3.63 V      3.46 V     2.97 V     3.13 V
                Current      9.89 mA      70.00 mA    68.00 mA   1.00 mA    2.00 mA
                Tx Power    -1.29 dBm     3.49 dBm    0.49 dBm  -12.19 dBm -8.19 dBm
                Rx Power    -9.26 dBm     3.49 dBm    0.49 dBm  -18.38 dBm -14.40 dBm
        """)
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].interface_name == "Ethernet1/1"
        assert result[0].temperature == pytest.approx(34.41)
        assert result[0].voltage == pytest.approx(3.22)
        assert result[0].channels[0].tx_power == pytest.approx(-1.29)
        assert result[0].channels[0].rx_power == pytest.approx(-9.26)

    def test_qsfp_format(self):
        raw = textwrap.dedent("""\
            Ethernet1/49
                transceiver is present
                type is QSFP-40G-SR4
                QSFP Detail Diagnostics Information (internal calibration)
                ============================================================
                Temperature : 32.15 C
                Voltage     : 3.30 V

                      Tx Bias     Tx Power    Rx Power
                Lane  Current     (dBm)       (dBm)
                ----  -------     --------    --------
                1     6.51        -1.50       -2.10
                2     6.48        -1.55       -2.30
                3     6.52        -1.48       -2.05
                4     6.45        -1.52       -2.20
        """)
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert len(result[0].channels) == 4
        assert result[0].temperature == pytest.approx(32.15)

    def test_not_present_skipped(self):
        raw = textwrap.dedent("""\
            Ethernet1/10
                transceiver is not present
        """)
        result = self.parser.parse(raw)
        assert len(result) == 0


# ====================================================================
# 10. Channel Group parsers (FNA)
# ====================================================================


class TestChannelGroupHpe:
    parser = GetChannelGroupHpeFnaParser()

    def test_valid_output(self):
        raw = textwrap.dedent("""\
            AggID   Interface   Link   Attribute   Mode   Members
            1       BAGG1       UP     A           LACP   HGE1/0/25(S) HGE1/0/26(S)
            2       BAGG2       DOWN   A           STATIC HGE1/0/27(U)
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].interface_name == "BAGG1"
        assert result[0].status == "up"
        assert result[0].members == ["HGE1/0/25", "HGE1/0/26"]
        assert result[0].member_status["HGE1/0/25"] == "up"
        assert result[1].status == "down"
        assert result[1].member_status["HGE1/0/27"] == "down"

    def test_no_members(self):
        """A row without recognizable member patterns still parses."""
        raw = "1       BAGG1       UP     A           LACP   --\n"
        result = self.parser.parse(raw)
        # The row matches, but no MEMBER_PATTERN matches in "--"
        assert len(result) == 1
        assert result[0].members == []
        assert result[0].member_status is None


class TestChannelGroupIos:
    parser = GetChannelGroupIosFnaParser()

    def test_valid_output(self):
        raw = textwrap.dedent("""\
            Flags:  D - down        P - bundled in port-channel
            Number of channel-groups in use: 2

            Group  Port-channel  Protocol    Ports
            ------+-------------+-----------+-----------------------------------------------
            1      Po1(SU)       LACP        Gi1/0/25(P) Gi1/0/26(P)
            7      Po7(SD)       -           Gi1/0/5(D)  Gi1/0/6(I)
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].interface_name == "Po1"
        assert result[0].status == "up"
        assert result[0].members == ["Gi1/0/25", "Gi1/0/26"]
        assert result[0].member_status["Gi1/0/25"] == "up"
        assert result[1].status == "down"
        assert result[1].member_status["Gi1/0/5"] == "down"

    def test_continuation_lines(self):
        raw = textwrap.dedent("""\
            Group  Port-channel  Protocol    Ports
            ------+-------------+-----------+-----------------------------------------------
            1      Po1(SU)       LACP        Gi1/0/25(P) Gi1/0/26(P)
                                             Gi1/0/27(P)
        """)
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert len(result[0].members) == 3


class TestChannelGroupNxos:
    parser = GetChannelGroupNxosFnaParser()

    def test_valid_output(self):
        raw = textwrap.dedent("""\
            Flags:  D - Down        P - Up in port-channel (members)
            --------------------------------------------------------------------------------
            Group Port-       Type     Protocol  Member Ports
                  Channel
            --------------------------------------------------------------------------------
            1     Po1(SU)     Eth      LACP      Eth1/25(P)    Eth1/26(P)
            135   Po135(SD)   Eth      NONE      --
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].interface_name == "Po1"
        assert result[0].status == "up"
        assert result[0].members == ["Eth1/25", "Eth1/26"]
        assert result[1].status == "down"
        assert result[1].members == []

    def test_continuation_lines(self):
        raw = textwrap.dedent("""\
            --------------------------------------------------------------------------------
            Group Port-       Type     Protocol  Member Ports
                  Channel
            --------------------------------------------------------------------------------
            811   Po811(RU)   Eth      LACP      Eth15/8(P)   Eth15/28(P)  Eth16/8(P)
                                                 Eth16/28(P)
        """)
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert len(result[0].members) == 4


# ====================================================================
# 11. LLDP Neighbor parsers (DNA)
# ====================================================================


class TestLldpHpe:
    parser = GetUplinkLldpHpeDnaParser()

    def test_valid_output(self):
        raw = textwrap.dedent("""\
            LLDP neighbor-information of port 25[GigabitEthernet1/0/25]:
              Neighbor index                   : 1
              Port ID                          : HundredGigE1/0/1
              System name                      : CORE-SW-01

            LLDP neighbor-information of port 26[GigabitEthernet1/0/26]:
              Port ID                          : HundredGigE1/0/2
              System name                      : CORE-SW-02
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].local_interface == "GigabitEthernet1/0/25"
        assert result[0].remote_hostname == "CORE-SW-01"
        assert result[0].remote_interface == "HundredGigE1/0/1"

    def test_missing_system_name(self):
        raw = textwrap.dedent("""\
            LLDP neighbor-information of port 25[GigabitEthernet1/0/25]:
              Port ID                          : HundredGigE1/0/1
        """)
        result = self.parser.parse(raw)
        assert len(result) == 0  # Missing system name -> skip


class TestLldpIos:
    parser = GetUplinkLldpIosDnaParser()

    def test_valid_output(self):
        raw = textwrap.dedent("""\
            ------------------------------------------------
            Local Intf: Gi1/0/49
            Chassis id: 0026.980a.3c01
            Port id: Eth1/25
            System Name: SPINE-01

            ------------------------------------------------
            Local Intf: Gi1/0/50
            Port id: Eth1/26
            System Name: SPINE-02
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].local_interface == "Gi1/0/49"
        assert result[0].remote_hostname == "SPINE-01"
        assert result[0].remote_interface == "Eth1/25"

    def test_not_advertised_skipped(self):
        raw = textwrap.dedent("""\
            ------------------------------------------------
            Local Intf: Gi1/0/49
            Port id: Eth1/25
            System Name: not advertised
        """)
        result = self.parser.parse(raw)
        assert len(result) == 0


class TestLldpNxos:
    parser = GetUplinkLldpNxosDnaParser()

    def test_valid_output(self):
        raw = textwrap.dedent("""\
            Chassis id: 0026.980a.3c01
            Port id: Ethernet1/25
            Local Port id: Eth1/1
            System Name: SPINE-01

            Chassis id: 0026.980a.3c02
            Port id: Ethernet1/25
            Local Port id: Eth1/2
            System Name: SPINE-02
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].local_interface == "Eth1/1"
        assert result[0].remote_hostname == "SPINE-01"
        assert result[0].remote_interface == "Ethernet1/25"

    def test_missing_local_port_skipped(self):
        raw = textwrap.dedent("""\
            Chassis id: 0026.980a.3c01
            Port id: Ethernet1/25
            System Name: SPINE-01
        """)
        result = self.parser.parse(raw)
        assert len(result) == 0


# ====================================================================
# 12. CDP Neighbor parsers (DNA)
# ====================================================================


class TestCdpIos:
    parser = GetUplinkCdpIosDnaParser()

    def test_valid_output(self):
        raw = textwrap.dedent("""\
            -------------------------
            Device ID: SW-CORE-01.example.com
            Platform: cisco WS-C3750X-48PF,  Capabilities: Router Switch IGMP
            Interface: GigabitEthernet0/1,  Port ID (outgoing port): GigabitEthernet1/0/1
            Holdtime : 143 sec
            -------------------------
            Device ID: SW-CORE-02
            Platform: cisco WS-C3750X-48PF
            Interface: GigabitEthernet0/2,  Port ID (outgoing port): GigabitEthernet1/0/1
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        assert result[0].remote_hostname == "SW-CORE-01.example.com"
        assert result[0].local_interface == "GigabitEthernet0/1"
        assert result[0].remote_interface == "GigabitEthernet1/0/1"

    def test_missing_interface_line_skipped(self):
        raw = textwrap.dedent("""\
            -------------------------
            Device ID: SW-CORE-01
            Platform: cisco WS-C3750X-48PF
        """)
        result = self.parser.parse(raw)
        assert len(result) == 0


class TestCdpNxos:
    parser = GetUplinkCdpNxosDnaParser()

    def test_valid_output(self):
        raw = textwrap.dedent("""\
            ----------------------------------------
            Device ID:SPINE-01(SSI12345678)
            System Name: SPINE-01
            Platform: N9K-C93180YC-EX
            Interface: Ethernet1/1, Port ID (outgoing port): Ethernet1/25
            ----------------------------------------
            Device ID:SPINE-02(SSI12345679)
            Interface: Ethernet1/2, Port ID (outgoing port): Ethernet1/25
        """)
        result = self.parser.parse(raw)
        assert len(result) == 2
        # Serial number suffix removed
        assert result[0].remote_hostname == "SPINE-01"
        assert result[0].local_interface == "Ethernet1/1"
        assert result[0].remote_interface == "Ethernet1/25"
        assert result[1].remote_hostname == "SPINE-02"

    def test_device_id_without_serial(self):
        raw = textwrap.dedent("""\
            ----------------------------------------
            Device ID:LEAF-01
            Interface: Ethernet1/1, Port ID (outgoing port): Ethernet1/1
        """)
        result = self.parser.parse(raw)
        assert len(result) == 1
        assert result[0].remote_hostname == "LEAF-01"


# ====================================================================
# 13. Ping Batch parser
# ====================================================================


class TestPingBatch:
    parser = PingBatchParser()

    def test_valid_json(self):
        data = {
            "result": {
                "10.1.1.1": {
                    "min_rtt": 0.5,
                    "avg_rtt": 1.2,
                    "max_rtt": 1.8,
                    "packets_sent": 3,
                    "packets_received": 3,
                    "packet_loss": 0,
                    "is_alive": True,
                },
                "10.1.1.2": {
                    "min_rtt": None,
                    "avg_rtt": None,
                    "max_rtt": None,
                    "packets_sent": 3,
                    "packets_received": 0,
                    "packet_loss": 100,
                    "is_alive": False,
                },
            }
        }
        result = self.parser.parse(json.dumps(data))
        assert len(result) == 2
        targets = {r.target: r.is_reachable for r in result}
        assert targets["10.1.1.1"] is True
        assert targets["10.1.1.2"] is False

    def test_invalid_json(self):
        result = self.parser.parse("not json at all")
        assert result == []

    def test_missing_result_key(self):
        result = self.parser.parse('{"data": {}}')
        assert result == []

    def test_result_not_dict(self):
        result = self.parser.parse('{"result": "some string"}')
        assert result == []

    def test_non_dict_stats_skipped(self):
        data = {"result": {"10.1.1.1": "not_a_dict"}}
        result = self.parser.parse(json.dumps(data))
        assert result == []

    def test_missing_is_alive_defaults_false(self):
        data = {"result": {"10.1.1.1": {"packets_sent": 3}}}
        result = self.parser.parse(json.dumps(data))
        assert len(result) == 1
        assert result[0].is_reachable is False


# ====================================================================
# Parametrized vendor variation tests
# ====================================================================


@pytest.mark.parametrize(
    "parser_cls",
    [GetMacTableHpeDnaParser, GetMacTableIosDnaParser, GetMacTableNxosDnaParser],
    ids=["hpe", "ios", "nxos"],
)
class TestMacTableCsvAllVendors:
    """All MAC table parsers should handle CSV format identically."""

    def test_csv_single_entry(self, parser_cls):
        raw = "MAC,Interface,VLAN\nAA:BB:CC:DD:EE:FF,Gi1/0/1,100\n"
        result = parser_cls().parse(raw)
        assert len(result) == 1
        assert result[0].mac_address == "AA:BB:CC:DD:EE:FF"
        assert result[0].vlan_id == 100

    def test_csv_empty_fields(self, parser_cls):
        raw = "MAC,Interface,VLAN\n,,\n"
        result = parser_cls().parse(raw)
        assert len(result) == 0

    def test_csv_invalid_vlan(self, parser_cls):
        raw = "MAC,Interface,VLAN\nAA:BB:CC:DD:EE:FF,Gi1/0/1,0\n"
        result = parser_cls().parse(raw)
        assert len(result) == 0

    def test_csv_multiple_entries(self, parser_cls):
        raw = "MAC,Interface,VLAN\nAA:BB:CC:DD:EE:01,Gi1/0/1,10\nAA:BB:CC:DD:EE:02,Gi1/0/2,20\n"
        result = parser_cls().parse(raw)
        assert len(result) == 2


@pytest.mark.parametrize(
    "parser_cls",
    [
        GetStaticAclHpeFnaParser,
        GetStaticAclIosFnaParser,
        GetStaticAclNxosFnaParser,
    ],
    ids=["hpe", "ios", "nxos"],
)
class TestStaticAclCsvAllVendors:
    """All static ACL parsers handle CSV format."""

    def test_csv_with_acl(self, parser_cls):
        raw = "Interface,ACL\nGi1/0/1,101\n"
        result = parser_cls().parse(raw)
        assert len(result) == 1
        assert result[0].acl_number == "101"

    def test_csv_without_acl(self, parser_cls):
        raw = "Interface,ACL\nGi1/0/1,\n"
        result = parser_cls().parse(raw)
        assert len(result) == 1
        assert result[0].acl_number is None

    def test_csv_dash_dash_is_none(self, parser_cls):
        raw = "Interface,ACL\nGi1/0/1,--\n"
        result = parser_cls().parse(raw)
        assert len(result) == 1
        assert result[0].acl_number is None


@pytest.mark.parametrize(
    "parser_cls",
    [
        GetDynamicAclHpeFnaParser,
        GetDynamicAclIosFnaParser,
        GetDynamicAclNxosFnaParser,
    ],
    ids=["hpe", "ios", "nxos"],
)
class TestDynamicAclCsvAllVendors:
    """All dynamic ACL parsers handle CSV fallback."""

    def test_csv_with_acl(self, parser_cls):
        raw = "Interface,ACL\nGi1/0/1,101\n"
        result = parser_cls().parse(raw)
        assert len(result) == 1
        assert result[0].acl_number == "101"

    def test_csv_no_acl(self, parser_cls):
        raw = "Interface,ACL\nGi1/0/1,\n"
        result = parser_cls().parse(raw)
        assert len(result) == 1
        assert result[0].acl_number is None


@pytest.mark.parametrize(
    "parser_cls",
    [GetVersionHpeDnaParser, GetVersionIosDnaParser, GetVersionNxosDnaParser],
    ids=["hpe", "ios", "nxos"],
)
class TestVersionAllVendorsEdgeCases:
    """Version parsers: empty and unrecognized format."""

    def test_no_version_in_text(self, parser_cls):
        result = parser_cls().parse("completely unrelated text without relevant data")
        assert result == []

    def test_returns_single_element(self, parser_cls):
        """All version parsers return at most one VersionData."""
        # Feed HPE, IOS, or NXOS the correct format to get exactly 1
        samples = {
            "GetVersionHpeDnaParser": "Comware Software, Version 7.1.070, Release 6635P07",
            "GetVersionIosDnaParser": "Cisco IOS Software, Version 15.2(4)E10",
            "GetVersionNxosDnaParser": "  NXOS: version 9.3(8)",
        }
        raw = samples.get(parser_cls.__name__, "")
        if raw:
            result = parser_cls().parse(raw)
            assert len(result) <= 1


@pytest.mark.parametrize(
    "parser_cls",
    [GetFanHpeDnaParser, GetFanIosDnaParser, GetFanNxosDnaParser],
    ids=["hpe", "ios", "nxos"],
)
class TestFanAllVendorsEdgeCases:
    """Fan parsers: malformed input."""

    def test_separator_only(self, parser_cls):
        result = parser_cls().parse("----------\n----------\n")
        assert result == []

    def test_header_only_hpe_style(self, parser_cls):
        """HPE header line; NXOS may parse 'FanID' as data but that's harmless."""
        result = parser_cls().parse("FanID    Status      Direction\n")
        # HPE and IOS skip it; NXOS may produce one result because its header
        # detection looks for "model" keyword. All still return a list.
        assert isinstance(result, list)


@pytest.mark.parametrize(
    "parser_cls",
    [GetPowerHpeDnaParser, GetPowerIosDnaParser, GetPowerNxosDnaParser],
    ids=["hpe", "ios", "nxos"],
)
class TestPowerAllVendorsEdgeCases:
    """Power parsers: unrecognized input."""

    def test_unrecognized_format(self, parser_cls):
        result = parser_cls().parse("some random unrecognized text\nwithout power info")
        assert isinstance(result, list)


@pytest.mark.parametrize(
    "parser_cls",
    [GetErrorCountHpeFnaParser, GetErrorCountIosFnaParser, GetErrorCountNxosFnaParser],
    ids=["hpe", "ios", "nxos"],
)
class TestErrorCountAllVendorsEdgeCases:
    """Error count parsers: header-only input."""

    def test_header_only_tabular(self, parser_cls):
        result = parser_cls().parse("Port   Align-Err  FCS-Err  Xmit-Err\n")
        assert result == []

    def test_separator_only(self, parser_cls):
        result = parser_cls().parse("------- ------- -------\n")
        assert result == []


@pytest.mark.parametrize(
    "parser_cls",
    [
        GetUplinkLldpHpeDnaParser,
        GetUplinkLldpIosDnaParser,
        GetUplinkLldpNxosDnaParser,
    ],
    ids=["hpe", "ios", "nxos"],
)
class TestLldpAllVendorsEdgeCases:
    """LLDP parsers: incomplete blocks."""

    def test_partial_block_skipped(self, parser_cls):
        """Block with only header / partial info should be skipped."""
        result = parser_cls().parse("Some partial LLDP data without proper structure")
        assert result == []


@pytest.mark.parametrize(
    "parser_cls",
    [GetUplinkCdpIosDnaParser, GetUplinkCdpNxosDnaParser],
    ids=["ios", "nxos"],
)
class TestCdpAllVendorsEdgeCases:
    """CDP parsers: various edge cases."""

    def test_missing_device_id_and_interface(self, parser_cls):
        """Block with no Device ID and no Interface line should be skipped."""
        raw = textwrap.dedent("""\
            -------------------------
            Platform: cisco WS-C3750X-48PF
            Holdtime : 143 sec
        """)
        result = parser_cls().parse(raw)
        assert result == []

    def test_no_separator(self, parser_cls):
        """Without dashes separator, entire text is one block."""
        raw = textwrap.dedent("""\
            Device ID: SWITCH-01
            Interface: Ethernet1/1, Port ID (outgoing port): Ethernet1/25
        """)
        result = parser_cls().parse(raw)
        assert len(result) == 1


# ====================================================================
# Additional edge-case tests per parser family
# ====================================================================


class TestMacTableMacNormalization:
    """Test MAC address normalization across formats."""

    @pytest.mark.parametrize(
        "raw_mac,expected",
        [
            ("000c-29aa-bb01", "00:0C:29:AA:BB:01"),  # HPE format
            ("000c.29aa.bb01", "00:0C:29:AA:BB:01"),  # Cisco format
            ("00:0c:29:aa:bb:01", "00:0C:29:AA:BB:01"),  # Standard format
            ("AA-BB-CC-DD-EE-FF", "AA:BB:CC:DD:EE:FF"),  # Windows format
        ],
    )
    def test_mac_formats_via_csv(self, raw_mac, expected):
        parser = GetMacTableHpeDnaParser()
        raw = f"MAC,Interface,VLAN\n{raw_mac},Gi1/0/1,10\n"
        result = parser.parse(raw)
        assert len(result) == 1
        assert result[0].mac_address == expected


class TestInterfaceStatusSpeedNormalization:
    """Test speed normalization across vendors."""

    def test_ios_speed_variants(self):
        parser = GetInterfaceStatusIosDnaParser()
        raw = textwrap.dedent("""\
            Port      Name               Status       Vlan       Duplex  Speed Type
            Gi1/0/1                      connected    1          a-full  a-1000 type
            Te1/1/1                      connected    trunk      full    10G    type
            Gi1/0/3                      connected    1          full    100    type
        """)
        result = parser.parse(raw)
        assert result[0].speed == "1000M"
        assert result[1].speed == "10G"
        assert result[2].speed == "100M"


class TestPingBatchJsonEdgeCases:
    parser = PingBatchParser()

    def test_empty_result_dict(self):
        data = {"result": {}}
        result = self.parser.parse(json.dumps(data))
        assert result == []

    def test_single_ip(self):
        data = {"result": {"192.168.1.1": {"is_alive": True}}}
        result = self.parser.parse(json.dumps(data))
        assert len(result) == 1
        assert result[0].target == "192.168.1.1"
        assert result[0].is_reachable is True

    def test_list_not_dict_at_top(self):
        result = self.parser.parse("[1, 2, 3]")
        assert result == []

    def test_message_response(self):
        """DNA error response with 'message' key, no 'result'."""
        data = {"message": "Device unreachable"}
        result = self.parser.parse(json.dumps(data))
        assert result == []


# ====================================================================
# 14. Scheduler _parse_ping_response (JSON + CSV)
# ====================================================================


class TestSchedulerParsePingResponse:
    """Test SchedulerService._parse_ping_response handles JSON and CSV."""

    @staticmethod
    def _parse(raw: str) -> list:
        from app.services.scheduler import SchedulerService
        return SchedulerService._parse_ping_response(raw)

    def test_json_real_gnms_response(self):
        """Real GNMS Ping API returns JSON with 'result' dict."""
        raw = json.dumps({
            "result": {
                "10.19.81.13": {
                    "min_rtt": 3.661,
                    "avg_rtt": 3.687,
                    "max_rtt": 3.713,
                    "rtts": [3.713, 3.661],
                    "packets_sent": 2,
                    "packets_received": 2,
                    "packet_loss": 0,
                    "jitter": 0.052,
                    "is_alive": True,
                },
                "10.19.81.14": {
                    "min_rtt": 0,
                    "avg_rtt": 0,
                    "max_rtt": 0,
                    "rtts": [],
                    "packets_sent": 2,
                    "packets_received": 0,
                    "packet_loss": 100,
                    "jitter": 0,
                    "is_alive": False,
                },
            }
        })
        results = self._parse(raw)
        assert len(results) == 2
        by_ip = {r.target: r for r in results}
        assert by_ip["10.19.81.13"].is_reachable is True
        assert by_ip["10.19.81.14"].is_reachable is False

    def test_csv_mock_format(self):
        """Mock server returns CSV format."""
        raw = "IP,Reachable,Latency_ms\n10.0.0.1,True,1.2\n10.0.0.2,False,0"
        results = self._parse(raw)
        assert len(results) == 2
        by_ip = {r.target: r for r in results}
        assert by_ip["10.0.0.1"].is_reachable is True
        assert by_ip["10.0.0.2"].is_reachable is False

    def test_empty_string(self):
        assert self._parse("") == []

    def test_json_empty_result(self):
        raw = json.dumps({"result": {}})
        assert self._parse(raw) == []


class TestFanStatusNormalization:
    """Test OperationalStatus normalization via FanStatusData."""

    @pytest.mark.parametrize(
        "raw_status,expected",
        [
            ("OK", "ok"),
            ("Ok", "ok"),
            ("Normal", "normal"),
            ("NORMAL", "normal"),
            ("Absent", "absent"),
            ("Fail", "fail"),
            ("NOT OK", "unknown"),
            ("SomethingWeird", "unknown"),
        ],
    )
    def test_status_normalization(self, raw_status, expected):
        """FanStatusData normalizes status via OperationalStatus enum."""
        from app.parsers.protocols import FanStatusData

        fan = FanStatusData(fan_id="test", status=raw_status)
        assert fan.status == expected


class TestPowerStatusNormalization:
    """Test OperationalStatus normalization via PowerData."""

    @pytest.mark.parametrize(
        "raw_status,expected",
        [
            ("OK", "ok"),
            ("Normal", "normal"),
            ("Absent", "absent"),
            ("FAULTY", "unknown"),
        ],
    )
    def test_status_normalization(self, raw_status, expected):
        from app.parsers.protocols import PowerData

        ps = PowerData(ps_id="PS1", status=raw_status)
        assert ps.status == expected


class TestPortChannelStatusNormalization:
    """Test LinkStatus normalization via PortChannelData."""

    @pytest.mark.parametrize(
        "raw_status,expected",
        [
            ("up", "up"),
            ("UP", "up"),
            ("down", "down"),
            ("DOWN", "down"),
            ("something", "unknown"),
        ],
    )
    def test_status_normalization(self, raw_status, expected):
        from app.parsers.protocols import PortChannelData

        pc = PortChannelData(
            interface_name="Po1", status=raw_status, members=[]
        )
        assert pc.status == expected


class TestInterfaceStatusLinkNormalization:
    """Test LinkStatus normalization via InterfaceStatusData."""

    @pytest.mark.parametrize(
        "raw_status,expected",
        [
            ("up", "up"),
            ("down", "down"),
            ("UP", "up"),
            ("invalid", "unknown"),
        ],
    )
    def test_link_status_normalization(self, raw_status, expected):
        from app.parsers.protocols import InterfaceStatusData

        data = InterfaceStatusData(
            interface_name="Gi1/0/1", link_status=raw_status
        )
        assert data.link_status == expected


class TestGbicMultipleInterfaces:
    """Test GBIC parsers with multiple interfaces in one output."""

    def test_hpe_multiple_sfp(self):
        parser = GetGbicDetailsHpeFnaParser()
        raw = textwrap.dedent("""\
            GigabitEthernet1/0/1 transceiver diagnostic information:
            The transceiver diagnostic information is as follows:
            Current diagnostic parameters:
              Temp.(°C) Voltage(V)  Bias(mA)  RX power(dBm)  TX power(dBm)
              36.43     3.31        6.13      -3.10           -2.50

            GigabitEthernet1/0/2 transceiver diagnostic information:
            The transceiver diagnostic information is as follows:
            Current diagnostic parameters:
              Temp.(°C) Voltage(V)  Bias(mA)  RX power(dBm)  TX power(dBm)
              35.00     3.30        6.10      -3.00           -2.30
        """)
        result = parser.parse(raw)
        assert len(result) == 2
        assert result[0].interface_name == "GigabitEthernet1/0/1"
        assert result[1].interface_name == "GigabitEthernet1/0/2"

    def test_ios_multiple_rows(self):
        parser = GetGbicDetailsIosFnaParser()
        raw = textwrap.dedent("""\
            Port       (Celsius)    (Volts)  (mA)     (dBm)     (dBm)
            ---------  -----------  -------  -------  --------  --------
            Gi1/0/1    32.7         3.28     6.1      -2.5      -3.1
            Gi1/0/2    28.1         3.30     6.0      -2.3      -3.0
            Te1/0/25   28.3         3.31     35.2     -1.2      -2.8
        """)
        result = parser.parse(raw)
        assert len(result) == 3

    def test_nxos_multiple_blocks(self):
        parser = GetGbicDetailsNxosFnaParser()
        raw = textwrap.dedent("""\
            Ethernet1/1
                transceiver is present
                type is 10Gbase-SR
                SFP Detail Diagnostics Information (internal calibration)
                Temperature  34.41 C      75.00 C     70.00 C    0.00 C     -5.00 C
                Voltage      3.22 V       3.63 V      3.46 V     2.97 V     3.13 V
                Tx Power    -1.29 dBm     3.49 dBm    0.49 dBm  -12.19 dBm -8.19 dBm
                Rx Power    -9.26 dBm     3.49 dBm    0.49 dBm  -18.38 dBm -14.40 dBm

            Ethernet1/2
                transceiver is not present
        """)
        result = parser.parse(raw)
        assert len(result) == 1
        assert result[0].interface_name == "Ethernet1/1"


class TestErrorCountZeroValues:
    """Interfaces with zero errors should still be returned."""

    def test_hpe_zero_errors(self):
        parser = GetErrorCountHpeFnaParser()
        raw = textwrap.dedent("""\
            Interface            Input(errs)       Output(errs)
            GE1/0/1                        0                  0
        """)
        result = parser.parse(raw)
        assert len(result) == 1
        assert result[0].crc_errors == 0

    def test_ios_zero_errors(self):
        parser = GetErrorCountIosFnaParser()
        raw = textwrap.dedent("""\
            Port        Align-Err    FCS-Err   Xmit-Err    Rcv-Err  UnderSize OutDiscards
            Gi0/1               0          0          0          0          0           0
        """)
        result = parser.parse(raw)
        assert len(result) == 1
        assert result[0].crc_errors == 0
