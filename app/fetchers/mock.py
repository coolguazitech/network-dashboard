"""
Mock Fetcher 實作。

提供 13 個 Mock Fetcher 用於開發與測試。
每個 Mock Fetcher 根據時間產生「收斂」的模擬資料：
- 初始階段：較高的失敗率，模擬系統剛啟動的不穩定狀態
- 收斂階段：失敗率逐漸下降，模擬系統趨於穩定
- 穩定階段：維持低失敗率（~2-5%）

USE_MOCK_API=true 時由 setup_fetchers() 自動註冊。

收斂時間（預設）:
    - Hardware (fan/power): 60 秒
    - Topology (uplink/port_channel): 120 秒
    - Transceiver: 300 秒
    - Ping: 300 秒
    - Error count: 600 秒
"""
from __future__ import annotations

import hashlib
import math
import random

from app.fetchers.base import BaseFetcher, FetchContext, FetchResult
from app.fetchers.convergence import (
    MockTimeTracker,
    get_converging_variance,
    should_fail,
)
from app.fetchers.registry import fetcher_registry


# ── Utility ────────────────────────────────────────────────────────


def _ip_hash(switch_ip: str, salt: str = "") -> int:
    """Deterministic hash from IP + salt for reproducible topology data."""
    digest = hashlib.md5(
        f"{switch_ip}:{salt}".encode(),
    ).hexdigest()
    return int(digest, 16)


# ══════════════════════════════════════════════════════════════════
# Indicator Fetchers (8)
# ══════════════════════════════════════════════════════════════════


class MockTransceiverFetcher(BaseFetcher):
    """
    Mock: HPE Comware 'display transceiver' output with time-converging values.

    初始階段光功率變異大，逐漸收斂到規格範圍內。
    """

    fetch_type = "transceiver"

    # 目標值（符合規格）
    TX_TARGET = -2.0  # dBm
    RX_TARGET = -5.0  # dBm
    TEMP_TARGET = 38.0  # °C

    # 變異數設定
    INITIAL_TX_VARIANCE = 15.0  # 初始可能從 -17 到 +13 dBm
    TARGET_TX_VARIANCE = 2.0    # 收斂後 -4 到 0 dBm
    INITIAL_RX_VARIANCE = 18.0  # 初始可能從 -23 到 +13 dBm
    TARGET_RX_VARIANCE = 3.0    # 收斂後 -8 到 -2 dBm

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        tracker = MockTimeTracker()
        elapsed = tracker.elapsed_seconds
        converge_time = tracker.config.transceiver_converge_time

        # 計算當前變異數
        tx_variance = get_converging_variance(
            elapsed, converge_time,
            self.INITIAL_TX_VARIANCE, self.TARGET_TX_VARIANCE,
        )
        rx_variance = get_converging_variance(
            elapsed, converge_time,
            self.INITIAL_RX_VARIANCE, self.TARGET_RX_VARIANCE,
        )

        port_count = 6
        lines: list[str] = []

        for i in range(1, port_count + 1):
            # 使用 gaussian 分佈產生收斂中的數值
            tx = self.TX_TARGET + random.gauss(0, tx_variance / 3)
            rx = self.RX_TARGET + random.gauss(0, rx_variance / 3)
            temp = self.TEMP_TARGET + random.gauss(0, 5.0)

            # 限制在合理範圍內
            tx = max(-20.0, min(5.0, tx))
            rx = max(-25.0, min(5.0, rx))
            temp = max(20.0, min(70.0, temp))

            lines.append(f"GigabitEthernet1/0/{i}")
            lines.append(f"  TX Power : {tx:.1f} dBm")
            lines.append(f"  RX Power : {rx:.1f} dBm")
            lines.append(f"  Temperature : {temp:.1f} C")
            lines.append("")

        return FetchResult(raw_output="\n".join(lines))


