"""
Mock Fetcher 實作。

提供 13 個 Mock Fetcher 用於開發與測試。
每個 Mock Fetcher 根據 switch_ip 產生確定性 (deterministic) 的模擬資料，
不需要外部 API Server。

USE_MOCK_API=true 時由 setup_fetchers() 自動註冊。
"""
from __future__ import annotations

import hashlib

from app.fetchers.base import BaseFetcher, FetchContext, FetchResult
from app.fetchers.registry import fetcher_registry


# ── Utility ────────────────────────────────────────────────────────


def _ip_hash(switch_ip: str, salt: str = "") -> int:
    """Deterministic hash from IP + salt for reproducible mock data."""
    digest = hashlib.md5(
        f"{switch_ip}:{salt}".encode(),
    ).hexdigest()
    return int(digest, 16)


# ══════════════════════════════════════════════════════════════════
# Indicator Fetchers (8)
# ══════════════════════════════════════════════════════════════════


class MockTransceiverFetcher(BaseFetcher):
    """Mock: HPE Comware 'display transceiver' output (~5% out-of-range)."""

    fetch_type = "transceiver"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        port_count = 6
        lines: list[str] = []

        for i in range(1, port_count + 1):
            ph = _ip_hash(ctx.switch_ip, f"xcvr-{i}")
            if ph % 20 == 0:
                tx, rx = -14.5, -20.1
            else:
                tx = -2.0 + (ph % 40) / 10.0 - 2.0
                rx = -5.0 + (ph % 60) / 10.0 - 3.0
            temp = 30.0 + (ph % 200) / 10.0

            lines.append(f"GigabitEthernet1/0/{i}")
            lines.append(f"  TX Power : {tx:.1f} dBm")
            lines.append(f"  RX Power : {rx:.1f} dBm")
            lines.append(f"  Temperature : {temp:.1f} C")
            lines.append("")

        return FetchResult(raw_output="\n".join(lines))


class MockVersionFetcher(BaseFetcher):
    """Mock: HPE Comware 'display version' output (~5% wrong version)."""

    fetch_type = "version"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        h = _ip_hash(ctx.switch_ip, "version")
        release = "6635P05" if h % 20 == 0 else "6635P07"

        output = (
            "HPE Comware Platform Software\n"
            f"Comware Software, Version 7.1.070, Release {release}\n"
            "Copyright (c) 2010-2024 Hewlett Packard Enterprise "
            "Development LP\n"
            "HPE FF 5710 48SFP+ 6QS 2SL Switch\n"
            "Uptime is 0 weeks, 1 day, 3 hours, 22 minutes\n"
        )
        return FetchResult(raw_output=output)


class MockUplinkFetcher(BaseFetcher):
    """Mock: HPE Comware 'display lldp neighbor-information' output (~5% missing neighbor)."""

    fetch_type = "uplink"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        h = _ip_hash(ctx.switch_ip, "neighbor")
        parts = ctx.switch_ip.split(".")
        third_octet = int(parts[2]) if len(parts) == 4 else 0
        dev_num = int(parts[-1]) if len(parts) == 4 else 1

        if third_octet == 2:
            neighbors = [
                ("SW-NEW-001-CORE", "HGE1/0/1"),
                ("SW-NEW-002-CORE", "HGE1/0/1"),
            ]
        elif third_octet == 3:
            edge_idx = dev_num - 11
            agg_num_1 = (edge_idx % 8) + 3
            agg_num_2 = ((edge_idx + 1) % 8) + 3
            neighbors = [
                (f"SW-NEW-{agg_num_1:03d}-AGG", f"XGE1/0/{edge_idx + 1}"),
                (f"SW-NEW-{agg_num_2:03d}-AGG", f"XGE1/0/{edge_idx + 1}"),
            ]
        else:
            neighbors = [
                ("SW-NEW-001-CORE", "HGE1/0/49"),
                ("SW-NEW-002-CORE", "HGE1/0/49"),
            ]

        if h % 20 == 0:
            neighbors = neighbors[:1]

        lines: list[str] = []
        for idx, (remote_host, remote_intf) in enumerate(neighbors):
            port_num = idx + 49
            lines.append(
                f"LLDP neighbor-information of port {port_num} "
                f"[GigabitEthernet1/0/{port_num}]:"
            )
            lines.append("  LLDP neighbor index       : 1")
            lines.append("  Chassis type              : MAC address")
            lines.append(
                f"  Chassis ID                : 0012-3456-78{dev_num:02x}"
            )
            lines.append("  Port ID type              : Interface name")
            lines.append(f"  Port ID                   : {remote_intf}")
            lines.append(f"  System name               : {remote_host}")
            lines.append(
                "  System description        : HPE Comware Platform Software"
            )
            lines.append("")

        return FetchResult(raw_output="\n".join(lines))


