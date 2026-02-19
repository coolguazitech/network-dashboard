#!/usr/bin/env python3
"""
Generate realistic CLI test data for all parsers.

Creates test_data/raw/{api}_{device_type}_{ip}.txt files with proper CLI text
that parsers can actually parse (not JSON placeholders).

Usage:
    python scripts/generate_test_data.py [--no-clean]
"""
from __future__ import annotations

import sys
from pathlib import Path

RAW_DIR = Path("test_data/raw")

# ─── IP addresses per device type ───────────────────────────────────
HPE_IPS = ["10.10.1.1", "10.10.1.2"]
IOS_IPS = ["10.10.2.1", "10.10.2.2"]
NXOS_IPS = ["10.10.3.1", "10.10.3.2"]


# =====================================================================
#  FAN
# =====================================================================
FAN_HPE = {
    HPE_IPS[0]: """\
Slot 1:
FanID    Status      Direction
1        Normal      Back-to-front
2        Normal      Back-to-front
3        Normal      Back-to-front
4        Normal      Back-to-front

Slot 2:
FanID    Status      Direction
1        Normal      Front-to-back
2        Normal      Front-to-back
""",
    HPE_IPS[1]: """\
Slot 1:
FanID    Status      Direction
1        Normal      Back-to-front
2        Normal      Back-to-front
3        Absent      Back-to-front
""",
}

FAN_IOS = {
    IOS_IPS[0]: """\
FAN 1 is OK
FAN 2 is OK
FAN PS-1 is OK
FAN PS-2 is OK
SYSTEM FAN is OK
""",
    IOS_IPS[1]: """\
FAN 1 is OK
FAN 2 is OK
FAN PS-1 is NOT OK
FAN PS-2 is OK
""",
}

FAN_NXOS = {
    NXOS_IPS[0]: """\
Fan:
--------------------------------------------------------------------------
Fan             Model                Hw     Direction      Status
--------------------------------------------------------------------------
Fan1(sys_fan1)  NXA-FAN-30CFM-F      --     front-to-back  Ok
Fan2(sys_fan2)  NXA-FAN-30CFM-F      --     front-to-back  Ok
Fan3(sys_fan3)  NXA-FAN-30CFM-F      --     front-to-back  Ok
Fan_in_PS1      --                   --     front-to-back  Ok
Fan_in_PS2      --                   --     front-to-back  Ok
""",
    NXOS_IPS[1]: """\
Fan:
--------------------------------------------------------------------------
Fan             Model                Hw     Direction      Status
--------------------------------------------------------------------------
Fan1(sys_fan1)  NXA-FAN-30CFM-F      --     front-to-back  Ok
Fan2(sys_fan2)  NXA-FAN-30CFM-F      --     front-to-back  Ok
Fan_in_PS1      --                   --     front-to-back  Ok
Fan_in_PS2      --                   --     front-to-back  Absent
""",
}


# =====================================================================
#  POWER
# =====================================================================
POWER_HPE = {
    HPE_IPS[0]: """\
Slot 1:
PowerID State    Mode   Current(A)  Voltage(V)  Power(W)  FanDirection
1       Normal   AC     1.2         12.0        150       Back-to-front
2       Normal   AC     1.1         12.0        145       Back-to-front

Slot 2:
PowerID State    Mode   Current(A)  Voltage(V)  Power(W)  FanDirection
1       Normal   AC     1.3         12.0        155       Back-to-front
""",
    HPE_IPS[1]: """\
Slot 1:
PowerID State    Mode   Current(A)  Voltage(V)  Power(W)  FanDirection
1       Normal   AC     1.2         12.0        150       Back-to-front
2       Absent   AC     --          --          --        Back-to-front
""",
}

POWER_IOS = {
    IOS_IPS[0]: """\
PS1 is OK
PS2 is OK
""",
    IOS_IPS[1]: """\
PS1 is OK
PS2 is NOT PRESENT
""",
}