class MockVersionFetcher(BaseFetcher):
    """
    Mock: HPE Comware 'display version' output with time-converging correctness.

    初始可能有錯誤版本，逐漸收斂到正確版本。
    """

    fetch_type = "version"

    INITIAL_FAILURE_RATE = 0.05  # 初始 5% 錯誤版本
    TARGET_FAILURE_RATE = 0.01   # 目標 1% 錯誤版本

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        tracker = MockTimeTracker()
        fails = should_fail(
            elapsed=tracker.elapsed_seconds,
            converge_time=tracker.config.version_stabilize_time,
            initial_failure_rate=self.INITIAL_FAILURE_RATE,
            target_failure_rate=self.TARGET_FAILURE_RATE,
        )

        release = "6635P05" if fails else "6635P07"

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
    """
    Mock: HPE Comware 'display lldp neighbor-information' with time-converging topology.

    初始可能缺少鄰居，逐漸收斂到完整拓樸。
    """

    fetch_type = "uplink"

    INITIAL_FAILURE_RATE = 0.15  # 初始 15% 缺少鄰居
    TARGET_FAILURE_RATE = 0.02   # 目標 2% 缺少鄰居

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        tracker = MockTimeTracker()
        fails = should_fail(
            elapsed=tracker.elapsed_seconds,
            converge_time=tracker.config.topology_stabilize_time,
            initial_failure_rate=self.INITIAL_FAILURE_RATE,
            target_failure_rate=self.TARGET_FAILURE_RATE,
        )

        # 解析 IP 以產生確定性的拓樸結構
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

        # 失敗時只顯示部分鄰居
        if fails:
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
    """
    Mock: HPE Comware 'display fan' output with time-converging status.

    初始可能有故障風扇，逐漸收斂到全部正常。
    """

    fetch_type = "fan"

    INITIAL_FAILURE_RATE = 0.10  # 初始 10% 故障
    TARGET_FAILURE_RATE = 0.01   # 目標 1% 故障

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        tracker = MockTimeTracker()
        fails = should_fail(
            elapsed=tracker.elapsed_seconds,
            converge_time=tracker.config.hardware_stabilize_time,
            initial_failure_rate=self.INITIAL_FAILURE_RATE,
            target_failure_rate=self.TARGET_FAILURE_RATE,
        )

        fan3_status = "Absent" if fails else "Normal"

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
    """
    Mock: HPE Comware 'display power' output with time-converging status.

    初始可能有故障 PSU，逐漸收斂到全部正常。
    """

    fetch_type = "power"

    INITIAL_FAILURE_RATE = 0.10  # 初始 10% 故障
    TARGET_FAILURE_RATE = 0.01   # 目標 1% 故障

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        tracker = MockTimeTracker()
        fails = should_fail(
            elapsed=tracker.elapsed_seconds,
            converge_time=tracker.config.hardware_stabilize_time,
            initial_failure_rate=self.INITIAL_FAILURE_RATE,
            target_failure_rate=self.TARGET_FAILURE_RATE,
        )

        ps2_status = "Absent" if fails else "Normal"

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
    """
    Mock: HPE Comware 'display counters error' with time-converging error counts.

    初始有較多錯誤，逐漸收斂到零錯誤。
    """

    fetch_type = "error_count"

    INITIAL_FAILURE_RATE = 0.20  # 初始 20% 介面有錯誤
    TARGET_FAILURE_RATE = 0.02   # 目標 2% 介面有錯誤

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        tracker = MockTimeTracker()
        elapsed = tracker.elapsed_seconds
        converge_time = tracker.config.error_converge_time

        lines = [
            "Interface            Input(errs)       Output(errs)"
        ]
        for i in range(1, 21):
            # 每個介面獨立判斷是否有錯誤
            has_error = should_fail(
                elapsed=elapsed,
                converge_time=converge_time,
                initial_failure_rate=self.INITIAL_FAILURE_RATE,
                target_failure_rate=self.TARGET_FAILURE_RATE,
            )

            if has_error:
                in_err = random.randint(1, 15)
                out_err = random.randint(0, 5)
            else:
                in_err = 0
                out_err = 0

            lines.append(
                f"GE1/0/{i}                        "
                f"{in_err}                  {out_err}"
            )
        return FetchResult(raw_output="\n".join(lines))


