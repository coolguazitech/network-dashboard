"""
Client data parsers.

將 Fetcher 回傳的原始資料解析為結構化的 Pydantic 模型。
這些 parser 不走 vendor/platform registry，因為 Fetcher 已處理廠牌差異。

使用方式：
    parser = MacTableParser()
    entries = parser.parse(raw_output)

格式說明：
    所有 Mock Fetcher 都回傳 CSV 格式，第一行為 header。
    各 parser 負責解析對應格式並轉換為 Pydantic 模型。
"""
from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from io import StringIO
from typing import TypeVar

from pydantic import BaseModel

from app.parsers.protocols import (
    AclData,
    ArpData,
    InterfaceStatusData,
    MacTableData,
    PingResultData,
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

    Fetcher 回傳格式 (CSV):
        MAC,Interface,VLAN
        AA:BB:CC:XX:XX:XX,GE1/0/1,100

    產出: list[MacTableData]
    用途: 建立 MAC → (interface, vlan) 對應，作為 ClientRecord 的基礎。
    """

    def parse(self, raw_output: str) -> list[MacTableData]:
        if not raw_output or not raw_output.strip():
            return []

        entries: list[MacTableData] = []
        reader = csv.DictReader(StringIO(raw_output))

        for row in reader:
            mac = row.get("MAC", "").strip()
            interface = row.get("Interface", "").strip()
            vlan_str = row.get("VLAN", "").strip()

            if not mac or not interface:
                continue

            vlan_id = int(vlan_str) if vlan_str.isdigit() else None

            entries.append(MacTableData(
                mac_address=mac,
                interface_name=interface,
                vlan_id=vlan_id,
            ))

        return entries


# ── ARP Table ────────────────────────────────────────────────────


class ArpParser(BaseFetcherParser):
    """
    解析 Fetcher `get_arp_table` 的回傳。

    Fetcher 回傳格式 (CSV):
        IP,MAC
        10.0.1.101,AA:BB:CC:XX:XX:XX

    產出: list[ArpData]
    用途: 為 MAC 地址關聯 IP 地址。
    """

    def parse(self, raw_output: str) -> list[ArpData]:
        if not raw_output or not raw_output.strip():
            return []

        entries: list[ArpData] = []
        reader = csv.DictReader(StringIO(raw_output))

        for row in reader:
            ip = row.get("IP", "").strip()
            mac = row.get("MAC", "").strip()

            if not ip or not mac:
                continue

            entries.append(ArpData(
                ip_address=ip,
                mac_address=mac,
            ))

        return entries


# ── Interface Status ─────────────────────────────────────────────


class InterfaceStatusParser(BaseFetcherParser):
    """
    解析 Fetcher `get_interface_status` 的回傳。

    Fetcher 回傳格式 (CSV):
        Interface,Status,Speed,Duplex
        GE1/0/1,UP,10G,full

    產出: list[InterfaceStatusData]
    用途: 填入 ClientRecord 的 speed, duplex, link_status。
    """

    def parse(self, raw_output: str) -> list[InterfaceStatusData]:
        if not raw_output or not raw_output.strip():
            return []

        entries: list[InterfaceStatusData] = []
        reader = csv.DictReader(StringIO(raw_output))

        for row in reader:
            interface = row.get("Interface", "").strip()
            status = row.get("Status", "").strip()
            speed = row.get("Speed", "").strip()
            duplex = row.get("Duplex", "").strip()

            if not interface:
                continue

            entries.append(InterfaceStatusData(
                interface_name=interface,
                link_status=status or None,
                speed=speed or None,
                duplex=duplex or None,
            ))

        return entries


# ── ACL Number ───────────────────────────────────────────────────


class AclParser(BaseFetcherParser):
    """
    解析 Fetcher `get_acl_number` 的回傳。

    Fetcher 回傳格式 (CSV):
        Interface,ACL
        GE1/0/1,3001
        GE1/0/2,

    產出: list[AclData]
    用途: 填入 ClientRecord 的 acl_rules_applied, acl_passes。
    """

    def parse(self, raw_output: str) -> list[AclData]:
        if not raw_output or not raw_output.strip():
            return []

        entries: list[AclData] = []
        reader = csv.DictReader(StringIO(raw_output))

        for row in reader:
            interface = row.get("Interface", "").strip()
            acl = row.get("ACL", "").strip()

            if not interface:
                continue

            entries.append(AclData(
                interface_name=interface,
                acl_number=acl if acl else None,
            ))

        return entries


# ── Ping Many ────────────────────────────────────────────────────


class PingManyParser(BaseFetcherParser):
    """
    解析 Fetcher `ping_many` 的回傳。

    Fetcher 回傳格式 (CSV):
        IP,Reachable
        10.0.1.101,true
        10.0.1.102,false

    產出: list[PingResultData]
    用途: 填入 ClientRecord 的 ping_reachable。
    """

    def parse(self, raw_output: str) -> list[PingResultData]:
        if not raw_output or not raw_output.strip():
            return []

        entries: list[PingResultData] = []
        reader = csv.DictReader(StringIO(raw_output))

        for row in reader:
            ip = row.get("IP", "").strip()
            reachable_str = row.get("Reachable", "").strip().lower()

            if not ip:
                continue

            is_reachable = reachable_str in ("true", "1", "yes")

            entries.append(PingResultData(
                ip_address=ip,
                is_reachable=is_reachable,
            ))

        return entries
