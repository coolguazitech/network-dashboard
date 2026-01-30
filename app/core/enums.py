"""
Enumeration definitions for the application.

All enums are defined here to maintain consistency and type safety.
"""
from enum import Enum, auto


class VendorType(str, Enum):
    """Network device vendor types."""

    CISCO = "cisco"
    HPE = "hpe"
    ARUBA = "aruba"


class PlatformType(str, Enum):
    """Platform/OS types for each vendor."""

    # Cisco platforms
    CISCO_IOS = "ios"
    CISCO_NXOS = "nxos"

    # HPE platforms
    HPE_PROCURVE = "procurve"
    HPE_COMWARE = "comware"

    # Aruba platforms
    ARUBA_OS = "aruba_os"
    ARUBA_CX = "aruba_cx"


class SiteType(str, Enum):
    """Site identifiers for external API."""

    T_SITE = "t_site"
    M_SITE = "m_site"
    H_SITE = "h_site"
    NJ = "nj"
    JASM = "jasm"
    AZ = "az"


class IndicatorObjectType(str, Enum):
    """
    The smallest unit of observation for an indicator.

    Examples:
    - INTERFACE: observe each interface (e.g., Tx/Rx power)
    - SWITCH: observe the switch itself (e.g., fan status)
    - ACL: observe ACL rules
    - UPLINK: observe uplink connections
    """

    INTERFACE = "interface"
    SWITCH = "switch"
    ACL = "acl"
    UPLINK = "uplink"


class DataType(str, Enum):
    """Data types for indicator values."""

    FLOAT = "float"
    INTEGER = "integer"
    STRING = "string"
    BOOLEAN = "boolean"


class MetricType(str, Enum):
    """
    Types of metrics for evaluation.

    - RANGE: value must be within min/max range
    - THRESHOLD: value must be above/below threshold
    - EQUALS: value must equal expected value (string comparison)
    - BOOLEAN: value is true/false
    - MAPPING: compare before/after with device mapping
    """

    RANGE = "range"
    THRESHOLD = "threshold"
    EQUALS = "equals"
    BOOLEAN = "boolean"
    MAPPING = "mapping"


class CollectionStatus(str, Enum):
    """Status of data collection."""

    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"
    PENDING = "pending"


class MaintenancePhase(str, Enum):
    """
    Maintenance phases for comparison.

    - OLD: existing/old equipment
    - NEW: replaced/new equipment
    """

    OLD = "old"
    NEW = "new"


class TenantGroup(str, Enum):
    """Tenant group for GNMS Ping API."""

    F18 = "F18"
    F6 = "F6"
    AP = "AP"
    F14 = "F14"
    F12 = "F12"


class ClientDetectionStatus(str, Enum):
    """
    Detection status for clients in maintenance.

    - NOT_CHECKED: Initial state, not yet checked
    - DETECTED: Client IP is reachable via GNMS Ping
    - MISMATCH: ARP data shows different IP-MAC mapping than user provided
    - NOT_DETECTED: Client IP is not reachable
    """

    NOT_CHECKED = "not_checked"  # 未檢查
    DETECTED = "detected"  # 已偵測
    MISMATCH = "mismatch"  # 不匹配
    NOT_DETECTED = "not_detected"  # 未偵測
