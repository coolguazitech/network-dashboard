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


# ── Mock Network State ─────────────────────────────────────────────


_mock_network_state_cache: list[dict] | None = None


def _load_mock_network_state() -> list[dict]:
    """
    載入模擬網路狀態設定檔。

    從 test_data/mock_network_state.csv 讀取，定義哪些 MAC 在模擬網路中存在。
    這與用戶輸入 (MaintenanceMacList) 分開，避免循環論證。

    Returns:
        模擬網路狀態列表，每筆包含:
        - mac_address: MAC 地址
        - ip_address: IP 地址
        - switch_hostname: 所在 switch
        - interface: 介面名稱
        - vlan: VLAN ID
        - ping_reachable: 是否可 ping
    """
    global _mock_network_state_cache

    if _mock_network_state_cache is not None:
        return _mock_network_state_cache

    import csv
    import os

    # 找到 test_data 目錄
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(os.path.dirname(current_dir))
    csv_path = os.path.join(project_root, "test_data", "mock_network_state.csv")

    if not os.path.exists(csv_path):
        _mock_network_state_cache = []
        return _mock_network_state_cache

    entries = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append({
                "mac_address": row["mac_address"].strip().upper(),
                "ip_address": row["ip_address"].strip(),
                "switch_hostname": row["switch_hostname"].strip(),
                "interface": row["interface"].strip(),
                "vlan": int(row["vlan"]) if row.get("vlan") else 10,
                "ping_reachable": row.get("ping_reachable", "true").lower() == "true",
            })

    _mock_network_state_cache = entries
    return _mock_network_state_cache


def _get_mock_entries_for_switch(switch_hostname: str) -> list[dict]:
    """取得指定 switch 的模擬網路條目。"""
    all_entries = _load_mock_network_state()
    return [e for e in all_entries if e["switch_hostname"] == switch_hostname]


def _get_mock_ping_reachability() -> dict[str, bool]:
    """取得所有 IP 的 ping 可達性對應表。"""
    all_entries = _load_mock_network_state()
    return {e["ip_address"]: e["ping_reachable"] for e in all_entries}


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
    Mock: Standard ping output with time-based deterministic convergence.

    統一收斂邏輯（基於設備類型）：
    - 使用 hostname 判斷設備類型（-OLD 或 -NEW）
    - 收斂時間點 = MOCK_PING_CONVERGE_TIME / 2
    - 收斂前：OLD 設備可達，NEW 設備不可達
    - 收斂後：OLD 設備不可達，NEW 設備可達
    - 設置 MOCK_PING_CONVERGE_TIME=0 時，只有 NEW 設備可達
    """

    fetch_type = "ping"

    FLAKY_RATE = 0.02  # 修好後仍有 2% 機率暫時不可達

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        elapsed = tracker.elapsed_seconds
        ip = ctx.switch_ip
        hostname = (ctx.switch_hostname or "").upper()

        # 判斷設備類型
        is_old_device = "-OLD" in hostname
        is_new_device = "-NEW" in hostname

        # 使用可配置的收斂時間
        converge_time = settings.mock_ping_converge_time

        # 計算是否已收斂（收斂時間點 = converge_time / 2）
        if converge_time <= 0:
            has_converged = True  # 立即收斂
        else:
            switch_time = converge_time / 2
            has_converged = elapsed >= switch_time

        # 根據設備類型和收斂狀態決定可達性
        if is_old_device:
            # OLD 設備：收斂前可達，收斂後不可達
            is_reachable = not has_converged
        elif is_new_device:
            # NEW 設備：收斂前不可達，收斂後可達
            is_reachable = has_converged
        else:
            # 其他設備：始終可達
            is_reachable = True

        # 偶發網路問題（僅對可達設備）
        if is_reachable and random.random() < self.FLAKY_RATE:
            is_reachable = False

        # 設定結果
        if is_reachable:
            loss, received = 0, 5
        else:
            loss, received = 100, 0

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
    Mock: MAC table (CSV format) 基於 mock_network_state.csv 生成。

    資料流邏輯：
    1. 從 mock_network_state.csv 讀取模擬網路狀態
    2. 返回該 switch 的 MAC table（只包含設定檔中屬於該 switch 的 MAC）

    這確保 mock 資料來自獨立的模擬網路狀態，而非用戶輸入。
    Ghost device（不在設定檔中的 MAC）自然不會出現。
    """

    fetch_type = "mac_table"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        hostname = ctx.switch_hostname or ""

        # 從 mock_network_state.csv 取得該 switch 的 MAC 清單
        entries = _get_mock_entries_for_switch(hostname)

        if not entries:
            return FetchResult(raw_output="MAC,Interface,VLAN")

        # 生成 MAC table
        lines = ["MAC,Interface,VLAN"]
        for entry in entries:
            lines.append(
                f"{entry['mac_address']},{entry['interface']},{entry['vlan']}"
            )

        return FetchResult(raw_output="\n".join(lines))