POWER_NXOS = {
    NXOS_IPS[0]: """\
Power Supply:
Voltage: 12 Volts
Power                              Actual        Total
Supply    Model                    Output     Capacity    Status
-------  -------------------  -----------  -----------  ----------
1        NXA-PAC-1100W-PE          186 W      1100 W     Ok
2        NXA-PAC-1100W-PE          180 W      1100 W     Ok

                                 Actual        Power
Module    Model                  Draw       Allocated    Status
-------  -------------------  -----------  -----------  ----------
1        N9K-C93180YC-FX       117.84 W    252.00 W     Powered-Up
""",
    NXOS_IPS[1]: """\
Power Supply:
Voltage: 12 Volts
Power                              Actual        Total
Supply    Model                    Output     Capacity    Status
-------  -------------------  -----------  -----------  ----------
1        NXA-PAC-1100W-PE          186 W      1100 W     Ok
2        NXA-PAC-1100W-PE            0 W      1100 W     Absent
""",
}


# =====================================================================
#  VERSION
# =====================================================================
VERSION_HPE = {
    HPE_IPS[0]: """\
HPE Comware Platform Software
Comware Software, Version 7.1.070, Release 6635P07
Copyright (c) 2010-2024 Hewlett Packard Enterprise Development LP
HPE FF 5710 48SFP+ 6QS 2SL Switch
Uptime is 0 weeks, 1 day, 3 hours, 22 minutes
 CPU     #0 99% idle
Serial Number : CN12345678

Slot 1:
Uptime is 0 weeks, 1 day, 3 hours, 22 minutes
HPE FF 5710 48SFP+ 6QS 2SL Switch  with 1 Processor
4096M    bytes SDRAM
""",
    HPE_IPS[1]: """\
HPE Comware Platform Software
Comware Software, Version 7.1.070, Release 6635P07
Copyright (c) 2010-2024 Hewlett Packard Enterprise Development LP
HPE FF 5710 24SFP+ 6QS 2SL Switch
Uptime is 2 weeks, 3 days, 12 hours, 45 minutes
Serial Number : CN98765432
""",
}

VERSION_IOS = {
    IOS_IPS[0]: """\
Cisco IOS Software, C3750E Software (C3750E-UNIVERSALK9-M), Version 15.2(4)E10
Technical Support: http://www.cisco.com/techsupport
Copyright (c) 1986-2020 by Cisco Systems, Inc.

ROM: Bootstrap program is C3750E boot loader
BOOTLDR: C3750E Boot Loader Version 12.2(58r)SE

SW-ACCESS-01 uptime is 30 weeks, 2 days, 14 hours, 5 minutes
System returned to ROM by power-on

System image file is "flash:c3750e-universalk9-mz.152-4.E10.bin"

Model number          : WS-C3750X-48PF-L
System serial number  : FDO1234A5BC
""",
    IOS_IPS[1]: """\
Cisco IOS Software, C3750E Software (C3750E-UNIVERSALK9-M), Version 15.2(4)E10
Technical Support: http://www.cisco.com/techsupport
Copyright (c) 1986-2020 by Cisco Systems, Inc.

SW-ACCESS-02 uptime is 15 weeks, 1 day, 8 hours, 30 minutes

Model number          : WS-C3750X-24PF-L
System serial number  : FDO5678B9DE
""",
}

VERSION_NXOS = {
    NXOS_IPS[0]: """\
Cisco Nexus Operating System (NX-OS) Software
TAC support: http://www.cisco.com/tac
Documents: http://www.cisco.com/en/US/products/ps9372/tsd_products_support_series_home.html
Copyright (c) 2002-2022, Cisco Systems, Inc. All rights reserved.
The copyrights to certain works contained herein are owned by
other third parties and are used and distributed under license.

Software
  BIOS: version 07.69
  NXOS: version 9.3(8)
  BIOS compile time:  08/04/2020
  NXOS compile time:  2/8/2022 17:00:00

Hardware
  cisco Nexus9000 C93180YC-FX Chassis
  Intel(R) Xeon(R) CPU D-1528 @ 1.90GHz with 24576712 kB of memory.
  Processor Board ID FDO21510JKR

Kernel uptime is 60 day(s), 5 hour(s), 30 minute(s), 22 second(s)
""",
    NXOS_IPS[1]: """\
Cisco Nexus Operating System (NX-OS) Software
TAC support: http://www.cisco.com/tac
Copyright (c) 2002-2022, Cisco Systems, Inc. All rights reserved.

Software
  BIOS: version 07.69
  NXOS: version 9.3(8)

Hardware
  cisco Nexus9000 C93180YC-FX Chassis
  Intel(R) Xeon(R) CPU D-1528 @ 1.90GHz with 24576712 kB of memory.
  Processor Board ID FDO21510ABC

Kernel uptime is 45 day(s), 2 hour(s), 15 minute(s), 10 second(s)
""",
}