class MockFanFetcher(BaseFetcher):
    """Mock: HPE Comware 'display fan' output (~3% failed fan)."""

    fetch_type = "fan"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        h = _ip_hash(ctx.switch_ip, "fan")
        fan3_status = "Absent" if h % 30 == 0 else "Normal"

        output = (
            "Slot 1:\n"
            "FanID    Status      Direction\n"
            "1        Normal      Back-to-front\n"
            "2        Normal      Back-to-front\n"
            f"3        {fan3_status}      Back-to-front\n"
            "4        Normal      Back-to-front\n"
        )
        return FetchResult(raw_output=output)


class MockPowerFetcher(BaseFetcher):
    """Mock: HPE Comware 'display power' output (~5% failed PSU)."""

    fetch_type = "power"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        h = _ip_hash(ctx.switch_ip, "power")
        ps2_status = "Absent" if h % 20 == 0 else "Normal"

        output = (
            "Slot 1:\n"
            "PowerID State    Mode   Current(A)  Voltage(V)  "
            "Power(W)  FanDirection\n"
            "1       Normal   AC     --          --          "
            "--        Back-to-front\n"
            f"2       {ps2_status}   AC     --          --          "
            "--        Back-to-front\n"
        )
        return FetchResult(raw_output=output)


class MockErrorCountFetcher(BaseFetcher):
    """Mock: HPE Comware 'display counters error' output (~5% errors)."""

    fetch_type = "error_count"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        lines = [
            "Interface            Input(errs)       Output(errs)"
        ]
        for i in range(1, 21):
            ph = _ip_hash(ctx.switch_ip, f"err-{i}")
            if ph % 20 == 0:
                in_err = (ph % 10) + 1
                out_err = (ph % 5) + 1
            else:
                in_err = 0
                out_err = 0
            lines.append(
                f"GE1/0/{i}                        "
                f"{in_err}                  {out_err}"
            )
        return FetchResult(raw_output="\n".join(lines))


class MockPortChannelFetcher(BaseFetcher):
    """Mock: HPE Comware 'display link-aggregation summary' (~5% down member)."""

    fetch_type = "port_channel"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        h = _ip_hash(ctx.switch_ip, "port_channel")
        m1_status = "U" if h % 20 == 0 else "S"

        parts = ctx.switch_ip.split(".")
        third_octet = int(parts[2]) if len(parts) == 4 else 0

        if third_octet == 2:
            m1, m2 = "HGE1/0/25", "HGE1/0/26"
        else:
            m1, m2 = "XGE1/0/51", "XGE1/0/52"

        lines = [
            "AggID   Interface   Link   Attribute   Mode   Members",
            (
                f"1       BAGG1       UP     A           LACP   "
                f"{m1}({m1_status}) {m2}(S)"
            ),
        ]
        return FetchResult(raw_output="\n".join(lines))


class MockPingFetcher(BaseFetcher):
    """Mock: Standard ping output (~10% fail)."""

    fetch_type = "ping"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        h = _ip_hash(ctx.switch_ip, "ping")
        ip = ctx.switch_ip

        if h % 10 == 0:
            loss, received = 100, 0
        elif h % 15 == 0:
            loss, received = 40, 3
        else:
            loss, received = 0, 5

        output = (
            f"PING {ip} ({ip}): 56 data bytes\n"
            f"64 bytes from {ip}: icmp_seq=0 ttl=64 time=1.2 ms\n"
            f"64 bytes from {ip}: icmp_seq=1 ttl=64 time=1.1 ms\n"
            f"64 bytes from {ip}: icmp_seq=2 ttl=64 time=1.3 ms\n"
            "\n"
            f"--- {ip} ping statistics ---\n"
            f"5 packets transmitted, {received} packets received, "
            f"{loss}% packet loss\n"
            "round-trip min/avg/max = 1.1/1.2/1.3 ms\n"
        )
        return FetchResult(raw_output=output)


