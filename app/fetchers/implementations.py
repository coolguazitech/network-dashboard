"""
Real Fetcher 實作（使用者填入）。

每個 Fetcher 的 fetch() 方法目前拋出 NotImplementedError，
需根據實際外部 API 規格覆寫。

每個 Fetcher 的 docstring 包含：
- 說明此 Fetcher 應取得什麼資料
- 對應的 Parser 和 ParsedData 型別
- ctx.params 中可用的額外參數
- 範例實作（僅供參考，需依實際 API 調整）

USE_MOCK_API=false 時由 setup_fetchers() 自動註冊。
"""
from __future__ import annotations

from app.fetchers.base import BaseFetcher, FetchContext, FetchResult
from app.fetchers.registry import fetcher_registry


# ══════════════════════════════════════════════════════════════════
# Indicator Fetchers (8)
# ══════════════════════════════════════════════════════════════════


class TransceiverFetcher(BaseFetcher):
    """
    光模塊資料 Fetcher。

    外部 API 應回傳該 switch 上所有光模塊的 Tx/Rx 功率與溫度。

    回傳格式參考: app.fetchers.mock.MockTransceiverFetcher
    對應 Parser: HpeComwareTransceiverParser (vendor/platform-specific, via parser_registry)
    對應 ParsedData: TransceiverData (interface_name, tx_power, rx_power, temperature, ...)

    範例實作::

        async def fetch(self, ctx: FetchContext) -> FetchResult:
            resp = await ctx.http.get(
                f"{ctx.base_url}/api/v1/device/transceiver",
                params={"ip": ctx.switch_ip, "source": ctx.source},
            )
            resp.raise_for_status()
            return FetchResult(raw_output=resp.text)
    """

    fetch_type = "transceiver"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raise NotImplementedError(
            "TransceiverFetcher.fetch() 尚未實作。"
            "請覆寫此方法以呼叫你的外部 API。"
            "回傳格式請參考 MockTransceiverFetcher。"
        )


class VersionFetcher(BaseFetcher):
    """
    韌體版本 Fetcher。

    外部 API 應回傳該 switch 的韌體版本資訊。

    回傳格式參考: app.fetchers.mock.MockVersionFetcher
    對應 Parser: HpeVersionParser (via parser_registry)
    對應 ParsedData: VersionData (version, model, serial_number, uptime)

    範例實作::

        async def fetch(self, ctx: FetchContext) -> FetchResult:
            resp = await ctx.http.get(
                f"{ctx.base_url}/api/v1/device/version",
                params={"ip": ctx.switch_ip},
            )
            return FetchResult(raw_output=resp.text)
    """

    fetch_type = "version"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raise NotImplementedError(
            "VersionFetcher.fetch() 尚未實作。"
        )


class UplinkFetcher(BaseFetcher):
    """
    Uplink 鄰居 Fetcher。

    外部 API 應回傳該 switch 的 LLDP/CDP 鄰居資訊。

    回傳格式參考: app.fetchers.mock.MockUplinkFetcher
    對應 Parser: HpeComwareNeighborParser (via parser_registry)
    對應 ParsedData: NeighborData (local_interface, remote_hostname, remote_interface)

    範例實作::

        async def fetch(self, ctx: FetchContext) -> FetchResult:
            resp = await ctx.http.get(
                f"{ctx.base_url}/api/v1/device/neighbors",
                params={"ip": ctx.switch_ip},
            )
            return FetchResult(raw_output=resp.text)
    """

    fetch_type = "uplink"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raise NotImplementedError(
            "UplinkFetcher.fetch() 尚未實作。"
        )


class FanFetcher(BaseFetcher):
    """
    風扇狀態 Fetcher。

    外部 API 應回傳該 switch 上所有風扇的狀態。

    回傳格式參考: app.fetchers.mock.MockFanFetcher
    對應 Parser: HpeFanParser (via parser_registry)
    對應 ParsedData: FanStatusData (fan_id, status, speed_rpm)
    """

    fetch_type = "fan"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raise NotImplementedError("FanFetcher.fetch() 尚未實作。")


class PowerFetcher(BaseFetcher):
    """
    電源供應器 Fetcher。

    外部 API 應回傳該 switch 上所有 PSU 的狀態。

    回傳格式參考: app.fetchers.mock.MockPowerFetcher
    對應 Parser: HpePowerParser (via parser_registry)
    對應 ParsedData: PowerData (ps_id, status, capacity_watts)
    """

    fetch_type = "power"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raise NotImplementedError("PowerFetcher.fetch() 尚未實作。")


class ErrorCountFetcher(BaseFetcher):
    """
    介面錯誤計數 Fetcher。

    外部 API 應回傳該 switch 上所有介面的錯誤計數。

    回傳格式參考: app.fetchers.mock.MockErrorCountFetcher
    對應 Parser: HpeErrorParser (via parser_registry)
    對應 ParsedData: InterfaceErrorData (interface_name, crc_errors, input_errors, output_errors)
    """

    fetch_type = "error_count"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raise NotImplementedError("ErrorCountFetcher.fetch() 尚未實作。")


