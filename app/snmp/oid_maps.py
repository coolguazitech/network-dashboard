"""
OID Constants & Vendor-Specific Mapping Tables.

所有 SNMP OID 常數集中管理於此，collector 只需引用。
"""
from __future__ import annotations

# =============================================================================
# Standard MIBs (跨廠商通用)
# =============================================================================

# SNMPv2-MIB
SYS_DESCR = "1.3.6.1.2.1.1.1.0"
SYS_OBJECT_ID = "1.3.6.1.2.1.1.2.0"

# IF-MIB
IF_NAME = "1.3.6.1.2.1.31.1.1.1.1"          # ifName (indexed by ifIndex)
IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"       # 1=up, 2=down, 3=testing
IF_SPEED = "1.3.6.1.2.1.2.2.1.5"             # bits/sec
IF_HIGH_SPEED = "1.3.6.1.2.1.31.1.1.1.15"    # Mbps (for >1G)
IF_IN_ERRORS = "1.3.6.1.2.1.2.2.1.14"        # ifInErrors
IF_OUT_ERRORS = "1.3.6.1.2.1.2.2.1.20"       # ifOutErrors
IF_TYPE = "1.3.6.1.2.1.2.2.1.3"              # ifType

# EtherLike-MIB
DOT3_STATS_FCS_ERRORS = "1.3.6.1.2.1.10.7.2.1.3"
DOT3_STATS_DUPLEX = "1.3.6.1.2.1.10.7.2.1.19"  # 1=unknown,2=half,3=full

# Q-BRIDGE-MIB (MAC table)
DOT1Q_TP_FDB_PORT = "1.3.6.1.2.1.17.7.1.2.2.1.2"

# BRIDGE-MIB
DOT1D_BASE_PORT_IF_INDEX = "1.3.6.1.2.1.17.1.4.1.2"
DOT1D_TP_FDB_PORT = "1.3.6.1.2.1.17.4.3.1.2"  # per-VLAN MAC table (Cisco IOS)

# LLDP-MIB (IEEE 802.1AB)
LLDP_REM_SYS_NAME = "1.0.8802.1.1.2.1.4.1.1.9"
LLDP_REM_PORT_ID = "1.0.8802.1.1.2.1.4.1.1.7"
LLDP_REM_PORT_DESC = "1.0.8802.1.1.2.1.4.1.1.8"
LLDP_LOC_PORT_ID = "1.0.8802.1.1.2.1.3.7.1.3"
LLDP_LOC_PORT_DESC = "1.0.8802.1.1.2.1.3.7.1.4"

# IEEE8023-LAG-MIB
DOT3AD_AGG_PORT_ATTACHED_AGG_ID = "1.2.840.10006.300.43.1.2.1.1.13"
DOT3AD_AGG_PORT_ACTOR_OPER_STATE = "1.2.840.10006.300.43.1.2.1.1.21"

# =============================================================================
# Vendor-Specific: HPE/H3C (Enterprise 25506)
# =============================================================================

# HH3C-ENTITY-EXT-MIB
HH3C_ENTITY_EXT_ERROR_STATUS = "1.3.6.1.4.1.25506.2.6.1.1.1.1.19"

# ENTITY-MIB (standard but needed for H3C cross-reference)
ENT_PHYSICAL_NAME = "1.3.6.1.2.1.47.1.1.1.1.7"
ENT_PHYSICAL_CLASS = "1.3.6.1.2.1.47.1.1.1.1.5"

# HH3C-TRANSCEIVER-INFO-MIB
HH3C_TRANSCEIVER_TEMPERATURE = "1.3.6.1.4.1.25506.2.70.1.1.1.1.15"
HH3C_TRANSCEIVER_VOLTAGE = "1.3.6.1.4.1.25506.2.70.1.1.1.1.16"
HH3C_TRANSCEIVER_BIAS = "1.3.6.1.4.1.25506.2.70.1.1.1.1.17"
HH3C_TRANSCEIVER_TX_POWER = "1.3.6.1.4.1.25506.2.70.1.1.1.1.9"   # hh3cTransceiverCurTXPower
HH3C_TRANSCEIVER_RX_POWER = "1.3.6.1.4.1.25506.2.70.1.1.1.1.12"  # hh3cTransceiverCurRXPower

# =============================================================================
# Vendor-Specific: Cisco (Enterprise 9)
# =============================================================================

# CISCO-ENVMON-MIB (fan + power)
CISCO_ENV_FAN_STATE = "1.3.6.1.4.1.9.9.13.1.4.1.3"
CISCO_ENV_FAN_DESCR = "1.3.6.1.4.1.9.9.13.1.4.1.2"
CISCO_ENV_SUPPLY_STATE = "1.3.6.1.4.1.9.9.13.1.5.1.3"
CISCO_ENV_SUPPLY_DESCR = "1.3.6.1.4.1.9.9.13.1.5.1.2"

