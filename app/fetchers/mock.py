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

    嚴格的命名模式（避免誤判）：
    - 包含 '-OLD-' 或 '_OLD_'（如 SW-OLD-01）
    - 以 '-OLD' 或 '_OLD' 結尾（如 SW01-OLD）
    - 以 '-O' 或 '_O' 結尾（如 SW-01-O, SW_01_O）

    不匹配的例子：
    - 'OHIO'（雖然以 O 結尾，但沒有分隔符）
    - 'PRODUCTION-GOLDEN'（包含 OLD 但不是獨立詞）
    """
    h = hostname.upper()
    # 檢查 OLD 作為獨立詞（前後有分隔符或邊界）
    if "-OLD-" in h or "_OLD_" in h:
        return True
    if h.endswith("-OLD") or h.endswith("_OLD"):
        return True
    if h.startswith("OLD-") or h.startswith("OLD_"):
        return True
    # 檢查以 -O 或 _O 結尾（單字母縮寫）
    if h.endswith("-O") or h.endswith("_O"):
        return True
    return False


def _is_new_device(hostname: str) -> bool:
    """
    判斷是否為新設備。

    嚴格的命名模式（避免誤判）：
    - 包含 '-NEW-' 或 '_NEW_'（如 SW-NEW-01）
    - 以 '-NEW' 或 '_NEW' 結尾（如 SW01-NEW）
    - 以 '-N' 或 '_N' 結尾（如 SW-01-N, SW_01_N）

    不匹配的例子：
    - 'PRODUCTION'（雖然以 N 結尾，但沒有分隔符）
    - 'RENEW-SERVER'（包含 NEW 但不是獨立詞）
    """
    h = hostname.upper()
    # 檢查 NEW 作為獨立詞（前後有分隔符或邊界）
    if "-NEW-" in h or "_NEW_" in h:
        return True
    if h.endswith("-NEW") or h.endswith("_NEW"):
        return True
    if h.startswith("NEW-") or h.startswith("NEW_"):
        return True
    # 檢查以 -N 或 _N 結尾（單字母縮寫）
    if h.endswith("-N") or h.endswith("_N"):
        return True
    return False


def _get_device_success_rate(
    hostname: str,
    elapsed: float,
    converge_time: float,
) -> float:
    """
    計算設備的成功率（基於時間收斂 + 新舊設備差異）。

    歲修模擬邏輯（確定性，無隨機）：
    - 舊設備 (OLD): 成功率從 100% 下降到 0%
    - 新設備 (NEW): 成功率從 0% 上升到 100%
    - 其他設備: 維持 100% 成功率

    Args:
        hostname: 設備名稱
        elapsed: 經過時間（秒）
        converge_time: 收斂時間（秒），完整切換在 2T 完成

    Returns:
        float: 成功率 (0.0 ~ 1.0)
    """
    if converge_time <= 0:
        # 立即收斂：OLD 失敗，NEW 成功
        if _is_old_device(hostname):
            return 0.0
        elif _is_new_device(hostname):
            return 1.0
        else:
            return 1.0

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
        # 其他設備：維持穩定 100%
        return 1.0

    return max(0.0, min(1.0, success_rate))


def _should_device_fail(
    hostname: str,
    elapsed: float,
    converge_time: float,
) -> bool:
    """
    判斷設備是否應該失敗（基於時間收斂 + 新舊設備差異）。

    收斂邏輯（與 MockArpTableFetcher 一致）：
    - 收斂切換點 = converge_time / 2
    - 舊設備 (OLD): 切換點前可達，之後不可達
    - 新設備 (NEW): 切換點前不可達，之後可達
    - 其他設備: 始終可達

    Args:
        hostname: 設備名稱
        elapsed: 經過時間（秒）
        converge_time: 收斂時間（秒）

    Returns:
        bool: True 表示應該失敗
    """
    if converge_time <= 0:
        # 立即收斂：OLD 失敗，NEW 成功
        if _is_old_device(hostname):
            return True
        elif _is_new_device(hostname):
            return False
        else:
            return False

    # 計算收斂狀態（統一邏輯：收斂時間點 = converge_time / 2）
    switch_time = converge_time / 2
    has_converged = elapsed >= switch_time

    if _is_old_device(hostname):
        # 舊設備：收斂前可達，收斂後失敗
        return has_converged
    elif _is_new_device(hostname):
        # 新設備：收斂前失敗，收斂後可達
        return not has_converged
    else:
        # 其他設備：始終可達
        return False


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

    歲修模擬（與 Ping 一致的二元切換）：
    - 切換點前：OLD 設備正常，NEW 設備光功率異常（超出規格）
    - 切換點後：OLD 設備光功率異常，NEW 設備正常
    """

    fetch_type = "transceiver"

    # 正常值（符合規格）
    TX_NORMAL = -2.0   # dBm
    RX_NORMAL = -5.0   # dBm
    TEMP_NORMAL = 38.0  # °C

    # 異常值（超出規格，會導致驗收失敗）
    TX_BAD = -18.0     # dBm（過低）
    RX_BAD = -22.0     # dBm（過低）
    TEMP_BAD = 65.0    # °C（過高）

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        hostname = ctx.switch_hostname or ""

        # 使用與 Ping 相同的二元切換邏輯
        should_fail = _should_device_fail(
            hostname=hostname,
            elapsed=tracker.get_elapsed_seconds(ctx.maintenance_id),
            converge_time=settings.mock_ping_converge_time,
        )

        port_count = 6
        lines: list[str] = []

        for i in range(1, port_count + 1):
            if should_fail:
                # 設備應該失敗：產生超出規格的數值
                tx = self.TX_BAD + random.gauss(0, 1.0)
                rx = self.RX_BAD + random.gauss(0, 1.0)
                temp = self.TEMP_BAD + random.gauss(0, 2.0)
            else:
                # 設備正常：產生符合規格的數值
                tx = self.TX_NORMAL + random.gauss(0, 1.0)
                rx = self.RX_NORMAL + random.gauss(0, 1.0)
                temp = self.TEMP_NORMAL + random.gauss(0, 3.0)

            # 限制在合理範圍內
            tx = max(-25.0, min(5.0, tx))
            rx = max(-30.0, min(5.0, rx))
            temp = max(20.0, min(80.0, temp))

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
            elapsed=tracker.get_elapsed_seconds(ctx.maintenance_id),
            converge_time=settings.mock_ping_converge_time,
        )

        # U = Up (異常 - 應該是 S=Selected)
        # S = Selected (正常)
        m1_status = "U" if fails else "S"

        # 使用 hash 產生確定性的介面名稱
        parts = ctx.switch_ip.split(".")
        third_octet = int(parts[2]) if len(parts) == 4 else 0

        if third_octet == 20:
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
        is_old = _is_old_device(hostname)
        is_new = _is_new_device(hostname)

        if is_old or is_new:
            # 計算收斂狀態（統一邏輯：收斂時間點 = converge_time / 2）
            tracker = MockTimeTracker()
            elapsed = tracker.get_elapsed_seconds(ctx.maintenance_id)
            converge_time = settings.mock_ping_converge_time

            if converge_time <= 0:
                has_converged = True
            else:
                switch_time = converge_time / 2
                has_converged = elapsed >= switch_time

            if is_old:
                device_reachable = not has_converged
            else:
                device_reachable = has_converged

            if not device_reachable:
                return FetchResult(
                    raw_output="IP,MAC",
                    success=False,
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
        elapsed = tracker.get_elapsed_seconds(ctx.maintenance_id)
        converge_time = tracker.converge_time

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
            elapsed=tracker.get_elapsed_seconds(ctx.maintenance_id),
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
            elapsed=tracker.get_elapsed_seconds(ctx.maintenance_id),
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
            elapsed=tracker.get_elapsed_seconds(ctx.maintenance_id),
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
            elapsed=tracker.get_elapsed_seconds(ctx.maintenance_id),
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
                elapsed=tracker.get_elapsed_seconds(ctx.maintenance_id),
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
    2. 根據設備名稱判斷是 OLD 還是 NEW 設備
    3. 根據時間收斂狀態決定是否返回 MAC table：
       - OLD 設備：收斂前返回 MAC，收斂後不返回（設備已下線）
       - NEW 設備：收斂前不返回 MAC，收斂後返回（設備已上線）

    這確保 mock 資料來自獨立的模擬網路狀態，而非用戶輸入。
    Ghost device（不在設定檔中的 MAC）自然不會出現。
    """

    fetch_type = "mac_table"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        hostname = ctx.switch_hostname or ""

        # 判斷設備類型（OLD/NEW）並根據收斂狀態決定是否返回 MAC table
        is_old = _is_old_device(hostname)
        is_new = _is_new_device(hostname)

        if is_old or is_new:
            # 計算收斂狀態（與 MockArpTableFetcher 相同邏輯）
            tracker = MockTimeTracker()
            elapsed = tracker.get_elapsed_seconds(ctx.maintenance_id)
            converge_time = settings.mock_ping_converge_time

            if converge_time <= 0:
                has_converged = True
            else:
                switch_time = converge_time / 2
                has_converged = elapsed >= switch_time

            if is_old:
                device_reachable = not has_converged
            else:
                device_reachable = has_converged

            if not device_reachable:
                return FetchResult(
                    raw_output="MAC,Interface,VLAN",
                    success=False,
                    error=f"Device {hostname} is not reachable",
                )

        # 設備可達，從 mock_network_state.csv 取得該 switch 的 MAC 清單
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

    Interface 名稱從 mock_network_state.csv 讀取，確保格式一致。
    """

    fetch_type = "interface_status"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        hostname = ctx.switch_hostname or ""

        # 從 mock_network_state.csv 取得該 switch 的所有 interface
        mock_state = _load_mock_network_state()
        switch_interfaces: set[str] = set()
        for entry in mock_state:
            if entry["switch_hostname"] == hostname:
                switch_interfaces.add(entry["interface"])

        # 如果沒有找到任何 interface，fallback 到預設的 GE1/0/x 格式
        if not switch_interfaces:
            switch_interfaces = {f"GE1/0/{i}" for i in range(1, 21)}

        lines = ["Interface,Status,Speed,Duplex"]
        for idx, interface in enumerate(sorted(switch_interfaces), start=1):
            # 每個介面獨立判斷
            is_down = _should_device_fail(
                hostname=hostname,
                elapsed=tracker.get_elapsed_seconds(ctx.maintenance_id),
                converge_time=settings.mock_ping_converge_time,
            )
            status = "DOWN" if is_down else "UP"
            speed = "10G" if idx <= 4 else "1000M"
            duplex = "full"
            lines.append(f"{interface},{status},{speed},{duplex}")
        return FetchResult(raw_output="\n".join(lines))


# ══════════════════════════════════════════════════════════════════
# GNMSPing Mock Fetcher (1)
#
# GNMS Ping API - 批量 Ping 多個 IP，不需 vendor_os。
# ══════════════════════════════════════════════════════════════════


class MockPingFetcher(BaseFetcher):
    """
    Mock: 設備 Ping Fetcher。

    對單一設備執行 ping，返回標準 ping 輸出格式（供 HpePingParser 解析）。

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
        switch_ip = ctx.switch_ip

        # 使用設備感知的失敗判斷
        is_unreachable = _should_device_fail(
            hostname=hostname,
            elapsed=tracker.get_elapsed_seconds(ctx.maintenance_id),
            converge_time=settings.mock_ping_converge_time,
        )

        # 返回標準 ping 輸出格式（供 HpePingParser 解析）
        if is_unreachable:
            # 失敗：100% packet loss
            output = (
                f"PING {switch_ip} ({switch_ip}): 56 data bytes\n"
                f"Request timeout for icmp_seq 0\n"
                f"Request timeout for icmp_seq 1\n"
                f"Request timeout for icmp_seq 2\n"
                f"\n"
                f"--- {switch_ip} ping statistics ---\n"
                f"3 packets transmitted, 0 packets received, 100.0% packet loss\n"
            )
        else:
            # 成功：0% packet loss
            output = (
                f"PING {switch_ip} ({switch_ip}): 56 data bytes\n"
                f"64 bytes from {switch_ip}: icmp_seq=0 ttl=64 time=1.2 ms\n"
                f"64 bytes from {switch_ip}: icmp_seq=1 ttl=64 time=1.1 ms\n"
                f"64 bytes from {switch_ip}: icmp_seq=2 ttl=64 time=1.3 ms\n"
                f"\n"
                f"--- {switch_ip} ping statistics ---\n"
                f"3 packets transmitted, 3 packets received, 0.0% packet loss\n"
                f"round-trip min/avg/max = 1.1/1.2/1.3 ms\n"
            )

        return FetchResult(raw_output=output)


class MockGnmsPingFetcher(BaseFetcher):
    """
    Mock: GNMS Ping Fetcher（批次 ping 多個 Client IP）。

    用於驗證 Client 設備的網路連通性。
    收斂行為基於 mock_network_state.csv 中的 switch hostname：
    - Client 在 OLD switch → 收斂前可達，收斂後不可達
    - Client 在 NEW switch → 收斂前不可達，收斂後可達
    - 未知 IP → 視為 NEW switch（收斂後可達）

    輸出格式：CSV (IP,Reachable,Latency_ms)
    """

    fetch_type = "gnms_ping"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from collections import defaultdict

        from app.core.config import settings

        tracker = MockTimeTracker()
        switch_ips = ctx.params.get("switch_ips", [])
        elapsed = tracker.get_elapsed_seconds(ctx.maintenance_id)
        converge_time = settings.mock_ping_converge_time

        # 載入 mock network state 建立 IP → (switch hostname, ping_reachable) 對應
        # 注意：每個 IP 可能同時出現在 OLD 和 NEW switch 上
        mock_state = _load_mock_network_state()
        ip_to_entries: dict[str, list[dict]] = defaultdict(list)
        for entry in mock_state:
            ip_to_entries[entry["ip_address"]].append(entry)

        # CSV header
        lines = ["IP,Reachable,Latency_ms"]

        for ip in switch_ips:
            # 根據 IP 查找對應的所有 entries
            entries = ip_to_entries.get(ip, [])

            if not entries:
                # IP 不在 mock network state 中，視為不可達
                lines.append(f"{ip},false,")
                continue

            # 只要任一 switch 可達且 ping_reachable=true，該 IP 就視為可達
            # 這處理了收斂期間 IP 同時存在於 OLD 和 NEW switch 的情況
            is_reachable = False
            for entry in entries:
                switch_hostname = entry["switch_hostname"]
                ping_reachable = entry.get("ping_reachable", True)

                # 檢查 switch 是否可達（基於收斂邏輯）
                switch_reachable = not _should_device_fail(
                    hostname=switch_hostname,
                    elapsed=elapsed,
                    converge_time=converge_time,
                )

                # 同時滿足：switch 可達 AND ping_reachable=true
                if switch_reachable and ping_reachable:
                    is_reachable = True
                    break

            if is_reachable:
                latency = round(random.uniform(1.0, 5.0), 2)
                lines.append(f"{ip},true,{latency}")
            else:
                lines.append(f"{ip},false,")

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
    # GNMSPing (2)
    MockPingFetcher,
    MockGnmsPingFetcher,
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