class MockArpTableFetcher(BaseFetcher):
    """
    Mock: ARP table (CSV format) 基於 mock_network_state.csv 生成。

    資料流邏輯：
    1. 從 mock_network_state.csv 讀取模擬網路狀態
    2. 根據設備名稱判斷是 OLD 還是 NEW 設備
    3. 根據時間收斂狀態決定是否返回 ARP 資料：
       - OLD 設備：收斂前返回 ARP，收斂後不返回（設備已下線）
       - NEW 設備：收斂前不返回 ARP，收斂後返回（設備已上線）

    這確保 ARP 資料來自獨立的模擬網路狀態，而非用戶輸入。
    """

    fetch_type = "arp_table"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.fetchers.convergence import MockTimeTracker
        from app.core.config import settings

        hostname = ctx.switch_hostname or ""
        hostname_upper = hostname.upper()

        # 判斷設備類型（OLD/NEW）並根據收斂狀態決定是否返回 ARP
        is_old_device = "-OLD" in hostname_upper
        is_new_device = "-NEW" in hostname_upper

        if is_old_device or is_new_device:
            # 計算收斂狀態（統一邏輯：收斂時間點 = converge_time / 2）
            tracker = MockTimeTracker()
            elapsed = tracker.elapsed_seconds
            converge_time = settings.mock_ping_converge_time

            if converge_time <= 0:
                # 立即收斂：OLD 不可達，NEW 可達
                has_converged = True
            else:
                # 統一收斂時間點 = converge_time / 2
                switch_time = converge_time / 2
                has_converged = elapsed >= switch_time

            # OLD 設備：收斂前可達，收斂後不可達
            # NEW 設備：收斂前不可達，收斂後可達
            if is_old_device:
                device_reachable = not has_converged
            else:  # is_new_device
                device_reachable = has_converged

            if not device_reachable:
                # 設備不可達，返回空 ARP（模擬連線失敗）
                return FetchResult(
                    raw_output="IP,MAC",
                    error=f"Device {hostname} is not reachable",
                )

        # 設備可達，返回 ARP 資料
        # Router/Gateway 可以看到整個網路的 ARP
        is_router = "EDGE" not in hostname_upper

        if is_router:
            all_entries = _load_mock_network_state()
            if not all_entries:
                return FetchResult(raw_output="IP,MAC")

            lines = ["IP,MAC"]
            for entry in all_entries:
                lines.append(f"{entry['ip_address']},{entry['mac_address']}")

            return FetchResult(raw_output="\n".join(lines))
        else:
            # Edge Switch 只能看到自己的 ARP
            entries = _get_mock_entries_for_switch(hostname)

            if not entries:
                return FetchResult(raw_output="IP,MAC")

            lines = ["IP,MAC"]
            for entry in entries:
                lines.append(f"{entry['ip_address']},{entry['mac_address']}")

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
    Mock: Bulk ping results (CSV format) with time-based deterministic convergence.

    從 ctx.params["target_ips"] 取得要 ping 的 IP 清單。

    時間收斂邏輯（確定性，可配置）：
    - 使用 MOCK_PING_CONVERGE_TIME 環境變數配置收斂時間（預設 600 秒 = 10 分鐘）
    - 每個 IP 有一個「修好時間點」（0 到 converge_time 內，用 hash 決定）
    - 修好前：不可達
    - 修好後：可達（但有 2% 機率暫時不可達，模擬偶發網路問題）
    - 設置 MOCK_PING_CONVERGE_TIME=0 可讓所有設備立即可達
    """

    fetch_type = "ping_many"

    FLAKY_RATE = 0.02  # 修好後仍有 2% 機率暫時不可達

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        elapsed = tracker.elapsed_seconds

        # 從 params 取得要 ping 的 IP 清單
        target_ips: list[str] = []
        if ctx.params and "target_ips" in ctx.params:
            target_ips = ctx.params["target_ips"]

        # 使用可配置的收斂時間（預設 10 分鐘）
        converge_time = settings.mock_ping_converge_time

        lines = ["IP,Reachable"]
        for ip in target_ips:
            # 如果 converge_time 為 0，所有設備立即可達
            if converge_time <= 0:
                fix_time = 0
            else:
                # 用 hash 決定該 IP 的「修好時間點」（0 到 converge_time 內）
                h = _ip_hash(ip, "ping_many_fix_time")
                fix_time = h % converge_time

            # 判斷是否可達
            if elapsed < fix_time:
                # 尚未修好：不可達
                reachable = "false"
            elif random.random() < self.FLAKY_RATE:
                # 偶發網路問題
                reachable = "false"
            else:
                # 已修好：可達
                reachable = "true"

            lines.append(f"{ip},{reachable}")

        return FetchResult(raw_output="\n".join(lines))


class MockGNMSPingFetcher(BaseFetcher):
    """
    Mock: GNMS Ping API - 批次 ping clients by IP.

    從 ctx.params 取得：
    - switch_ips: list[str] - 要 ping 的 client IP 清單
    - tenant_group: TenantGroup - 租戶群組

    回傳 CSV 格式: IP,Reachable,Latency_ms

    Ping 可達性來自 mock_network_state.csv 的 ping_reachable 欄位。
    不在設定檔中的 IP（如 ghost device）會被視為不可達。
    """

    fetch_type = "gnms_ping"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        # 從 params 取得參數
        target_ips: list[str] = []
        if ctx.params:
            target_ips = ctx.params.get("switch_ips", [])

        # 取得 mock 網路狀態的 ping 可達性對應表
        ping_reachability = _get_mock_ping_reachability()

        lines = ["IP,Reachable,Latency_ms"]
        for ip in target_ips:
            # 從 mock_network_state.csv 查詢可達性
            # 不在設定檔中的 IP（如 ghost device）視為不可達
            is_reachable = ping_reachability.get(ip, False)

            if is_reachable:
                latency = round(random.uniform(1.0, 10.0), 2)
                lines.append(f"{ip},true,{latency}")
            else:
                lines.append(f"{ip},false,")

        return FetchResult(
            raw_output="\n".join(lines),
        )


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
    # Client (6)
    MockMacTableFetcher,
    MockArpTableFetcher,
    MockInterfaceStatusFetcher,
    MockAclFetcher,
    MockPingManyFetcher,
    MockGNMSPingFetcher,
]


def clear_mock_network_state_cache() -> None:
    """清除 mock network state 快取，強制重新載入 CSV。"""
    global _mock_network_state_cache
    _mock_network_state_cache = None


def register_mock_fetchers() -> None:
    """註冊所有 mock fetcher 到全域 registry。"""
    # 清除快取，確保使用最新的 mock_network_state.csv
    clear_mock_network_state_cache()
    for cls in _ALL_MOCK_FETCHERS:
        fetcher_registry.register(cls())