# CISCO-ENTITY-SENSOR-MIB (transceiver DOM)
CISCO_ENT_SENSOR_VALUE = "1.3.6.1.4.1.9.9.91.1.1.1.1.4"
CISCO_ENT_SENSOR_TYPE = "1.3.6.1.4.1.9.9.91.1.1.1.1.1"
CISCO_ENT_SENSOR_SCALE = "1.3.6.1.4.1.9.9.91.1.1.1.1.2"
CISCO_ENT_SENSOR_PRECISION = "1.3.6.1.4.1.9.9.91.1.1.1.1.3"
CISCO_ENT_SENSOR_STATUS = "1.3.6.1.4.1.9.9.91.1.1.1.1.5"

# CISCO-VTP-MIB (VLAN list for per-VLAN MAC table)
CISCO_VTP_VLAN_STATE = "1.3.6.1.4.1.9.9.46.1.3.1.1.2"

# CISCO-CDP-MIB
CISCO_CDP_CACHE_DEVICE_ID = "1.3.6.1.4.1.9.9.23.1.2.1.1.6"
CISCO_CDP_CACHE_DEVICE_PORT = "1.3.6.1.4.1.9.9.23.1.2.1.1.7"

# =============================================================================
# Value Mapping Tables
# =============================================================================

# HH3C-ENTITY-EXT-MIB::hh3cEntityExtErrorStatus
HH3C_ERROR_STATUS_MAP: dict[int, str] = {
    1: "unknown",       # notSupported
    2: "normal",
    3: "fail",          # postFailure
    4: "absent",        # entityAbsent
    11: "fail",         # poeError
    21: "fail",         # stackError
    22: "fail",         # stackPortBlocked
    23: "fail",         # stackPortFailed
    31: "fail",         # sfpRecvError
    32: "fail",         # sfpSendError
    33: "fail",         # sfpBothError
    41: "fail",         # fanError
    51: "fail",         # psuError
    61: "fail",         # rpsError
    71: "fail",         # moduleFaulty
    81: "fail",         # sensorError
    91: "fail",         # hardwareFaulty
}

# CISCO-ENVMON-MIB::ciscoEnvMonFanState / ciscoEnvMonSupplyState
CISCO_ENVMON_STATE_MAP: dict[int, str] = {
    1: "normal",
    2: "normal",        # warning — still operational
    3: "fail",          # critical
    4: "fail",          # shutdown
    5: "absent",        # notPresent
    6: "fail",          # notFunctioning
}

# IF-MIB::ifOperStatus
IF_OPER_STATUS_MAP: dict[int, str] = {
    1: "up",
    2: "down",
    3: "down",          # testing → treat as down
    4: "unknown",
    5: "down",          # dormant
    6: "down",          # notPresent
    7: "down",          # lowerLayerDown
}

# EtherLike-MIB::dot3StatsDuplexStatus
DUPLEX_STATUS_MAP: dict[int, str] = {
    1: "unknown",
    2: "half",
    3: "full",
}

# CISCO-ENTITY-SENSOR-MIB::entSensorType
CISCO_SENSOR_TYPE_CELSIUS = 8
CISCO_SENSOR_TYPE_VOLTS_DC = 4
CISCO_SENSOR_TYPE_AMPERES = 5
CISCO_SENSOR_TYPE_DBM = 14

# CISCO-ENTITY-SENSOR-MIB::entSensorScale
CISCO_SENSOR_SCALE_MAP: dict[int, float] = {
    1: 1e-24,   # yocto
    2: 1e-21,   # zepto
    3: 1e-18,   # atto
    4: 1e-15,   # femto
    5: 1e-12,   # pico
    6: 1e-9,    # nano
    7: 1e-6,    # micro
    8: 1e-3,    # milli
    9: 1.0,     # units
    10: 1e3,    # kilo
    11: 1e6,    # mega
    12: 1e9,    # giga
    13: 1e12,   # tera
    14: 1e18,   # exa
    15: 1e15,   # peta
    16: 1e21,   # zetta
    17: 1e24,   # yotta
}

# ENTITY-MIB::entPhysicalClass
ENT_PHYSICAL_CLASS_FAN = 7
ENT_PHYSICAL_CLASS_POWER_SUPPLY = 6
ENT_PHYSICAL_CLASS_SENSOR = 8
ENT_PHYSICAL_CLASS_MODULE = 9
ENT_PHYSICAL_CLASS_PORT = 10

# ifType values for filtering physical ports
IF_TYPE_ETHERNET_CSMACD = 6
IF_TYPE_GIG_ETHERNET = 117
IF_TYPE_PROP_VIRTUAL = 53     # Port-Channel / LAG
IF_TYPE_IEEE8023AD_LAG = 161  # 802.3ad LAG
