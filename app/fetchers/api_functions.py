"""
外部 API 函數封裝。

每個 function 封裝對一個外部 API source 的 HTTP 呼叫。
Fetcher 透過呼叫這些 function 取得 raw output。

API 來源分類：
    FNA (4): transceiver, port_channel, arp_table, acl
    DNA (7): version, uplink, fan, power, error_count, mac_table, interface_status
    GNMSPing (1): ping (支援單一或批量)

FNA functions — 只需 switch_ip:
    async def get_X_from_fna(switch_ip: str, **kwargs) -> str

DNA functions — 需要 vendor_os + switch_ip:
    async def get_X_from_dna(vendor_os: str, switch_ip: str, **kwargs) -> str

GNMSPing functions — 需要 target_ips:
    async def ping_from_gnms(target_ips: list[str], **kwargs) -> str

目前為 stub（raise NotImplementedError），日後依實際 API 實作。
"""
from __future__ import annotations


# ══════════════════════════════════════════════════════════════════
# FNA Functions (4)
#
# FNA (Factory Network Automation) 內部自動偵測廠牌，
# 只需 switch_ip，不需 vendor_os。
# ══════════════════════════════════════════════════════════════════


async def get_transceiver_from_fna(
    switch_ip: str, **kwargs: object,
) -> str:
    """
    從 FNA 取得光模塊資料（Tx/Rx 功率、溫度）。

    Args:
        switch_ip: 目標 switch IP
        **kwargs: 保留給未來擴充

    Returns:
        str: API 回傳的原始字串（交給 Parser 解析）
    """
    raise NotImplementedError(
        "get_transceiver_from_fna() 尚未實作。"
    )


async def get_port_channel_from_fna(
    switch_ip: str, **kwargs: object,
) -> str:
    """
    從 FNA 取得 Port-Channel / LAG 狀態資料。

    Args:
        switch_ip: 目標 switch IP
        **kwargs: 保留給未來擴充

    Returns:
        str: API 回傳的原始字串（交給 Parser 解析）
    """
    raise NotImplementedError(
        "get_port_channel_from_fna() 尚未實作。"
    )


async def get_arp_table_from_fna(
    switch_ip: str, **kwargs: object,
) -> str:
    """
    從 FNA 取得 ARP 表資料。

    Args:
        switch_ip: 目標 switch IP
        **kwargs: 保留給未來擴充

    Returns:
        str: API 回傳的原始字串（交給 Parser 解析）
    """
    raise NotImplementedError(
        "get_arp_table_from_fna() 尚未實作。"
    )


async def get_acl_from_fna(
    switch_ip: str, **kwargs: object,
) -> str:
    """
    從 FNA 取得 ACL 規則資料。

    Args:
        switch_ip: 目標 switch IP
        **kwargs: 保留給未來擴充
            interfaces (list[str]): 要查詢 ACL 的介面清單

    Returns:
        str: API 回傳的原始字串（交給 Parser 解析）
    """
    raise NotImplementedError(
        "get_acl_from_fna() 尚未實作。"
    )


# ══════════════════════════════════════════════════════════════════
# DNA Functions (7)
#
# DNA (Device Network Automation) 需要指定 vendor_os（設備廠牌）
# + switch_ip。
# ══════════════════════════════════════════════════════════════════


async def get_version_from_dna(
    vendor_os: str, switch_ip: str, **kwargs: object,
) -> str:
    """
    從 DNA 取得韌體版本資料。

    Args:
        vendor_os: 設備 vendor-os (e.g. "HPE", "Cisco-IOS")
        switch_ip: 目標 switch IP
        **kwargs: 保留給未來擴充

    Returns:
        str: API 回傳的原始字串（交給 Parser 解析）
    """
    raise NotImplementedError(
        "get_version_from_dna() 尚未實作。"
    )