# ══════════════════════════════════════════════════════════════════
# Client Fetchers (5)
# ══════════════════════════════════════════════════════════════════


class MockMacTableFetcher(BaseFetcher):
    """Mock: MAC table (CSV format)."""

    fetch_type = "mac_table"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        lines = ["MAC,Interface,VLAN"]
        port_count = 12
        for i in range(1, port_count + 1):
            h = _ip_hash(ctx.switch_ip, f"mac-{i}")
            mac = f"AA:BB:CC:{h % 256:02X}:{(h >> 8) % 256:02X}:{i:02X}"
            vlan = 100 + (h % 5) * 10
            lines.append(f"{mac},GE1/0/{i},{vlan}")
        return FetchResult(raw_output="\n".join(lines))


class MockArpTableFetcher(BaseFetcher):
    """Mock: ARP table (CSV format)."""

    fetch_type = "arp_table"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        lines = ["IP,MAC"]
        port_count = 12
        base_parts = ctx.switch_ip.rsplit(".", 1)
        base_prefix = base_parts[0] if len(base_parts) == 2 else "10.0.0"
        for i in range(1, port_count + 1):
            h = _ip_hash(ctx.switch_ip, f"mac-{i}")
            mac = f"AA:BB:CC:{h % 256:02X}:{(h >> 8) % 256:02X}:{i:02X}"
            ip = f"{base_prefix}.{100 + i}"
            lines.append(f"{ip},{mac}")
        return FetchResult(raw_output="\n".join(lines))


class MockInterfaceStatusFetcher(BaseFetcher):
    """Mock: Interface status (CSV format, ~4% DOWN)."""

    fetch_type = "interface_status"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        lines = ["Interface,Status,Speed,Duplex"]
        port_count = 20
        for i in range(1, port_count + 1):
            h = _ip_hash(ctx.switch_ip, f"if-{i}")
            status = "DOWN" if h % 25 == 0 else "UP"
            speed = "10G" if i <= 4 else "1000M"
            duplex = "full"
            lines.append(f"GE1/0/{i},{status},{speed},{duplex}")
        return FetchResult(raw_output="\n".join(lines))


class MockAclFetcher(BaseFetcher):
    """Mock: ACL per interface (CSV format, ~70% have ACL 3001)."""

    fetch_type = "acl"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        lines = ["Interface,ACL"]
        port_count = 20
        for i in range(1, port_count + 1):
            h = _ip_hash(ctx.switch_ip, f"acl-{i}")
            acl = "3001" if h % 10 < 7 else ""
            lines.append(f"GE1/0/{i},{acl}")
        return FetchResult(raw_output="\n".join(lines))


class MockPingManyFetcher(BaseFetcher):
    """Mock: Bulk ping results (CSV format, ~7% unreachable)."""

    fetch_type = "ping_many"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        lines = ["IP,Reachable"]
        base_parts = ctx.switch_ip.rsplit(".", 1)
        base_prefix = base_parts[0] if len(base_parts) == 2 else "10.0.0"
        for i in range(1, 13):
            h = _ip_hash(ctx.switch_ip, f"cping-{i}")
            ip = f"{base_prefix}.{100 + i}"
            reachable = "false" if h % 15 == 0 else "true"
            lines.append(f"{ip},{reachable}")
        return FetchResult(raw_output="\n".join(lines))


# ══════════════════════════════════════════════════════════════════
# Registration
# ══════════════════════════════════════════════════════════════════

_ALL_MOCK_FETCHERS: list[type[BaseFetcher]] = [
    # Indicator (8)
    MockTransceiverFetcher,
    MockVersionFetcher,
    MockUplinkFetcher,
    MockFanFetcher,
    MockPowerFetcher,
    MockErrorCountFetcher,
    MockPortChannelFetcher,
    MockPingFetcher,
    # Client (5)
    MockMacTableFetcher,
    MockArpTableFetcher,
    MockInterfaceStatusFetcher,
    MockAclFetcher,
    MockPingManyFetcher,
]


def register_mock_fetchers() -> None:
    """註冊所有 mock fetcher 到全域 registry。"""
    for cls in _ALL_MOCK_FETCHERS:
        fetcher_registry.register(cls())