# =====================================================================
#  GBIC DETAILS (Transceiver)
# =====================================================================
GBIC_HPE = {
    HPE_IPS[0]: """\
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
""",
    HPE_IPS[1]: """\
GigabitEthernet1/0/1 transceiver diagnostic information:
The transceiver diagnostic information is as follows:
Current diagnostic parameters:
  Temp.(°C) Voltage(V)  Bias(mA)  RX power(dBm)  TX power(dBm)
  37.20     3.30        6.20      -4.50           -3.10

GigabitEthernet1/0/2 transceiver diagnostic information:
The transceiver diagnostic information is as follows:
Current diagnostic parameters:
  Temp.(°C) Voltage(V)  Bias(mA)  RX power(dBm)  TX power(dBm)
  36.80     3.31        6.15      -3.80           -2.90
""",
}

GBIC_IOS = {
    IOS_IPS[0]: """\
                                        Optical   Optical
                   Temperature  Voltage  Current  Tx Power  Rx Power
Port       (Celsius)    (Volts)  (mA)     (dBm)     (dBm)
---------  -----------  -------  -------  --------  --------
Gi1/0/1    32.7         3.28     6.1      -2.5      -3.1
Gi1/0/2    28.1         3.30     6.0      -2.3      -3.0
Te1/0/25   28.3         3.31     35.2     -1.2      -2.8
""",
    IOS_IPS[1]: """\
                                        Optical   Optical
                   Temperature  Voltage  Current  Tx Power  Rx Power
Port       (Celsius)    (Volts)  (mA)     (dBm)     (dBm)
---------  -----------  -------  -------  --------  --------
Gi1/0/1    30.5         3.29     6.2      -2.8      -3.5
Gi1/0/2    29.0         3.30     6.1      -2.6      -3.2
""",
}

GBIC_NXOS = {
    NXOS_IPS[0]: """\
Ethernet1/1
    transceiver is present
    type is 10Gbase-SR
    name is CISCO-AVAGO
    part number is SFBR-7702SDZ-CS5
    revision is G2.5
    serial number is AVD2048E1A6
    nominal bitrate is 10300 MBit/sec
    cisco id is --
    cisco extended id number is 4

    SFP Detail Diagnostics Information (internal calibration)
    ------------------------------------------------------------
                           High Alarm  High Warn  Low Warn   Low Alarm
           Measurement     Threshold   Threshold  Threshold  Threshold
    ----------  ----------  ----------  ----------  ----------
        Temperature  34.41 C      75.00 C     70.00 C    0.00 C     -5.00 C
        Voltage      3.22 V       3.63 V      3.46 V     2.97 V     3.13 V
        Current      9.89 mA      70.00 mA    68.00 mA   1.00 mA    2.00 mA
        Tx Power    -1.29 dBm     3.49 dBm    0.49 dBm  -12.19 dBm -8.19 dBm
        Rx Power    -9.26 dBm     3.49 dBm    0.49 dBm  -18.38 dBm -14.40 dBm
        Transmit Fault Count = 0

Ethernet1/2
    transceiver is present
    type is 10Gbase-SR

    SFP Detail Diagnostics Information (internal calibration)
    ------------------------------------------------------------
                           High Alarm  High Warn  Low Warn   Low Alarm
           Measurement     Threshold   Threshold  Threshold  Threshold
    ----------  ----------  ----------  ----------  ----------
        Temperature  33.50 C      75.00 C     70.00 C    0.00 C     -5.00 C
        Voltage      3.25 V       3.63 V      3.46 V     2.97 V     3.13 V
        Current      9.50 mA      70.00 mA    68.00 mA   1.00 mA    2.00 mA
        Tx Power    -1.50 dBm     3.49 dBm    0.49 dBm  -12.19 dBm -8.19 dBm
        Rx Power    -8.80 dBm     3.49 dBm    0.49 dBm  -18.38 dBm -14.40 dBm
        Transmit Fault Count = 0
""",
    NXOS_IPS[1]: """\
Ethernet1/49
    transceiver is present
    type is QSFP-40G-SR4
    name is CISCO-AVAGO

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
""",
}


