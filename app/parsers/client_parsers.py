"""
Client data parsers.

將 Fetcher 回傳的原始資料解析為結構化的 Pydantic 模型。
這些 parser 不走 vendor/platform registry，因為 Fetcher 已處理廠牌差異。

使用方式：
    parser = MacTableParser()
    entries = parser.parse(raw_output)

填寫說明：
    每個 parser 的 parse() 方法目前是 TODO placeholder。
    當 Fetcher 實作完成後，根據 Fetcher 的實際回傳格式填入解析邏輯。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

from app.parsers.protocols import (
    AclData,
    ArpData,
    InterfaceStatusData,
    MacTableData,
    PingManyData,
)

T = TypeVar("T", bound=BaseModel)


class BaseFetcherParser(ABC):
    """Fetcher parser 的基底類別。"""

    @abstractmethod
    def parse(self, raw_output: str) -> list:
        """解析 Fetcher 回傳的原始字串。"""
        ...


# ── MAC Table ────────────────────────────────────────────────────


class MacTableParser(BaseFetcherParser):
    """
    解析 Fetcher `get_mac_table` 的回傳。

    Fetcher 回傳: 該 switch 上所有 MAC 地址及其所在 port / VLAN。
    產出: list[MacTableData]
    用途: 建立 MAC → (interface, vlan) 對應，作為 ClientRecord 的基礎。
    """

    def parse(self, raw_output: str) -> list[MacTableData]:
        # TODO: 根據 Fetcher 實際回傳格式實作解析邏輯
        # 預期每筆包含: mac_address, interface_name, vlan_id
        raise NotImplementedError(
            "MacTableParser.parse() 需等 Fetcher 完成後實作"
        )


# ── ARP Table ────────────────────────────────────────────────────


class ArpParser(BaseFetcherParser):
    """
    解析 Fetcher `get_arp_table` 的回傳。

    Fetcher 回傳: 該 switch 上的 ARP 表（MAC ↔ IP 對應）。
    產出: list[ArpData]
    用途: 為 MAC 地址關聯 IP 地址。
    """

    def parse(self, raw_output: str) -> list[ArpData]:
        # TODO: 根據 Fetcher 實際回傳格式實作解析邏輯
        # 預期每筆包含: ip_address, mac_address
        raise NotImplementedError(
            "ArpParser.parse() 需等 Fetcher 完成後實作"
        )


# ── Interface Status ─────────────────────────────────────────────


class InterfaceStatusParser(BaseFetcherParser):
    """
    解析 Fetcher `get_interface_status` 的回傳。

    Fetcher 回傳: 該 switch 上所有介面的狀態 / 速率 / 雙工。
    產出: list[InterfaceStatusData]
    用途: 填入 ClientRecord 的 speed, duplex, link_status。
    """

    def parse(self, raw_output: str) -> list[InterfaceStatusData]:
        # TODO: 根據 Fetcher 實際回傳格式實作解析邏輯
        # 預期每筆包含: interface_name, link_status, speed, duplex
        raise NotImplementedError(
            "InterfaceStatusParser.parse() 需等 Fetcher 完成後實作"
        )


# ── ACL Number ───────────────────────────────────────────────────


class AclParser(BaseFetcherParser):
    """
    解析 Fetcher `get_acl_number` 的回傳。

    Fetcher 回傳: 該 switch 上每個 port 套用的 ACL 編號。
    （Fetcher 內部已處理 per-interface 迴圈，回傳聚合結果）
    產出: list[AclData]
    用途: 填入 ClientRecord 的 acl_rules_applied, acl_passes。
    """

    def parse(self, raw_output: str) -> list[AclData]:
        # TODO: 根據 Fetcher 實際回傳格式實作解析邏輯
        # 預期每筆包含: interface_name, acl_number (None = 未套用)
        raise NotImplementedError(
            "AclParser.parse() 需等 Fetcher 完成後實作"
        )


# ── Ping Many ────────────────────────────────────────────────────


class PingManyParser(BaseFetcherParser):
    """
    解析 Fetcher `ping_many` 的回傳。

    Fetcher 回傳: 批量 ping 多個客戶端 IP 的結果。
    產出: list[PingManyData]
    用途: 填入 ClientRecord 的 ping_reachable。
    """

    def parse(self, raw_output: str) -> list[PingManyData]:
        # TODO: 根據 Fetcher 實際回傳格式實作解析邏輯
        # 預期每筆包含: ip_address, is_reachable
        raise NotImplementedError(
            "PingManyParser.parse() 需等 Fetcher 完成後實作"
        )