class PortChannelFetcher(BaseFetcher):
    """
    Port-Channel / LAG 狀態 Fetcher。

    外部 API 應回傳該 switch 上所有 Port-Channel 的成員狀態。

    回傳格式參考: app.fetchers.mock.MockPortChannelFetcher
    對應 Parser: HpePortChannelParser (via parser_registry)
    對應 ParsedData: PortChannelData (interface_name, status, members, member_status)
    """

    fetch_type = "port_channel"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raise NotImplementedError("PortChannelFetcher.fetch() 尚未實作。")


class PingFetcher(BaseFetcher):
    """
    設備連通性 Ping Fetcher。

    外部 API 應回傳 ping 該 switch 的結果。

    回傳格式參考: app.fetchers.mock.MockPingFetcher
    對應 Parser: HpePingParser / CiscoNxosPingParser (via parser_registry)
    對應 ParsedData: PingData (target, is_reachable, success_rate)
    """

    fetch_type = "ping"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raise NotImplementedError("PingFetcher.fetch() 尚未實作。")


# ══════════════════════════════════════════════════════════════════
# Client Fetchers (5)
# ══════════════════════════════════════════════════════════════════


class MacTableFetcher(BaseFetcher):
    """
    MAC 表 Fetcher。

    外部 API 應回傳該 switch 上所有 MAC 位址及其所在 port / VLAN。

    回傳格式參考: app.fetchers.mock.MockMacTableFetcher
    對應 Parser: MacTableParser (app.parsers.client_parsers)
    對應 ParsedData: MacTableData (mac_address, interface_name, vlan_id)

    範例實作::

        async def fetch(self, ctx: FetchContext) -> FetchResult:
            resp = await ctx.http.get(
                f"{ctx.base_url}/api/v1/device/mac-table",
                params={"ip": ctx.switch_ip},
            )
            return FetchResult(raw_output=resp.text)
    """

    fetch_type = "mac_table"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raise NotImplementedError("MacTableFetcher.fetch() 尚未實作。")


class ArpTableFetcher(BaseFetcher):
    """
    ARP 表 Fetcher。

    外部 API 應回傳該 switch 上的 ARP 表（MAC ↔ IP 對應）。

    回傳格式參考: app.fetchers.mock.MockArpTableFetcher
    對應 Parser: ArpParser (app.parsers.client_parsers)
    對應 ParsedData: ArpData (ip_address, mac_address)
    """

    fetch_type = "arp_table"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raise NotImplementedError("ArpTableFetcher.fetch() 尚未實作。")


class InterfaceStatusFetcher(BaseFetcher):
    """
    介面狀態 Fetcher。

    外部 API 應回傳該 switch 上所有介面的狀態 / 速率 / 雙工模式。

    回傳格式參考: app.fetchers.mock.MockInterfaceStatusFetcher
    對應 Parser: InterfaceStatusParser (app.parsers.client_parsers)
    對應 ParsedData: InterfaceStatusData (interface_name, link_status, speed, duplex)
    """

    fetch_type = "interface_status"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raise NotImplementedError("InterfaceStatusFetcher.fetch() 尚未實作。")


class AclFetcher(BaseFetcher):
    """
    ACL 規則 Fetcher。

    外部 API 應回傳該 switch 上每個 port 套用的 ACL 編號。

    回傳格式參考: app.fetchers.mock.MockAclFetcher
    對應 Parser: AclParser (app.parsers.client_parsers)
    對應 ParsedData: AclData (interface_name, acl_number)
    """

    fetch_type = "acl"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raise NotImplementedError("AclFetcher.fetch() 尚未實作。")


class PingManyFetcher(BaseFetcher):
    """
    批量 Ping Fetcher。

    外部 API 應接收目標 IP 清單並回傳每個 IP 的可達性結果。

    ctx.params 可用參數:
        target_ips: list[str] — 要 ping 的目標 IP 清單

    回傳格式參考: app.fetchers.mock.MockPingManyFetcher
    對應 Parser: PingManyParser (app.parsers.client_parsers)
    對應 ParsedData: PingManyData (ip_address, is_reachable)

    範例實作::

        async def fetch(self, ctx: FetchContext) -> FetchResult:
            target_ips = ctx.params.get("target_ips", [])
            resp = await ctx.http.post(
                f"{ctx.base_url}/api/v1/device/ping-many",
                json={"device_ip": ctx.switch_ip, "targets": target_ips},
            )
            return FetchResult(raw_output=resp.text)
    """

    fetch_type = "ping_many"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        raise NotImplementedError("PingManyFetcher.fetch() 尚未實作。")


# ══════════════════════════════════════════════════════════════════
# Registration
# ══════════════════════════════════════════════════════════════════

_ALL_REAL_FETCHERS: list[type[BaseFetcher]] = [
    # Indicator (8)
    TransceiverFetcher,
    VersionFetcher,
    UplinkFetcher,
    FanFetcher,
    PowerFetcher,
    ErrorCountFetcher,
    PortChannelFetcher,
    PingFetcher,
    # Client (5)
    MacTableFetcher,
    ArpTableFetcher,
    InterfaceStatusFetcher,
    AclFetcher,
    PingManyFetcher,
]


def register_real_fetchers() -> None:
    """註冊所有 real fetcher 到全域 registry。"""
    for cls in _ALL_REAL_FETCHERS:
        fetcher_registry.register(cls())