# =====================================================================
#  CHANNEL GROUP (Port-Channel / LAG)
# =====================================================================
CHANNEL_HPE = {
    HPE_IPS[0]: """\
Loadsharing Type: Shar -- Shared-link group
Port Status:  S -- Selected  U -- Unselected  I -- Individual  B -- Blocked

AggID   Interface   Link   Attribute   Mode   Members
1       BAGG1       UP     A           LACP   HGE1/0/25(S) HGE1/0/26(S)
2       BAGG2       UP     A           LACP   HGE1/0/27(S) HGE1/0/28(S)
""",
}

CHANNEL_IOS = {
    IOS_IPS[0]: """\
Flags:  D - down        P - bundled in port-channel
        I - stand-alone s - suspended
        H - Hot-standby (LACP only)
        R - Layer3      S - Layer2
        U - in use      N - not in use, no aggregation
        f - failed to allocate aggregator

Number of channel-groups in use: 2
Number of aggregators:           2

Group  Port-channel  Protocol    Ports
------+-------------+-----------+-----------------------------------------------
1      Po1(SU)       LACP        Gi1/0/25(P) Gi1/0/26(P)
7      Po7(SU)       LACP        Gi1/0/5(P)  Gi1/0/6(P)
""",
    IOS_IPS[1]: """\
Flags:  D - down        P - bundled in port-channel
        I - stand-alone s - suspended
        H - Hot-standby (LACP only)

Number of channel-groups in use: 1
Number of aggregators:           1

Group  Port-channel  Protocol    Ports
------+-------------+-----------+-----------------------------------------------
1      Po1(SU)       LACP        Gi1/0/25(P) Gi1/0/26(P)
""",
}

CHANNEL_NXOS = {
    NXOS_IPS[0]: """\
Flags:  D - Down        P - Up in port-channel (members)
        I - Individual  H - Hot-standby (LACP only)
        s - Suspended   r - Module-removed
        S - Switched    R - Routed
        U - Up (port-channel)
        M - Not in use. Min-links not met
--------------------------------------------------------------------------------
Group Port-       Type     Protocol  Member Ports
      Channel
--------------------------------------------------------------------------------
1     Po1(SU)     Eth      LACP      Eth1/25(P)    Eth1/26(P)
811   Po811(RU)   Eth      LACP      Eth15/8(P)   Eth15/28(P)  Eth16/8(P)
                                     Eth16/28(P)
""",
    NXOS_IPS[1]: """\
Flags:  D - Down        P - Up in port-channel (members)
        I - Individual  H - Hot-standby (LACP only)
        s - Suspended   r - Module-removed
        S - Switched    R - Routed
        U - Up (port-channel)
--------------------------------------------------------------------------------
Group Port-       Type     Protocol  Member Ports
      Channel
--------------------------------------------------------------------------------
1     Po1(SU)     Eth      LACP      Eth1/25(P)    Eth1/26(P)
""",
}


# =====================================================================
#  UPLINK (LLDP/CDP Neighbors)
# =====================================================================
UPLINK_HPE = {
    HPE_IPS[0]: """\
LLDP neighbor-information of port 25[GigabitEthernet1/0/25]:
  Neighbor index                   : 1
  Update time                      : 0 days, 0 hours, 1 minutes, 30 seconds
  Chassis type                     : MAC address
  Chassis ID                       : 000c-29aa-bb01
  Port ID type                     : Interface name
  Port ID                          : HundredGigE1/0/1
  Port description                 : uplink
  System name                      : CORE-SW-01
  System description               : HPE Comware Platform Software,
  Software Version 7.1.070, Release 6635P07
  System capabilities supported    : Bridge, Router
  System capabilities enabled      : Bridge, Router

LLDP neighbor-information of port 26[GigabitEthernet1/0/26]:
  Neighbor index                   : 1
  Chassis ID                       : 000c-29aa-bb02
  Port ID                          : HundredGigE1/0/2
  System name                      : CORE-SW-02
  System description               : HPE Comware Platform Software
""",
    HPE_IPS[1]: """\
LLDP neighbor-information of port 25[GigabitEthernet1/0/25]:
  Neighbor index                   : 1
  Chassis ID                       : 000c-29aa-cc01
  Port ID                          : HundredGigE2/0/1
  System name                      : DIST-SW-01
  System description               : HPE Comware Platform Software
""",
}

