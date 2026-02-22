"""
Parser protocols and base types — Parser 開發的核心模組。

==========================================================================
本模組定義所有 Parser 必須實作的介面，以及 Parser 回傳的資料模型（ParsedData）。
如果你要為新的設備廠牌 / 平台撰寫 Parser，本文件是你的起點。
==========================================================================

架構總覽：
    Fetcher (採集原始 CLI 輸出)
        ↓ raw_output: str
    Parser (本模組定義的介面)
        ↓ list[ParsedData]
    Indicator (評估是否通過)
        ↓ IndicatorEvaluationResult

ParsedData 是 Parser 與下游程式之間的嚴格契約：
- 枚舉欄位透過 before-validator 自動正規化（大小寫不敏感）
  例如 "OK", "ok", "Ok" → OperationalStatus.OK ("ok")
- 數值欄位有合理範圍限制（Pydantic Field 的 ge/le）
  例如 tx_power: float | None = Field(None, ge=-40.0, le=10.0)
- MAC / IP 有格式驗證（自動正規化為標準格式）
- 無法匹配枚舉時 → "unknown"（不拋錯，讓 indicator 判為 fail）

ParsedData 子類別一覽：
    TransceiverData      - 光模組診斷（巢狀 channels: 每通道 Tx/Rx/Bias + 模組層溫度/電壓）
    InterfaceErrorData   - 介面 CRC 錯誤計數（inbound+outbound 加總）
    FanStatusData        - 風扇狀態（status 自動正規化為 OperationalStatus）
    VersionData          - 韌體版本（version, model, serial_number）
    NeighborData         - 鄰居資訊（CDP/LLDP）
    PortChannelData      - Port-Channel/LAG 資訊（成員、狀態、協議）
    PowerData            - 電源供應器狀態
    MacTableData         - MAC 位址表（vlan_id 無結果時為 0）
    AclData              - ACL 編號（來自 static_acl 或 dynamic_acl）
    PingResultData       - 單一 IP Ping 結果
"""
from __future__ import annotations

import ipaddress
import re
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, field_validator

from app.core.enums import (
    AggregationProtocol,
    DeviceType,
    DuplexMode,
    LinkStatus,
    OperationalStatus,
)

# Type variable for parsed result
TResult = TypeVar("TResult", bound=BaseModel)


# ── Helper ───────────────────────────────────────────────────────


_MAC_SEPARATORS = re.compile(r"[.:\-]")


def _normalize_mac(raw: str) -> str:
    """
    將各種 MAC 格式正規化為 AA:BB:CC:DD:EE:FF。

    支援：
    - AA:BB:CC:DD:EE:FF（標準）
    - AA-BB-CC-DD-EE-FF（Windows）
    - AABB.CCDD.EEFF（Cisco）
    - aabbccddeeff（無分隔）
    """
    digits = _MAC_SEPARATORS.sub("", raw).upper()
    if len(digits) != 12 or not all(c in "0123456789ABCDEF" for c in digits):
        return raw.upper()  # 無法解析，原樣返回（大寫）
    return ":".join(digits[i : i + 2] for i in range(0, 12, 2))


def _normalize_operational_status(v: Any) -> str:
    """將 status 字串正規化為 OperationalStatus 枚舉值。"""
    if v is None:
        return OperationalStatus.UNKNOWN.value
    if isinstance(v, str):
        v = v.strip().lower()
    try:
        return OperationalStatus(v).value
    except ValueError:
        return OperationalStatus.UNKNOWN.value


def _normalize_link_status(v: Any) -> str:
    """將 link status 字串正規化為 LinkStatus 枚舉值。"""
    if v is None:
        return LinkStatus.UNKNOWN.value
    if isinstance(v, str):
        v = v.strip().lower()
    try:
        return LinkStatus(v).value
    except ValueError:
        return LinkStatus.UNKNOWN.value


def _validate_ipv4(v: str) -> str:
    """驗證 IPv4 格式，無效時原樣返回。"""
    v = v.strip()
    try:
        ipaddress.IPv4Address(v)
    except (ValueError, ipaddress.AddressValueError):
        pass  # 不拋錯，讓資料進 DB，downstream 會處理
    return v


# ── ParsedData Models ────────────────────────────────────────────


class ParsedData(BaseModel):
    """Base class for all parsed data."""

    pass