async def get_uplink_from_dna(
    vendor_os: str, switch_ip: str, **kwargs: object,
) -> str:
    """
    從 DNA 取得 Uplink LLDP 鄰居資料。

    Args:
        vendor_os: 設備 vendor-os (e.g. "HPE", "Cisco-IOS")
        switch_ip: 目標 switch IP
        **kwargs: 保留給未來擴充

    Returns:
        str: API 回傳的原始字串（交給 Parser 解析）
    """
    raise NotImplementedError(
        "get_uplink_from_dna() 尚未實作。"
    )


async def get_fan_from_dna(
    vendor_os: str, switch_ip: str, **kwargs: object,
) -> str:
    """
    從 DNA 取得風扇狀態資料。

    Args:
        vendor_os: 設備 vendor-os (e.g. "HPE", "Cisco-IOS")
        switch_ip: 目標 switch IP
        **kwargs: 保留給未來擴充

    Returns:
        str: API 回傳的原始字串（交給 Parser 解析）
    """
    raise NotImplementedError(
        "get_fan_from_dna() 尚未實作。"
    )


async def get_power_from_dna(
    vendor_os: str, switch_ip: str, **kwargs: object,
) -> str:
    """
    從 DNA 取得電源供應器狀態資料。

    Args:
        vendor_os: 設備 vendor-os (e.g. "HPE", "Cisco-IOS")
        switch_ip: 目標 switch IP
        **kwargs: 保留給未來擴充

    Returns:
        str: API 回傳的原始字串（交給 Parser 解析）
    """
    raise NotImplementedError(
        "get_power_from_dna() 尚未實作。"
    )


async def get_error_count_from_dna(
    vendor_os: str, switch_ip: str, **kwargs: object,
) -> str:
    """
    從 DNA 取得介面錯誤計數資料。

    Args:
        vendor_os: 設備 vendor-os (e.g. "HPE", "Cisco-IOS")
        switch_ip: 目標 switch IP
        **kwargs: 保留給未來擴充

    Returns:
        str: API 回傳的原始字串（交給 Parser 解析）
    """
    raise NotImplementedError(
        "get_error_count_from_dna() 尚未實作。"
    )


async def get_mac_table_from_dna(
    vendor_os: str, switch_ip: str, **kwargs: object,
) -> str:
    """
    從 DNA 取得 MAC 表資料。

    Args:
        vendor_os: 設備 vendor-os (e.g. "HPE", "Cisco-IOS")
        switch_ip: 目標 switch IP
        **kwargs: 保留給未來擴充

    Returns:
        str: API 回傳的原始字串（交給 Parser 解析）
    """
    raise NotImplementedError(
        "get_mac_table_from_dna() 尚未實作。"
    )


async def get_interface_status_from_dna(
    vendor_os: str, switch_ip: str, **kwargs: object,
) -> str:
    """
    從 DNA 取得介面狀態資料。

    Args:
        vendor_os: 設備 vendor-os (e.g. "HPE", "Cisco-IOS")
        switch_ip: 目標 switch IP
        **kwargs: 保留給未來擴充

    Returns:
        str: API 回傳的原始字串（交給 Parser 解析）
    """
    raise NotImplementedError(
        "get_interface_status_from_dna() 尚未實作。"
    )


# ══════════════════════════════════════════════════════════════════
# GNMSPing Functions (1)
#
# GNMS Ping API - 批量 Ping 多個 IP，不需 vendor_os。
# ══════════════════════════════════════════════════════════════════


async def ping_from_gnms(
    target_ips: list[str], **kwargs: object,
) -> str:
    """
    從 GNMS Ping API 批量 Ping 多個目標 IP。

    Args:
        target_ips: 要 ping 的目標 IP 清單
        **kwargs: 保留給未來擴充
            tenant_group (str): 租戶群組

    Returns:
        str: API 回傳的原始字串（交給 Parser 解析）
            格式: "IP,Reachable\\n192.168.1.1,true\\n..."
    """
    raise NotImplementedError(
        "ping_from_gnms() 尚未實作。"
    )
