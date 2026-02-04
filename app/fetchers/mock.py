"""
Mock Fetcher 實作。

提供 12 個 Mock Fetcher 用於開發與測試，與 Real Fetcher 對應。

歲修模擬邏輯（時間收斂 + 新舊設備差異）：
    - 舊設備 (OLD): 成功率隨時間下降，從 ~100% → ~0%（模擬設備逐漸離線）
    - 新設備 (NEW): 成功率隨時間上升，從 ~0% → ~100%（模擬設備逐漸上線）
    - 收斂時間點 T = converge_time / 2

API 來源分類（與 Real Fetcher 對應）：
    FNA (4): transceiver, port_channel, arp_table, acl
    DNA (7): version, uplink, fan, power, error_count, mac_table, interface_status
    GNMSPing (1): ping

USE_MOCK_API=true 時由 setup_fetchers() 自動註冊。
"""
from __future__ import annotations

import math
import random

from app.fetchers.base import BaseFetcher, FetchContext, FetchResult
from app.fetchers.convergence import MockTimeTracker
from app.fetchers.registry import fetcher_registry


# ── Utility ────────────────────────────────────────────────────────


def _is_old_device(hostname: str) -> bool:
    """
    判斷是否為舊設備。

    支援的命名模式：
    - 包含 'old'（如 SW-OLD-01, swold01）
    - 以 'old' 結尾（如 sw01old）
    - 以 '-o' 或 '_o' 結尾（如 SW-01-O, SW_01_O）
    - 以 'o' 結尾且不是以 'new' 結尾（如 SWO, sw01o）
    """
    h = hostname.lower()
    if "old" in h:
        return True
    # 檢查以 -o, _o, 或單獨 o 結尾
    if h.endswith(("-o", "_o")):
        return True
    # 以 o 結尾但不是 new 結尾（避免誤判）
    if h.endswith("o") and not h.endswith("new"):
        return True
    return False


def _is_new_device(hostname: str) -> bool:
    """
    判斷是否為新設備。

    支援的命名模式：
    - 包含 'new'（如 SW-NEW-01, swnew01）
    - 以 'new' 結尾（如 sw01new）
    - 以 '-n' 或 '_n' 結尾（如 SW-01-N, SW_01_N）
    - 以 'n' 結尾且不是以 'old' 結尾（如 SWN, sw01n）
    """
    h = hostname.lower()
    if "new" in h:
        return True
    # 檢查以 -n, _n, 或單獨 n 結尾
    if h.endswith(("-n", "_n")):
        return True
    # 以 n 結尾但不是 old 結尾（避免誤判）
    if h.endswith("n") and not h.endswith("old"):
        return True
    return False


def _get_device_success_rate(
    hostname: str,
    elapsed: float,
    converge_time: float,
    base_flaky_rate: float = 0.02,
) -> float:
    """
    計算設備的成功率（基於時間收斂 + 新舊設備差異）。

    歲修模擬邏輯：
    - 舊設備 (OLD): 成功率從 ~100% 下降到 ~0%
    - 新設備 (NEW): 成功率從 ~0% 上升到 ~100%
    - 其他設備: 維持穩定的高成功率

    Args:
        hostname: 設備名稱
        elapsed: 經過時間（秒）
        converge_time: 收斂時間（秒），完整切換在 2T 完成
        base_flaky_rate: 基礎不穩定率（即使成功也有此機率失敗）

    Returns:
        float: 成功率 (0.0 ~ 1.0)
    """
    if converge_time <= 0:
        # 立即收斂：OLD 失敗，NEW 成功
        if _is_old_device(hostname):
            return base_flaky_rate
        elif _is_new_device(hostname):
            return 1.0 - base_flaky_rate
        else:
            return 1.0 - base_flaky_rate

    # 計算收斂進度：0.0（開始）到 1.0（完成）
    # 使用 S 曲線（sigmoid）讓轉換更平滑
    # 在 T 時進度為 0.5，在 2T 時進度趨近 1.0
    t = elapsed / converge_time  # 標準化時間
    # Sigmoid: 1 / (1 + e^(-k*(t-1)))，k 控制陡峭度
    progress = 1.0 / (1.0 + math.exp(-4.0 * (t - 1.0)))

    if _is_old_device(hostname):
        # 舊設備：成功率從高到低
        success_rate = 1.0 - progress
    elif _is_new_device(hostname):
        # 新設備：成功率從低到高
        success_rate = progress
    else:
        # 其他設備：維持穩定
        success_rate = 1.0 - base_flaky_rate
        return success_rate

    # 加入隨機抖動
    if random.random() < base_flaky_rate:
        success_rate = max(0.0, success_rate - 0.1)

    return max(0.0, min(1.0, success_rate))