class TransceiverChannelData(BaseModel):
    """單一通道的光模組診斷資料。"""

    channel: int = Field(ge=1, le=4, description="通道編號 (SFP=1, QSFP=1~4)")
    tx_power: float | None = Field(None, ge=-40.0, le=10.0, description="發射功率 (dBm)")
    rx_power: float | None = Field(None, ge=-40.0, le=10.0, description="接收功率 (dBm)")
    bias_current_ma: float | None = Field(None, ge=0.0, description="偏置電流 (mA)")


class TransceiverData(ParsedData):
    """光模組診斷 — 每個介面一筆，通道資料以巢狀 list 表示。

    一個 SFP 模組有 1 個 channel，一個 QSFP 模組有 1~4 個 channel。
    temperature / voltage 屬於模組層級，tx_power / rx_power / bias 屬於通道層級。

    存入 DB 時由 Repository 負責展開 channels 為扁平 rows。
    """

    interface_name: str
    temperature: float | None = Field(None, ge=-10.0, le=100.0, description="模組溫度 (°C)")
    voltage: float | None = Field(None, ge=0.0, le=10.0, description="模組電壓 (V)")
    channels: list[TransceiverChannelData]


class InterfaceErrorData(ParsedData):
    """介面 CRC 錯誤計數。

    crc_errors 是 inbound + outbound CRC 錯誤的加總結果。
    Parser 負責將雙方向的計數合併後填入此欄位。
    """

    interface_name: str
    crc_errors: int = Field(0, ge=0, description="inbound + outbound CRC 錯誤加總")


class FanStatusData(ParsedData):
    """風扇狀態資料。"""

    fan_id: str
    status: str = Field(description="正規化為 OperationalStatus 枚舉值")
    speed_rpm: int | None = Field(None, ge=0)
    speed_percent: int | None = Field(None, ge=0, le=100)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Any) -> str:
        return _normalize_operational_status(v)


class VersionData(ParsedData):
    """韌體版本資料。"""

    version: str
    model: str | None = None
    serial_number: str | None = None
    uptime: str | None = None


class NeighborData(ParsedData):
    """鄰居 (CDP/LLDP) 資料。"""

    local_interface: str
    remote_hostname: str
    remote_interface: str
    remote_platform: str | None = None


class PortChannelData(ParsedData):
    """Port-Channel (LAG) 資料。"""

    interface_name: str
    status: str = Field(description="正規化為 LinkStatus 枚舉值")
    protocol: str | None = Field(None, description="正規化為 AggregationProtocol 枚舉值")
    members: list[str]
    member_status: dict[str, str] | None = None

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Any) -> str:
        return _normalize_link_status(v)

    @field_validator("protocol", mode="before")
    @classmethod
    def normalize_protocol(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip().lower()
        try:
            return AggregationProtocol(v).value
        except ValueError:
            return AggregationProtocol.NONE.value

    @field_validator("member_status", mode="before")
    @classmethod
    def normalize_member_status(cls, v: Any) -> dict[str, str] | None:
        if v is None:
            return None
        return {k: _normalize_link_status(s) for k, s in v.items()}


class PowerData(ParsedData):
    """電源供應器狀態資料。"""

    ps_id: str
    status: str = Field(description="正規化為 OperationalStatus 枚舉值")
    input_status: str | None = None
    output_status: str | None = None
    capacity_watts: float | None = Field(None, ge=0.0)
    actual_output_watts: float | None = Field(None, ge=0.0)

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Any) -> str:
        return _normalize_operational_status(v)

    @field_validator("input_status", "output_status", mode="before")
    @classmethod
    def normalize_sub_status(cls, v: Any) -> str | None:
        if v is None:
            return None
        return _normalize_operational_status(v)


# ── Client Fetcher 中間資料模型 ──────────────────────────────────


class MacTableData(ParsedData):
    """Fetcher get_mac_table 的解析結果。"""

    mac_address: str = Field(description="正規化為 AA:BB:CC:DD:EE:FF")
    interface_name: str
    vlan_id: int = Field(default=0, ge=0, le=4094, description="VLAN ID，parse 無結果時為 0")

    @field_validator("mac_address", mode="before")
    @classmethod
    def normalize_mac(cls, v: str) -> str:
        return _normalize_mac(v)