class MockPortChannelFetcher(BaseFetcher):
    """
    Mock: HPE Comware 'display link-aggregation summary' with time-converging status.

    初始可能有成員 down，逐漸收斂到全部 UP。
    """

    fetch_type = "port_channel"

    INITIAL_FAILURE_RATE = 0.15  # 初始 15% 成員異常
    TARGET_FAILURE_RATE = 0.02   # 目標 2% 成員異常

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        tracker = MockTimeTracker()
        fails = should_fail(
            elapsed=tracker.elapsed_seconds,
            converge_time=tracker.config.topology_stabilize_time,
            initial_failure_rate=self.INITIAL_FAILURE_RATE,
            target_failure_rate=self.TARGET_FAILURE_RATE,
        )

        # U = Up (異常 - 應該是 S=Selected)
        # S = Selected (正常)
        m1_status = "U" if fails else "S"

        # 使用 hash 產生確定性的介面名稱
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
    """
    Mock: Standard ping output with time-converging success rate.

    初始成功率較低，逐漸收斂到高成功率。
    """

    fetch_type = "ping"

    INITIAL_FAILURE_RATE = 0.40  # 初始 40% 失敗
    TARGET_FAILURE_RATE = 0.05   # 目標 5% 失敗

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        tracker = MockTimeTracker()
        fails = should_fail(
            elapsed=tracker.elapsed_seconds,
            converge_time=tracker.config.ping_converge_time,
            initial_failure_rate=self.INITIAL_FAILURE_RATE,
            target_failure_rate=self.TARGET_FAILURE_RATE,
        )

        ip = ctx.switch_ip

        if fails:
            # 隨機選擇失敗模式
            loss = random.choice([100, 60, 40])
            received = 5 - (loss * 5 // 100)
        else:
            loss, received = 0, 5

        # 產生 ping 回應
        ping_lines = []
        for seq in range(received):
            rtt = 1.0 + random.random() * 0.5
            ping_lines.append(
                f"64 bytes from {ip}: icmp_seq={seq} ttl=64 time={rtt:.1f} ms"
            )

        output = (
            f"PING {ip} ({ip}): 56 data bytes\n"
            + "\n".join(ping_lines)
            + "\n\n"
            f"--- {ip} ping statistics ---\n"
            f"5 packets transmitted, {received} packets received, "
            f"{loss}% packet loss\n"
            "round-trip min/avg/max = 1.0/1.2/1.5 ms\n"
        )
        return FetchResult(raw_output=output)


# ══════════════════════════════════════════════════════════════════
# Client Fetchers (5)
# ══════════════════════════════════════════════════════════════════


class MockMacTableFetcher(BaseFetcher):
    """
    Mock: MAC table (CSV format) with deterministic addresses.

    MAC 格式與 seed_client_data.py 一致:
      EQP:    00:11:22:E0:XX:XX
      AMHS:   00:11:22:A0:XX:XX
      SNR:    00:11:22:B0:XX:XX
      OTHERS: 00:11:22:C0:XX:XX

    依 switch hostname 的類別 (EQP/AMHS/SNR/OTHERS) 分配對應的 MAC。
    """

    fetch_type = "mac_table"

    # 類別配置 (與 seed_client_data.py 一致)
    # CORE/AGG 沒有客戶端 MAC，count=0
    CATEGORY_CONFIG = {
        "CORE": {"prefix": "", "count": 0, "vlan": 0},
        "AGG": {"prefix": "", "count": 0, "vlan": 0},
        "EQP": {"prefix": "E0", "count": 50, "vlan": 10},
        "AMHS": {"prefix": "A0", "count": 25, "vlan": 20},
        "SNR": {"prefix": "B0", "count": 15, "vlan": 30},
        "OTHERS": {"prefix": "C0", "count": 10, "vlan": 40},
    }

    # 各類別有多少台 switch (從 factory_device_config.py)
    SWITCHES_PER_CATEGORY = {
        "CORE": 2,
        "AGG": 8,
        "EQP": 10,
        "AMHS": 4,
        "SNR": 5,
        "OTHERS": 5,
    }

    def _get_category(self, hostname: str) -> str:
        """從 hostname 提取類別 (最後一段)。"""
        parts = hostname.split("-")
        if parts:
            cat = parts[-1].upper()
            if cat in self.CATEGORY_CONFIG:
                return cat
        return ""  # 未知類別不產生 MAC

    def _get_switch_index(self, hostname: str) -> int:
        """從 hostname 提取設備編號，轉成 0-based index。"""
        parts = hostname.split("-")
        if len(parts) >= 2:
            try:
                # SW-NEW-013-EQP → 13 → index 2 (EQP 從 11 開始)
                num = int(parts[2])
                return num % 100  # 取最後兩位作為相對位置
            except (ValueError, IndexError):
                pass
        return 0

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        hostname = ctx.switch_hostname or ""
        category = self._get_category(hostname)

        # 未知類別或 CORE/AGG 不產生 MAC
        if not category or category not in self.CATEGORY_CONFIG:
            return FetchResult(raw_output="MAC,Interface,VLAN")

        config = self.CATEGORY_CONFIG[category]
        if config["count"] == 0:
            return FetchResult(raw_output="MAC,Interface,VLAN")

        switches_count = self.SWITCHES_PER_CATEGORY.get(category, 1)

        # 計算此 switch 在該類別中的相對位置
        sw_index = self._get_switch_index(hostname) % switches_count

        # 計算此 switch 應有的 MAC 範圍
        total_macs = config["count"]
        macs_per_switch = (total_macs + switches_count - 1) // switches_count

        start_mac_idx = sw_index * macs_per_switch
        end_mac_idx = min(start_mac_idx + macs_per_switch, total_macs)

        lines = ["MAC,Interface,VLAN"]
        prefix = config["prefix"]
        vlan = config["vlan"]

        for port, mac_idx in enumerate(
            range(start_mac_idx, end_mac_idx), start=1,
        ):
            idx = mac_idx + 1  # MAC 編號從 1 開始
            mac = f"00:11:22:{prefix}:{idx:02X}:{idx:02X}"
            lines.append(f"{mac},GE1/0/{port},{vlan}")

        return FetchResult(raw_output="\n".join(lines))


class MockArpTableFetcher(BaseFetcher):
    """
    Mock: ARP table (CSV format) with deterministic mappings.

    MAC 格式與 MockMacTableFetcher 一致，確保 MAC → IP 對應正確:
      EQP:    00:11:22:E0:XX:XX → 10.0.10.XX
      AMHS:   00:11:22:A0:XX:XX → 10.0.20.XX
      SNR:    00:11:22:B0:XX:XX → 10.0.30.XX
      OTHERS: 00:11:22:C0:XX:XX → 10.0.40.XX
    """

    fetch_type = "arp_table"

    # 與 MockMacTableFetcher 保持一致
    # CORE/AGG 沒有客戶端，count=0
    CATEGORY_CONFIG = {
        "CORE": {"prefix": "", "count": 0, "ip_base": ""},
        "AGG": {"prefix": "", "count": 0, "ip_base": ""},
        "EQP": {"prefix": "E0", "count": 50, "ip_base": "10.0.10"},
        "AMHS": {"prefix": "A0", "count": 25, "ip_base": "10.0.20"},
        "SNR": {"prefix": "B0", "count": 15, "ip_base": "10.0.30"},
        "OTHERS": {"prefix": "C0", "count": 10, "ip_base": "10.0.40"},
    }

    SWITCHES_PER_CATEGORY = {
        "CORE": 2,
        "AGG": 8,
        "EQP": 10,
        "AMHS": 4,
        "SNR": 5,
        "OTHERS": 5,
    }

    def _get_category(self, hostname: str) -> str:
        """從 hostname 提取類別 (最後一段)。"""
        parts = hostname.split("-")
        if parts:
            cat = parts[-1].upper()
            if cat in self.CATEGORY_CONFIG:
                return cat
        return ""  # 未知類別不產生 ARP

    def _get_switch_index(self, hostname: str) -> int:
        """從 hostname 提取設備編號，轉成 0-based index。"""
        parts = hostname.split("-")
        if len(parts) >= 2:
            try:
                num = int(parts[2])
                return num % 100
            except (ValueError, IndexError):
                pass
        return 0

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        hostname = ctx.switch_hostname or ""
        category = self._get_category(hostname)

        # 未知類別或 CORE/AGG 不產生 ARP
        if not category or category not in self.CATEGORY_CONFIG:
            return FetchResult(raw_output="IP,MAC")

        config = self.CATEGORY_CONFIG[category]
        if config["count"] == 0:
            return FetchResult(raw_output="IP,MAC")

        switches_count = self.SWITCHES_PER_CATEGORY.get(category, 1)

        sw_index = self._get_switch_index(hostname) % switches_count

        total_macs = config["count"]
        macs_per_switch = (total_macs + switches_count - 1) // switches_count

        start_mac_idx = sw_index * macs_per_switch
        end_mac_idx = min(start_mac_idx + macs_per_switch, total_macs)

        lines = ["IP,MAC"]
        prefix = config["prefix"]
        ip_base = config["ip_base"]

        for mac_idx in range(start_mac_idx, end_mac_idx):
            idx = mac_idx + 1  # MAC 編號從 1 開始
            mac = f"00:11:22:{prefix}:{idx:02X}:{idx:02X}"
            ip = f"{ip_base}.{idx}"
            lines.append(f"{ip},{mac}")

        return FetchResult(raw_output="\n".join(lines))


class MockInterfaceStatusFetcher(BaseFetcher):
    """
    Mock: Interface status (CSV format) with time-converging UP rate.

    初始有較多 DOWN，逐漸收斂到大部分 UP。
    """

    fetch_type = "interface_status"

    INITIAL_FAILURE_RATE = 0.15  # 初始 15% DOWN
    TARGET_FAILURE_RATE = 0.02   # 目標 2% DOWN

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        tracker = MockTimeTracker()
        elapsed = tracker.elapsed_seconds
        converge_time = tracker.config.topology_stabilize_time

        lines = ["Interface,Status,Speed,Duplex"]
        port_count = 20
        for i in range(1, port_count + 1):
            is_down = should_fail(
                elapsed=elapsed,
                converge_time=converge_time,
                initial_failure_rate=self.INITIAL_FAILURE_RATE,
                target_failure_rate=self.TARGET_FAILURE_RATE,
            )
            status = "DOWN" if is_down else "UP"
            speed = "10G" if i <= 4 else "1000M"
            duplex = "full"
            lines.append(f"GE1/0/{i},{status},{speed},{duplex}")
        return FetchResult(raw_output="\n".join(lines))


class MockAclFetcher(BaseFetcher):
    """
    Mock: ACL per interface (CSV format) with time-converging compliance.

    初始可能缺少 ACL，逐漸收斂到大部分有 ACL。
    """

    fetch_type = "acl"

    INITIAL_COMPLIANCE_RATE = 0.60  # 初始 60% 有 ACL
    TARGET_COMPLIANCE_RATE = 0.95   # 目標 95% 有 ACL

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        tracker = MockTimeTracker()
        elapsed = tracker.elapsed_seconds
        converge_time = tracker.config.topology_stabilize_time

        # 計算當前合規率
        decay = math.exp(-3.0 * elapsed / converge_time) if converge_time > 0 else 0
        compliance_rate = (
            self.TARGET_COMPLIANCE_RATE
            + (self.INITIAL_COMPLIANCE_RATE - self.TARGET_COMPLIANCE_RATE) * decay
        )

        lines = ["Interface,ACL"]
        port_count = 20
        for i in range(1, port_count + 1):
            has_acl = random.random() < compliance_rate
            acl = "3001" if has_acl else ""
            lines.append(f"GE1/0/{i},{acl}")
        return FetchResult(raw_output="\n".join(lines))


class MockPingManyFetcher(BaseFetcher):
    """
    Mock: Bulk ping results (CSV format) with time-converging reachability.

    從 ctx.params["target_ips"] 取得要 ping 的 IP 清單。
    初始可達率較低，逐漸收斂到高可達率。
    """

    fetch_type = "ping_many"

    INITIAL_FAILURE_RATE = 0.20  # 初始 20% 不可達
    TARGET_FAILURE_RATE = 0.03   # 目標 3% 不可達

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        tracker = MockTimeTracker()
        elapsed = tracker.elapsed_seconds
        converge_time = tracker.config.ping_converge_time

        # 從 params 取得要 ping 的 IP 清單
        target_ips: list[str] = []
        if ctx.params and "target_ips" in ctx.params:
            target_ips = ctx.params["target_ips"]

        lines = ["IP,Reachable"]
        for ip in target_ips:
            unreachable = should_fail(
                elapsed=elapsed,
                converge_time=converge_time,
                initial_failure_rate=self.INITIAL_FAILURE_RATE,
                target_failure_rate=self.TARGET_FAILURE_RATE,
            )
            reachable = "false" if unreachable else "true"
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
