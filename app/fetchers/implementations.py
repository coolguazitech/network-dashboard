"""
Real Fetcher 實作。

每個 Fetcher 繼承 BaseFetcher，在 fetch() 中呼叫對應的 API function。
API function 定義在 app.fetchers.api_functions，每個 function 綁定
恰好一個外部 API source。

API 來源分類：
    FNA (4): transceiver, port_channel, arp_table, acl
    DNA (7): version, uplink, fan, power, error_count, mac_table, interface_status
    GNMSPing (1): ping

重要設計：Fetcher 與廠牌無關。
  - 一個 fetch_type 只有一個 Fetcher
  - 廠牌差異由 Service 層透過 parser_registry 選擇對應 Parser
  - Fetcher 只負責呼叫 API function 拿到 raw_output

USE_MOCK_API=false 時由 setup_fetchers() 自動註冊。
"""
from __future__ import annotations

from app.fetchers.api_functions import (
    # FNA
    get_transceiver_from_fna,
    get_port_channel_from_fna,
    get_arp_table_from_fna,
    get_acl_from_fna,
    # DNA
    get_version_from_dna,
    get_uplink_from_dna,
    get_fan_from_dna,
    get_power_from_dna,
    get_error_count_from_dna,
    get_mac_table_from_dna,
    get_interface_status_from_dna,
    # GNMSPing
    ping_from_gnms,
)
from app.fetchers.base import BaseFetcher, FetchContext, FetchResult
from app.fetchers.registry import fetcher_registry


# ══════════════════════════════════════════════════════════════════
# FNA Fetchers (4)
#
# FNA (Factory Network Automation) 內部自動偵測廠牌，只需 switch_ip。
# ══════════════════════════════════════════════════════════════════


class TransceiverFetcher(BaseFetcher):
    """
    光模塊資料 Fetcher（FNA）。

    外部 API 應回傳該 switch 上所有光模塊的 Tx/Rx 功率與溫度。
    此 Fetcher 同時服務所有廠牌（HPE / Cisco / ...），
    廠牌差異由 parser_registry 根據 vendor + platform 選擇對應 Parser。

    回傳格式參考: app.fetchers.mock.MockTransceiverFetcher
    對應 Parser（由 parser_registry 依 vendor/platform 自動選擇）:
        - HPE Comware  → HpeComwareTransceiverParser
        - Cisco IOS    → CiscoIosTransceiverParser
        - Cisco NX-OS  → CiscoNxosTransceiverParser
    對應 ParsedData: TransceiverData
    """

    fetch_type = "transceiver"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raw = await get_transceiver_from_fna(ctx.switch_ip)
        return FetchResult(raw_output=raw)


class PortChannelFetcher(BaseFetcher):
    """
    Port-Channel / LAG 狀態 Fetcher（FNA）。

    回傳格式參考: app.fetchers.mock.MockPortChannelFetcher
    對應 Parser: HpePortChannelParser / CiscoNxosPortChannelParser
    對應 ParsedData: PortChannelData
    """

    fetch_type = "port_channel"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raw = await get_port_channel_from_fna(ctx.switch_ip)
        return FetchResult(raw_output=raw)


class ArpTableFetcher(BaseFetcher):
    """
    ARP 表 Fetcher（FNA）。

    回傳格式參考: app.fetchers.mock.MockArpTableFetcher
    對應 Parser: ArpParser
    對應 ParsedData: ArpData
    """

    fetch_type = "arp_table"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raw = await get_arp_table_from_fna(ctx.switch_ip)
        return FetchResult(raw_output=raw)


class AclFetcher(BaseFetcher):
    """
    ACL 規則 Fetcher（FNA）。

    ctx.params 可用參數:
        interfaces: list[str] — 要查詢 ACL 的介面清單

    回傳格式參考: app.fetchers.mock.MockAclFetcher
    對應 Parser: AclParser
    對應 ParsedData: AclData
    """

    fetch_type = "acl"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        interfaces = ctx.params.get("interfaces", [])
        raw = await get_acl_from_fna(ctx.switch_ip, interfaces=interfaces)
        return FetchResult(raw_output=raw)


# ══════════════════════════════════════════════════════════════════
# DNA Fetchers (7)
#
# DNA (Device Network Automation) 需要指定 vendor_os + switch_ip。
# ══════════════════════════════════════════════════════════════════


class VersionFetcher(BaseFetcher):
    """
    韌體版本 Fetcher（DNA）。

    回傳格式參考: app.fetchers.mock.MockVersionFetcher
    對應 Parser: HpeVersionParser (registry)
    對應 ParsedData: VersionData
    """

    fetch_type = "version"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raw = await get_version_from_dna(ctx.brand or "", ctx.switch_ip)
        return FetchResult(raw_output=raw)