class InterfaceStatusData(ParsedData):
    """Fetcher get_interface_status 的解析結果。"""

    interface_name: str
    link_status: str = Field(description="正規化為 LinkStatus 枚舉值")
    speed: str | None = None
    duplex: str | None = None

    @field_validator("link_status", mode="before")
    @classmethod
    def normalize_link_status(cls, v: Any) -> str:
        return _normalize_link_status(v)

    @field_validator("duplex", mode="before")
    @classmethod
    def normalize_duplex(cls, v: Any) -> str | None:
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip().lower()
        try:
            return DuplexMode(v).value
        except ValueError:
            return DuplexMode.UNKNOWN.value


class AclData(ParsedData):
    """Fetcher get_acl_number 的解析結果。"""

    interface_name: str
    acl_number: str | None = None


class PingResultData(ParsedData):
    """單一 IP 的 Ping 結果。parse() 回傳 list[PingResultData] 代表多個 IP。"""

    target: str
    is_reachable: bool
    success_rate: float = 0.0
    avg_rtt_ms: float | None = None

    @field_validator("target", mode="before")
    @classmethod
    def validate_target(cls, v: str) -> str:
        return _validate_ipv4(v)


# ── Parser Base ──────────────────────────────────────────────────


class BaseParser(ABC, Generic[TResult]):
    """
    所有 Parser 的抽象基底類別 — 每個 Parser 負責解析一個特定 API 的 raw output。

    Parser 與 Indicator 完全解耦：
    - Parser 只關心「如何將 raw text 轉為對應的 ParsedData」
    - 一個 ParsedData 可能服務多個 Indicator
    - 一個 Indicator 可能使用多個 ParsedData 的資料

    =========================================================================
    如何新增一個 Parser：
    =========================================================================

    範例：

        .. code-block:: python

            from app.core.enums import DeviceType
            from app.parsers.protocols import BaseParser, TransceiverData
            from app.parsers.registry import parser_registry

            class GetTransceiverHpeFnaParser(BaseParser[TransceiverData]):
                device_type = DeviceType.HPE
                command = "get_transceiver_hpe_fna"

                def parse(self, raw_output: str) -> list[TransceiverData]:
                    results = []
                    # ... 解析邏輯 ...
                    return results

            parser_registry.register(GetTransceiverHpeFnaParser())

    =========================================================================
    Class attributes：
    =========================================================================

    device_type : DeviceType | None
        設備類型。設為 None 表示通用型（如 Ping）。
        Registry 查詢時先精確匹配，再 fallback 到 None。

    command : str
        此 Parser 對應的 API 名稱（即 api_test.yaml 中的 api name）。
        這是 Registry 查詢的 key，必須唯一。
        例如 "get_fan_hpe_dna", "get_errors_hpe_fna", "ping_batch"

    Type Parameters:
        TResult: Parser 產出的 Pydantic model 類型（必須是 ParsedData 子類別）
    """

    # ── 子類別必須設定的 class attributes ──
    device_type: DeviceType | None  # None = generic parser (all device types)
    command: str  # API name, e.g., "get_fan_hpe_dna"

    @abstractmethod
    def parse(self, raw_output: str) -> list[TResult]:
        """
        將原始 CLI 輸出解析為結構化資料。

        Args:
            raw_output: Fetcher 從設備取回的原始 CLI 輸出字串。
                       可能包含表頭、分隔線、空行等，parser 需要自行過濾。

        Returns:
            list[TResult]: 解析後的資料列表。
                          - 正常：回傳一或多筆資料
                          - 無資料：回傳空列表 []（不是 error）
                          - 不要 raise exception，遇到無法解析的行就 continue 跳過
        """
        ...

    def can_parse(self, raw_output: str) -> bool:
        """
        檢查此 parser 是否能處理給定的輸出（可選覆寫）。

        預設回傳 True。若你的 parser 需要先判斷格式是否正確，
        可以覆寫此方法做前置檢查。

        Args:
            raw_output: 原始 CLI 輸出字串

        Returns:
            bool: True 表示此 parser 可以處理此輸出
        """
        return True


class ParserKey(BaseModel):
    """
    Parser 在 registry 中的唯一識別鍵。

    由兩個維度組成：device_type + command。

    舉例：
        ParserKey(device_type=DeviceType.HPE, command="get_fan_hpe_dna")
        → 對應 GetFanHpeDnaParser
    """

    device_type: DeviceType | None
    command: str

    def __hash__(self) -> int:
        """Make hashable for use as dict key."""
        return hash((self.device_type, self.command))

    def __eq__(self, other: object) -> bool:
        """Equality comparison."""
        if not isinstance(other, ParserKey):
            return False
        return (
            self.device_type == other.device_type
            and self.command == other.command
        )