UPLINK_IOS = {
    IOS_IPS[0]: """\
-------------------------
Device ID: SW-CORE-01.example.com
Entry address(es):
  IP address: 10.0.0.1
Platform: cisco WS-C3750X-48PF,  Capabilities: Router Switch IGMP
Interface: GigabitEthernet0/1,  Port ID (outgoing port): GigabitEthernet1/0/1
Holdtime : 143 sec
Version :
Cisco IOS Software, C3750E Software, Version 15.2(4)E10
-------------------------
Device ID: SW-CORE-02
Platform: cisco WS-C3750X-48PF,  Capabilities: Router Switch IGMP
Interface: GigabitEthernet0/2,  Port ID (outgoing port): GigabitEthernet1/0/1
Holdtime : 143 sec
""",
    IOS_IPS[1]: """\
-------------------------
Device ID: SW-DIST-01.example.com
Entry address(es):
  IP address: 10.0.0.3
Platform: cisco WS-C3750X-24PF,  Capabilities: Router Switch IGMP
Interface: GigabitEthernet0/1,  Port ID (outgoing port): GigabitEthernet1/0/1
Holdtime : 140 sec
""",
}

UPLINK_NXOS = {
    NXOS_IPS[0]: """\
Chassis id: 0026.980a.3c01
Port id: Ethernet1/25
Local Port id: Eth1/1
Port Description: SERVER-ETH0
System Name: SPINE-01
System Description:
Cisco Nexus Operating System (NX-OS) Software 9.3(8)
Time remaining: 106 seconds
System Capabilities: B, R
Enabled Capabilities: B, R
Management Address: 10.0.0.1

Chassis id: 0026.980a.3c02
Port id: Ethernet1/25
Local Port id: Eth1/2
System Name: SPINE-02
System Description:
Cisco Nexus Operating System (NX-OS) Software 9.3(8)
Time remaining: 106 seconds
""",
    NXOS_IPS[1]: """\
Chassis id: 0026.980a.3c03
Port id: Ethernet1/49
Local Port id: Eth1/1
System Name: SPINE-03
System Description:
Cisco Nexus Operating System (NX-OS) Software 9.3(8)
Time remaining: 110 seconds
""",
}


# =====================================================================
#  ERROR COUNT
# =====================================================================
ERROR_HPE = {
    HPE_IPS[0]: """\
Interface             Total(pkts)  Broadcast   Multicast  Err(pkts)
GE1/0/1                    123456       1234         567          0
GE1/0/2                     98765        876         432          5
XGE1/0/25                  654321       5432        1234          0
""",
    HPE_IPS[1]: """\
Interface             Total(pkts)  Broadcast   Multicast  Err(pkts)
GE1/0/1                    234567       2345         678          0
GE1/0/2                    187654       1876         543          1
""",
}

ERROR_IOS = {
    IOS_IPS[0]: """\
Port        Align-Err    FCS-Err   Xmit-Err    Rcv-Err  UnderSize OutDiscards
Gi0/1               0          0          0          0          0           0
Gi0/2               0          5          0          3          0           0
Gi0/3               0          0          0          0          0           0
""",
    IOS_IPS[1]: """\
Port        Align-Err    FCS-Err   Xmit-Err    Rcv-Err  UnderSize OutDiscards
Gi0/1               0          0          0          0          0           0
Gi0/2               0          0          1          0          0           0
""",
}