class UplinkFetcher(BaseFetcher):
    """
    Uplink 鄰居 Fetcher（DNA）。

    回傳格式參考: app.fetchers.mock.MockUplinkFetcher
    對應 Parser: HpeComwareNeighborParser / CiscoIosNeighborParser
    對應 ParsedData: NeighborData
    """

    fetch_type = "uplink"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raw = await get_uplink_from_dna(ctx.brand or "", ctx.switch_ip)
        return FetchResult(raw_output=raw)


class FanFetcher(BaseFetcher):
    """
    風扇狀態 Fetcher（DNA）。

    回傳格式參考: app.fetchers.mock.MockFanFetcher
    對應 Parser: HpeFanParser / CiscoNxosFanParser (registry)
    對應 ParsedData: FanStatusData
    """

    fetch_type = "fan"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raw = await get_fan_from_dna(ctx.brand or "", ctx.switch_ip)
        return FetchResult(raw_output=raw)


class PowerFetcher(BaseFetcher):
    """
    電源供應器 Fetcher（DNA）。

    回傳格式參考: app.fetchers.mock.MockPowerFetcher
    對應 Parser: HpePowerParser / CiscoNxosPowerParser (registry)
    對應 ParsedData: PowerData
    """

    fetch_type = "power"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raw = await get_power_from_dna(ctx.brand or "", ctx.switch_ip)
        return FetchResult(raw_output=raw)


class ErrorCountFetcher(BaseFetcher):
    """
    介面錯誤計數 Fetcher（DNA）。

    回傳格式參考: app.fetchers.mock.MockErrorCountFetcher
    對應 Parser: HpeErrorParser / CiscoNxosErrorParser (registry)
    對應 ParsedData: InterfaceErrorData
    """

    fetch_type = "error_count"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raw = await get_error_count_from_dna(ctx.brand or "", ctx.switch_ip)
        return FetchResult(raw_output=raw)


class MacTableFetcher(BaseFetcher):
    """
    MAC 表 Fetcher（DNA）。

    回傳格式參考: app.fetchers.mock.MockMacTableFetcher
    對應 Parser: MacTableParser
    對應 ParsedData: MacTableData
    """

    fetch_type = "mac_table"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raw = await get_mac_table_from_dna(ctx.brand or "", ctx.switch_ip)
        return FetchResult(raw_output=raw)


class InterfaceStatusFetcher(BaseFetcher):
    """
    介面狀態 Fetcher（DNA）。

    回傳格式參考: app.fetchers.mock.MockInterfaceStatusFetcher
    對應 Parser: InterfaceStatusParser
    對應 ParsedData: InterfaceStatusData
    """

    fetch_type = "interface_status"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raw = await get_interface_status_from_dna(ctx.brand or "", ctx.switch_ip)
        return FetchResult(raw_output=raw)


# ══════════════════════════════════════════════════════════════════
# GNMSPing Fetcher (1)
#
# GNMS Ping API - 批量 Ping 多個 IP，不需 vendor_os。
# ══════════════════════════════════════════════════════════════════


class PingFetcher(BaseFetcher):
    """
    批量 Ping Fetcher（GNMSPing）。

    ctx.params 可用參數:
        target_ips: list[str] — 要 ping 的目標 IP 清單
        tenant_group: str — 租戶群組

    回傳格式參考: app.fetchers.mock.MockPingFetcher
    對應 Parser: PingParser
    對應 ParsedData: PingData
    """

    fetch_type = "ping"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        target_ips = ctx.params.get("target_ips", [])
        if not target_ips:
            # 若未指定 target_ips，預設 ping switch 本身
            target_ips = [ctx.switch_ip]
        raw = await ping_from_gnms(target_ips)
        return FetchResult(raw_output=raw)


# ══════════════════════════════════════════════════════════════════
# Registration
# ══════════════════════════════════════════════════════════════════

_ALL_REAL_FETCHERS: list[type[BaseFetcher]] = [
    # FNA (4)
    TransceiverFetcher,
    PortChannelFetcher,
    ArpTableFetcher,
    AclFetcher,
    # DNA (7)
    VersionFetcher,
    UplinkFetcher,
    FanFetcher,
    PowerFetcher,
    ErrorCountFetcher,
    MacTableFetcher,
    InterfaceStatusFetcher,
    # GNMSPing (1)
    PingFetcher,
]


def register_real_fetchers() -> None:
    """註冊所有 real fetcher 到全域 registry。"""
    for cls in _ALL_REAL_FETCHERS:
        fetcher_registry.register(cls())
