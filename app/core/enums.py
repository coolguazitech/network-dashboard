"""
Enumeration definitions for the application.

All enums are defined here to maintain consistency and type safety.
"""
from enum import Enum


class DeviceType(str, Enum):
    """
    Device types — the single enum for parser lookup, API params, and DB storage.

    Values match MaintenanceDeviceList.new_vendor / old_vendor column values.
    Use .api_value for external API parameters (lowercase: hpe, ios, nxos).
    """

    HPE = "HPE"
    CISCO_IOS = "Cisco-IOS"
    CISCO_NXOS = "Cisco-NXOS"

    @property
    def api_value(self) -> str:
        """Lowercase value for external API endpoint params: hpe, ios, nxos."""
        return {"HPE": "hpe", "Cisco-IOS": "ios", "Cisco-NXOS": "nxos"}[self.value]


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

    Values are uppercase to match production DB enum definitions.
    """

    NOT_CHECKED = "NOT_CHECKED"
    DETECTED = "DETECTED"
    MISMATCH = "MISMATCH"
    NOT_DETECTED = "NOT_DETECTED"


class CaseStatus(str, Enum):
    """
    案件處理狀態。

    Values are uppercase to match production DB enum definitions.
    """

    UNASSIGNED = "UNASSIGNED"       # 未指派
    ASSIGNED = "ASSIGNED"           # 已指派
    IN_PROGRESS = "IN_PROGRESS"     # 處理中
    DISCUSSING = "DISCUSSING"       # 待討論
    RESOLVED = "RESOLVED"           # 已解決


class MealDeliveryStatus(str, Enum):
    """
    餐點配送狀態。

    Values are uppercase to match production DB enum definitions.
    """

    NO_MEAL = "NO_MEAL"
    PENDING = "PENDING"
    ARRIVED = "ARRIVED"


class UserRole(str, Enum):
    """
    使用者角色定義。

    - ROOT: 超級管理員，可管理歲修 ID 和使用者
    - PM: 專案經理，有除了歲修/用戶管理外的所有寫入權限
    - GUEST: 訪客，只有讀取權限，所有寫入操作都禁止

    Values are uppercase to match production DB enum definitions.
    """

    ROOT = "ROOT"
    PM = "PM"
    GUEST = "GUEST"


# ── ParsedData 嚴格枚舉 ─────────────────────────────────────────


class OperationalStatus(str, Enum):
    """硬體元件（風扇、電源）的操作狀態。

    健康狀態判定由 .env OPERATIONAL_HEALTHY_STATUSES 控制，
    此枚舉僅用於 parser 正規化。
    """

    OK = "ok"
    GOOD = "good"
    NORMAL = "normal"
    ONLINE = "online"
    ACTIVE = "active"
    FAIL = "fail"
    ABSENT = "absent"
    UNKNOWN = "unknown"


class LinkStatus(str, Enum):
    """鏈路 / Port-Channel / 介面的連線狀態。"""

    UP = "up"
    DOWN = "down"
    UNKNOWN = "unknown"


class DuplexMode(str, Enum):
    """介面雙工模式。"""

    FULL = "full"
    HALF = "half"
    AUTO = "auto"
    UNKNOWN = "unknown"


class AggregationProtocol(str, Enum):
    """鏈路聚合協議。"""

    LACP = "lacp"
    STATIC = "static"
    PAGP = "pagp"
    NONE = "none"