ERROR_NXOS = {
    NXOS_IPS[0]: """\
--------------------------------------------------------------------------------
Port          Align-Err    FCS-Err   Xmit-Err    Rcv-Err  UnderSize OutDiscards
--------------------------------------------------------------------------------
Eth1/1                0          0          0          0          0           0
Eth1/2                0          3          2          5          0           0
Eth1/3                0          0          0          0          0           0
""",
    NXOS_IPS[1]: """\
--------------------------------------------------------------------------------
Port          Align-Err    FCS-Err   Xmit-Err    Rcv-Err  UnderSize OutDiscards
--------------------------------------------------------------------------------
Eth1/1                0          0          0          0          0           0
Eth1/2                0          0          0          0          0           0
""",
}



# =====================================================================
#  MAC TABLE
# =====================================================================
MAC_HPE = {
    HPE_IPS[0]: """\
MAC ADDR          VLAN ID  STATE          PORT INDEX               AGING TIME(s)
000c-29aa-bb01    100      Learned        GigabitEthernet1/0/1     AGING
000c-29aa-bb02    200      Learned        GigabitEthernet1/0/2     AGING
000c-29aa-bb03    10       Security       GigabitEthernet1/0/3     NOAGED
""",
    HPE_IPS[1]: """\
MAC ADDR          VLAN ID  STATE          PORT INDEX               AGING TIME(s)
000c-29aa-cc01    100      Learned        GigabitEthernet1/0/1     AGING
000c-29aa-cc02    100      Learned        GigabitEthernet1/0/2     AGING
""",
}

MAC_IOS = {
    IOS_IPS[0]: """\
              Mac Address Table
-------------------------------------------

Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
  10    68a8.2845.7640    DYNAMIC     Gi1/0/3
  20    7c0e.ceca.9548    DYNAMIC     Gi1/0/1
 100    0100.5e00.0001    STATIC      CPU
Total Mac Addresses for this criterion: 3
""",
    IOS_IPS[1]: """\
              Mac Address Table
-------------------------------------------

Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
  10    a0b1.c2d3.e4f5    DYNAMIC     Gi1/0/1
  20    a0b1.c2d3.e4f6    DYNAMIC     Gi1/0/2
Total Mac Addresses for this criterion: 2
""",
}

MAC_NXOS = {
    NXOS_IPS[0]: """\
Legend:
        * - primary entry, G - Gateway MAC, (R) - Routed MAC, O - Overlay MAC
        age - seconds since last seen,+ - primary entry using vPC Peer-Link

   VLAN     MAC Address      Type      age     Secure   NTFY   Ports
---------+-----------------+--------+---------+------+----+------------------
*   10     5254.0012.d6e1   dynamic  0         F      F    Eth1/2
*   10     5254.0018.39c9   dynamic  0         F      F    Eth1/1
*   20     0050.5687.1abb   dynamic  0         F      F    Eth1/3
G    -     5254.0001.0607   static   -         F      F    sup-eth1(R)
""",
    NXOS_IPS[1]: """\
Legend:
        * - primary entry, G - Gateway MAC, (R) - Routed MAC

   VLAN     MAC Address      Type      age     Secure   NTFY   Ports
---------+-----------------+--------+---------+------+----+------------------
*   10     aabb.ccdd.0001   dynamic  0         F      F    Eth1/1
*   20     aabb.ccdd.0002   dynamic  0         F      F    Eth1/2
""",
}


# =====================================================================
#  STATIC ACL
# =====================================================================
STATIC_ACL_HPE = {
    HPE_IPS[0]: """\
interface GigabitEthernet1/0/1
 packet-filter 3001 inbound
interface GigabitEthernet1/0/2
 packet-filter 3002 inbound
interface GigabitEthernet1/0/3
""",
    HPE_IPS[1]: """\
interface GigabitEthernet1/0/1
 packet-filter 3001 inbound
interface GigabitEthernet1/0/2
""",
}

STATIC_ACL_IOS = {
    IOS_IPS[0]: """\
interface GigabitEthernet1/0/1
 ip access-group 101 in
interface GigabitEthernet1/0/2
 ip access-group 102 in
interface GigabitEthernet1/0/3
""",
    IOS_IPS[1]: """\
interface GigabitEthernet1/0/1
 ip access-group 101 in
interface GigabitEthernet1/0/2
""",
}

