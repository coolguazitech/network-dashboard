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
    TransceiverData   - 光模組診斷（Tx/Rx 功率、溫度、電壓）
    InterfaceErrorData - 介面錯誤計數器（CRC、input/output errors）
    FanStatusData     - 風扇狀態（status 自動正規化為 OperationalStatus）
    VersionData       - 韌體版本（version, model, serial_number）
    NeighborData      - 鄰居資訊（CDP/LLDP）
    PortChannelData   - Port-Channel/LAG 資訊（成員、狀態、協議）
    PowerData         - 電源供應器狀態
    PingData          - Ping 可達性結果
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


class TransceiverData(ParsedData):
    """光模組 (Transceiver) 診斷資料。"""

    interface_name: str
    tx_power: float | None = Field(None, ge=-40.0, le=10.0, description="發射功率 (dBm)")
    rx_power: float | None = Field(None, ge=-40.0, le=10.0, description="接收功率 (dBm)")
    temperature: float | None = Field(None, ge=-10.0, le=100.0, description="溫度 (°C)")
    voltage: float | None = Field(None, ge=0.0, le=10.0, description="電壓 (V)")


class InterfaceErrorData(ParsedData):
    """介面錯誤計數器。"""

    interface_name: str
    crc_errors: int = Field(0, ge=0)
    input_errors: int = Field(0, ge=0)
    output_errors: int = Field(0, ge=0)
    collisions: int = Field(0, ge=0)
    giants: int = Field(0, ge=0)
    runts: int = Field(0, ge=0)


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


class PingData(ParsedData):
    """設備 Ping 可達性資料。"""

    target: str
    is_reachable: bool
    success_rate: float = Field(ge=0.0, le=100.0, description="成功率 0-100%")
    avg_rtt_ms: float | None = Field(None, ge=0.0)


# ── Client Fetcher 中間資料模型 ──────────────────────────────────


class MacTableData(ParsedData):
    """Fetcher get_mac_table 的解析結果。"""

    mac_address: str = Field(description="正規化為 AA:BB:CC:DD:EE:FF")
    interface_name: str
    vlan_id: int = Field(ge=1, le=4094)

    @field_validator("mac_address", mode="before")
    @classmethod
    def normalize_mac(cls, v: str) -> str:
        return _normalize_mac(v)


class ArpData(ParsedData):
    """Fetcher get_arp_table 的解析結果。"""

    ip_address: str
    mac_address: str

    @field_validator("ip_address", mode="before")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        return _validate_ipv4(v)

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


class PingManyData(ParsedData):
    """Fetcher ping_many 的解析結果。"""

    ip_address: str
    is_reachable: bool

    @field_validator("ip_address", mode="before")
    @classmethod
    def validate_ip(cls, v: str) -> str:
        return _validate_ipv4(v)


# ── Parser Base ──────────────────────────────────────────────────