def _should_device_fail(
    hostname: str,
    elapsed: float,
    converge_time: float,
    base_flaky_rate: float = 0.02,
) -> bool:
    """
    判斷設備是否應該失敗（基於時間收斂 + 新舊設備差異）。

    Args:
        hostname: 設備名稱
        elapsed: 經過時間（秒）
        converge_time: 收斂時間（秒）
        base_flaky_rate: 基礎不穩定率

    Returns:
        bool: True 表示應該失敗
    """
    success_rate = _get_device_success_rate(
        hostname, elapsed, converge_time, base_flaky_rate
    )
    return random.random() > success_rate


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
# FNA Mock Fetchers (4)
#
# FNA (Factory Network Automation) 內部自動偵測廠牌，只需 switch_ip。
# ══════════════════════════════════════════════════════════════════


class MockTransceiverFetcher(BaseFetcher):
    """
    Mock: HPE Comware 'display transceiver' output.

    歲修模擬：
    - 舊設備 (OLD): 光功率隨時間偏離規格（模擬設備逐漸故障）
    - 新設備 (NEW): 光功率隨時間趨於規格（模擬設備逐漸穩定）
    """

    fetch_type = "transceiver"

    # 目標值（符合規格）
    TX_TARGET = -2.0  # dBm
    RX_TARGET = -5.0  # dBm
    TEMP_TARGET = 38.0  # °C

    # 變異數設定
    HIGH_VARIANCE = 15.0   # 高變異（不穩定）
    LOW_VARIANCE = 2.0     # 低變異（穩定）

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        hostname = ctx.switch_hostname or ""

        # 計算設備成功率來決定變異數
        success_rate = _get_device_success_rate(
            hostname=hostname,
            elapsed=tracker.elapsed_seconds,
            converge_time=settings.mock_ping_converge_time,
        )

        # 成功率高 → 低變異（穩定），成功率低 → 高變異（不穩定）
        variance = self.HIGH_VARIANCE * (1.0 - success_rate) + self.LOW_VARIANCE * success_rate

        port_count = 6
        lines: list[str] = []

        for i in range(1, port_count + 1):
            # 使用 gaussian 分佈產生數值
            tx = self.TX_TARGET + random.gauss(0, variance / 3)
            rx = self.RX_TARGET + random.gauss(0, variance / 3)
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