STATIC_ACL_NXOS = {
    NXOS_IPS[0]: """\
interface Ethernet1/1
 ip access-group 101 in
interface Ethernet1/2
 ip access-group 102 in
interface Ethernet1/3
""",
    NXOS_IPS[1]: """\
interface Ethernet1/1
 ip access-group 101 in
interface Ethernet1/2
""",
}


# =====================================================================
#  DYNAMIC ACL
# =====================================================================
DYNAMIC_ACL_HPE = {
    HPE_IPS[0]: """\
Slot ID   : 1
Total connections : 3

Interface         MAC Address     Auth State      ACL Number
GE1/0/1           aabb-ccdd-0001  Authenticated   3001
GE1/0/2           aabb-ccdd-0002  Unauthenticated --
GE1/0/3           aabb-ccdd-0003  Authenticated   3001
""",
    HPE_IPS[1]: """\
Slot ID   : 1
Total connections : 2

Interface         MAC Address     Auth State      ACL Number
GE1/0/1           aabb-ccdd-0004  Authenticated   3002
GE1/0/2           aabb-ccdd-0005  Authenticated   3002
""",
}

DYNAMIC_ACL_IOS = {
    IOS_IPS[0]: """\
Interface         MAC Address        ACL         Status
Gi1/0/1           0050.5687.1234     101         Authorized
Gi1/0/2           0050.5687.5678     --          Unauthorized
Gi1/0/3           0050.5687.9abc     102         Authorized
""",
    IOS_IPS[1]: """\
Interface         MAC Address        ACL         Status
Gi1/0/1           0050.5687.abcd     101         Authorized
Gi1/0/2           0050.5687.ef01     101         Authorized
""",
}

DYNAMIC_ACL_NXOS = {
    NXOS_IPS[0]: """\
Interface         MAC Address        ACL         Status
Eth1/1            aabb.ccdd.0001     101         Authorized
Eth1/2            aabb.ccdd.0002     --          Unauthorized
""",
    NXOS_IPS[1]: """\
Interface         MAC Address        ACL         Status
Eth1/1            aabb.ccdd.0003     102         Authorized
""",
}


# =====================================================================
#  Master registry: api → device_type → {ip: content}
# =====================================================================
ALL_DATA: dict[str, dict[str, dict[str, str]]] = {
    "get_fan": {"hpe": FAN_HPE, "ios": FAN_IOS, "nxos": FAN_NXOS},
    "get_power": {"hpe": POWER_HPE, "ios": POWER_IOS, "nxos": POWER_NXOS},
    "get_version": {"hpe": VERSION_HPE, "ios": VERSION_IOS, "nxos": VERSION_NXOS},
    "get_gbic_details": {"hpe": GBIC_HPE, "ios": GBIC_IOS, "nxos": GBIC_NXOS},
    "get_channel_group": {"hpe": CHANNEL_HPE, "ios": CHANNEL_IOS, "nxos": CHANNEL_NXOS},
    "get_uplink": {"hpe": UPLINK_HPE, "ios": UPLINK_IOS, "nxos": UPLINK_NXOS},
    "get_error_count": {"hpe": ERROR_HPE, "ios": ERROR_IOS, "nxos": ERROR_NXOS},
"get_mac_table": {"hpe": MAC_HPE, "ios": MAC_IOS, "nxos": MAC_NXOS},
    "get_static_acl": {"hpe": STATIC_ACL_HPE, "ios": STATIC_ACL_IOS, "nxos": STATIC_ACL_NXOS},
    "get_dynamic_acl": {"hpe": DYNAMIC_ACL_HPE, "ios": DYNAMIC_ACL_IOS, "nxos": DYNAMIC_ACL_NXOS},
}


def main() -> None:
    no_clean = "--no-clean" in sys.argv

    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if not no_clean:
        for f in RAW_DIR.glob("*.txt"):
            f.unlink()
        print(f"Cleaned {RAW_DIR}/")

    count = 0
    for api_name, devices in sorted(ALL_DATA.items()):
        for device_type, ips in sorted(devices.items()):
            for ip, content in sorted(ips.items()):
                fname = f"{api_name}_{device_type}_{ip}.txt"
                path = RAW_DIR / fname
                path.write_text(content)
                count += 1

    print(f"Generated {count} test data files in {RAW_DIR}/")


if __name__ == "__main__":
    main()
