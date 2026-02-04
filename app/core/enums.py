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
    設備類別（非時間概念）。

    用於區分歲修期間操作的設備類型：
    - OLD: 舊設備（被更換的設備）
    - NEW: 新設備（替換上去的設備）

    注意：這與時間軸上的「checkpoint 時間」vs「最新快照時間」是獨立的概念。
    同一個 phase 的資料可能在不同時間點被採集多次。
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