class MockPortChannelFetcher(BaseFetcher):
    """
    Mock: HPE Comware 'display link-aggregation summary'.

    歲修模擬：
    - 舊設備 (OLD): Port-Channel 狀態隨時間惡化（模擬設備逐漸故障）
    - 新設備 (NEW): Port-Channel 狀態隨時間改善（模擬設備逐漸穩定）
    """

    fetch_type = "port_channel"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        hostname = ctx.switch_hostname or ""

        fails = _should_device_fail(
            hostname=hostname,
            elapsed=tracker.elapsed_seconds,
            converge_time=settings.mock_ping_converge_time,
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
                has_converged = True
            else:
                switch_time = converge_time / 2
                has_converged = elapsed >= switch_time

            if is_old_device:
                device_reachable = not has_converged
            else:
                device_reachable = has_converged

            if not device_reachable:
                return FetchResult(
                    raw_output="IP,MAC",
                    error=f"Device {hostname} is not reachable",
                )

        # 設備可達，返回 ARP 資料
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
            entries = _get_mock_entries_for_switch(hostname)

            if not entries:
                return FetchResult(raw_output="IP,MAC")

            lines = ["IP,MAC"]
            for entry in entries:
                lines.append(f"{entry['ip_address']},{entry['mac_address']}")

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


# ══════════════════════════════════════════════════════════════════
# DNA Mock Fetchers (7)
#
# DNA (Device Network Automation) 需要指定 vendor_os + switch_ip。
# ══════════════════════════════════════════════════════════════════


class MockVersionFetcher(BaseFetcher):
    """
    Mock: HPE Comware 'display version' output.

    歲修模擬：
    - 舊設備 (OLD): 版本正確率隨時間下降（模擬設備逐漸離線/故障）
    - 新設備 (NEW): 版本正確率隨時間上升（模擬設備逐漸上線/穩定）
    """

    fetch_type = "version"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        hostname = ctx.switch_hostname or ""

        # 使用設備感知的失敗判斷
        fails = _should_device_fail(
            hostname=hostname,
            elapsed=tracker.elapsed_seconds,
            converge_time=settings.mock_ping_converge_time,
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
    Mock: HPE Comware 'display lldp neighbor-information'.

    歲修模擬：
    - 舊設備 (OLD): 鄰居連線隨時間減少（模擬設備逐漸離線）
    - 新設備 (NEW): 鄰居連線隨時間增加（模擬設備逐漸上線）
    """

    fetch_type = "uplink"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        hostname = ctx.switch_hostname or ""

        # 使用設備感知的失敗判斷
        fails = _should_device_fail(
            hostname=hostname,
            elapsed=tracker.elapsed_seconds,
            converge_time=settings.mock_ping_converge_time,
        )

        # 從 ctx.params 取得 uplink 期望值
        expectations = ctx.params.get("uplink_expectations", []) if ctx.params else []

        # 建立鄰居列表：(local_interface, remote_hostname, remote_interface)
        neighbors: list[tuple[str, str, str]] = []
        if expectations:
            for exp in expectations:
                neighbors.append((
                    exp["local_interface"],
                    exp["expected_neighbor"],
                    exp["expected_interface"],
                ))
        else:
            # Fallback：無期望值時使用預設拓樸
            neighbors = [
                ("GigabitEthernet1/0/49", "SW-DEFAULT-CORE-01", "HGE1/0/1"),
                ("GigabitEthernet1/0/50", "SW-DEFAULT-CORE-02", "HGE1/0/1"),
            ]

        # 失敗時只顯示部分鄰居（模擬鏈路斷線）
        if fails and len(neighbors) > 1:
            neighbors = neighbors[:len(neighbors) - 1]

        # 產生 LLDP 輸出
        lines: list[str] = []
        dev_num = int(ctx.switch_ip.split(".")[-1]) if ctx.switch_ip else 1

        for idx, (local_intf, remote_host, remote_intf) in enumerate(neighbors):
            port_num = idx + 1
            lines.append(
                f"LLDP neighbor-information of port {port_num} [{local_intf}]:"
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
    Mock: HPE Comware 'display fan' output.

    歲修模擬：
    - 舊設備 (OLD): 風扇狀態隨時間惡化（模擬設備逐漸故障）
    - 新設備 (NEW): 風扇狀態隨時間改善（模擬設備逐漸穩定）
    """

    fetch_type = "fan"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        hostname = ctx.switch_hostname or ""

        fails = _should_device_fail(
            hostname=hostname,
            elapsed=tracker.elapsed_seconds,
            converge_time=settings.mock_ping_converge_time,
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
    Mock: HPE Comware 'display power' output.

    歲修模擬：
    - 舊設備 (OLD): 電源狀態隨時間惡化（模擬設備逐漸故障）
    - 新設備 (NEW): 電源狀態隨時間改善（模擬設備逐漸穩定）
    """

    fetch_type = "power"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        hostname = ctx.switch_hostname or ""

        fails = _should_device_fail(
            hostname=hostname,
            elapsed=tracker.elapsed_seconds,
            converge_time=settings.mock_ping_converge_time,
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
    Mock: HPE Comware 'display counters error'.

    歲修模擬：
    - 舊設備 (OLD): 錯誤計數隨時間增加（模擬設備逐漸故障）
    - 新設備 (NEW): 錯誤計數隨時間減少（模擬設備逐漸穩定）
    """

    fetch_type = "error_count"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        hostname = ctx.switch_hostname or ""

        lines = [
            "Interface            Input(errs)       Output(errs)"
        ]
        for i in range(1, 21):
            # 每個介面獨立判斷
            has_error = _should_device_fail(
                hostname=hostname,
                elapsed=tracker.elapsed_seconds,
                converge_time=settings.mock_ping_converge_time,
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


class MockInterfaceStatusFetcher(BaseFetcher):
    """
    Mock: Interface status (CSV format) with time-converging UP rate.

    歲修模擬：
    - 舊設備 (OLD): 介面狀態隨時間惡化（模擬設備逐漸故障）
    - 新設備 (NEW): 介面狀態隨時間改善（模擬設備逐漸穩定）
    """

    fetch_type = "interface_status"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        hostname = ctx.switch_hostname or ""

        lines = ["Interface,Status,Speed,Duplex"]
        port_count = 20
        for i in range(1, port_count + 1):
            # 每個介面獨立判斷
            is_down = _should_device_fail(
                hostname=hostname,
                elapsed=tracker.elapsed_seconds,
                converge_time=settings.mock_ping_converge_time,
            )
            status = "DOWN" if is_down else "UP"
            speed = "10G" if i <= 4 else "1000M"
            duplex = "full"
            lines.append(f"GE1/0/{i},{status},{speed},{duplex}")
        return FetchResult(raw_output="\n".join(lines))


# ══════════════════════════════════════════════════════════════════
# GNMSPing Mock Fetcher (1)
#
# GNMS Ping API - 批量 Ping 多個 IP，不需 vendor_os。
# ══════════════════════════════════════════════════════════════════


class MockPingFetcher(BaseFetcher):
    """
    Mock: 批量 Ping Fetcher（GNMSPing）。

    ctx.params 可用參數:
        target_ips: list[str] — 要 ping 的目標 IP 清單

    若未指定 target_ips，預設 ping switch 本身（ctx.switch_ip）。

    回傳格式: "IP,Reachable\\n192.168.1.1,true\\n..."

    歲修模擬：
    - 舊設備 (OLD): 可達率隨時間下降（模擬設備逐漸離線）
    - 新設備 (NEW): 可達率隨時間上升（模擬設備逐漸上線）
    - 設置 MOCK_PING_CONVERGE_TIME=0 可讓所有設備立即可達
    """

    fetch_type = "ping"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        hostname = ctx.switch_hostname or ""

        # 從 params 取得要 ping 的 IP 清單
        target_ips: list[str] = []
        if ctx.params and "target_ips" in ctx.params:
            target_ips = ctx.params["target_ips"]

        # 若未指定 target_ips，預設 ping switch 本身
        if not target_ips:
            target_ips = [ctx.switch_ip]

        lines = ["IP,Reachable"]
        for ip in target_ips:
            # 使用設備感知的失敗判斷
            is_unreachable = _should_device_fail(
                hostname=hostname,
                elapsed=tracker.elapsed_seconds,
                converge_time=settings.mock_ping_converge_time,
            )
            reachable = "false" if is_unreachable else "true"
            lines.append(f"{ip},{reachable}")

        return FetchResult(raw_output="\n".join(lines))


# ══════════════════════════════════════════════════════════════════
# Registration
# ══════════════════════════════════════════════════════════════════

_ALL_MOCK_FETCHERS: list[type[BaseFetcher]] = [
    # FNA (4)
    MockTransceiverFetcher,
    MockPortChannelFetcher,
    MockArpTableFetcher,
    MockAclFetcher,
    # DNA (7)
    MockVersionFetcher,
    MockUplinkFetcher,
    MockFanFetcher,
    MockPowerFetcher,
    MockErrorCountFetcher,
    MockMacTableFetcher,
    MockInterfaceStatusFetcher,
    # GNMSPing (1)
    MockPingFetcher,
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