class BaseParser(ABC, Generic[TResult]):
    """
    所有 Parser 的抽象基底類別 — 每個 Parser 負責「一個設備類型 + 一種指標」。

    =========================================================================
    如何新增一個 Parser（保姆級步驟）：
    =========================================================================

    第 1 步：建立檔案
        在 app/parsers/plugins/ 目錄下建立新檔案。
        命名慣例：{vendor}_{indicator_type}.py
        範例：hpe_version.py, cisco_ios_transceiver.py

    第 2 步：定義 Parser 類別
        繼承 BaseParser[你的 ParsedData 子類別]，設定三個必填 class attribute，
        然後實作 parse() 方法。

        .. code-block:: python

            from app.core.enums import DeviceType
            from app.parsers.protocols import BaseParser, TransceiverData
            from app.parsers.registry import parser_registry

            class HpeTransceiverParser(BaseParser[TransceiverData]):
                # ── 必填 class attributes ──
                device_type = DeviceType.HPE         # 設備類型（見 app/core/enums.py）
                indicator_type = "transceiver"        # 指標類型，必須與 scheduler.yaml
                                                      #   的 fetcher name 一致！
                command = "display transceiver"       # 對應的 CLI 指令（供文檔參考）

                def parse(self, raw_output: str) -> list[TransceiverData]:
                    # raw_output 是 Fetcher 從設備取回的原始字串
                    results = []
                    # ... 你的解析邏輯 ...
                    return results

    第 3 步：註冊 Parser
        在檔案底部呼叫 parser_registry.register()：

        .. code-block:: python

            # 檔案最底部
            parser_registry.register(HpeTransceiverParser())

        然後在 app/parsers/plugins/__init__.py 加上 import：

        .. code-block:: python

            from . import hpe_transceiver  # 新增這行

    =========================================================================
    各 class attribute 說明：
    =========================================================================

    device_type : DeviceType | None
        設備類型。目前支援：HPE, CISCO_IOS, CISCO_NXOS。
        設為 None 表示此 Parser 為通用型，適用所有設備類型（如 Ping）。
        Registry 查詢時先精確匹配 device_type，再 fallback 到 None。
        若需新增設備類型，先在 app/core/enums.py 的 DeviceType 中加入。

    indicator_type : str
        指標類型字串。常見值：
        "transceiver", "fan", "power", "error_count", "version",
        "uplink", "port_channel", "ping"
        **重要**：此值必須與 scheduler.yaml 的 fetcher name 完全一致！
        fetcher name == indicator_type 是系統自動配對的關鍵。

    command : str
        對應的 CLI 指令，主要用於文檔參考和除錯時查閱。
        例如 "show interfaces transceiver", "display fan"。

    =========================================================================
    parse() 回傳值說明：
    =========================================================================

    - 回傳 list[TResult]：正常情況下回傳解析出的資料列表。
    - 回傳空列表 []：表示「沒有找到資料」，這不是 error！
      例如 transceiver parser 在一台沒有光模組的設備上跑，
      會回傳 []（空列表），下游 indicator 會處理「無資料」的情況。
    - 不要拋出例外：如果某行解析失敗，跳過該行即可（continue）。
      只有整個 raw_output 格式完全錯誤時才考慮 raise。

    =========================================================================
    ParsedData 驗證機制（你不需要自己做正規化！）：
    =========================================================================

    ParsedData 的 Pydantic before-validator 會自動幫你處理：
    - FanStatusData.status: "OK" → "ok", "Normal" → "normal"
    - PortChannelData.status: "UP" → "up", "DOWN" → "down"
    - PowerData.status: "Ok" → "ok", "Fail" → "fail"
    - MacTableData.mac_address: "0012.3456.789a" → "00:12:34:56:78:9A"
    所以 parser 只需把原始字串塞進去，Pydantic 會自動正規化。

    Type Parameters:
        TResult: Parser 產出的 Pydantic model 類型（必須是 ParsedData 子類別）
    """

    # ── 子類別必須設定的 class attributes ──
    device_type: DeviceType | None  # None = generic parser (all device types)
    indicator_type: str  # e.g., "transceiver", "error_count"
    command: str  # CLI command to execute

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

    由兩個維度組成：device_type + indicator_type。
    這代表「一個 ParserKey 對應一個 Parser」的 1:1 關係。

    舉例：
        ParserKey(device_type=DeviceType.CISCO_NXOS, indicator_type="transceiver")
        → 對應 CiscoNxosTransceiverParser

    系統使用 ParserKey 來查找正確的 Parser：
        1. DataCollectionService 拿到設備的 device_type
        2. 加上要採集的 indicator_type（如 "transceiver"）
        3. 組成 ParserKey 向 registry 查詢
        4. 找到對應的 Parser 實例，呼叫 parser.parse(raw_output)
    """

    device_type: DeviceType | None
    indicator_type: str

    def __hash__(self) -> int:
        """Make hashable for use as dict key."""
        return hash((self.device_type, self.indicator_type))

    def __eq__(self, other: object) -> bool:
        """Equality comparison."""
        if not isinstance(other, ParserKey):
            return False
        return (
            self.device_type == other.device_type
            and self.indicator_type == other.indicator_type
        )
