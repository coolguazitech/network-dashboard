"""
Mock Fetcher 實作。

提供 12 個 Mock Fetcher 用於開發與測試，與 Real Fetcher 對應。

歲修模擬邏輯（時間收斂 + 新舊設備差異）：
    - 舊設備 (is_old_device=True): 成功率隨時間下降，模擬設備逐漸離線
    - 新設備 (is_old_device=False): 成功率隨時間上升，模擬設備逐漸上線
    - 未指定 (is_old_device=None): 無收斂行為，始終正常
    - 收斂時間點 T = converge_time / 2

API 來源分類（與 Real Fetcher 對應）：
    FNA (3): transceiver, port_channel, acl
    DNA (8): version, uplink, fan, power, error_count, mac_table, interface_status, arp_table
    GNMSPing (1): ping

USE_MOCK_API=true 時由 setup_fetchers() 自動註冊。
"""
from __future__ import annotations

import math
import random

from app.core.enums import DeviceType
from app.fetchers.base import BaseFetcher, FetchContext, FetchResult
from app.fetchers.convergence import MockTimeTracker
from app.fetchers.registry import fetcher_registry


# ── Utility ────────────────────────────────────────────────────────


def _should_device_fail(
    is_old: bool | None,
    elapsed: float,
    converge_time: float,
) -> bool:
    """
    判斷設備是否應該失敗（基於時間收斂 + 新舊設備差異）。

    收斂邏輯：
    - 收斂切換點 = converge_time / 2
    - 舊設備 (is_old=True): 切換點前可達，之後不可達
    - 新設備 (is_old=False): 切換點前不可達，之後可達
    - 未指定 (is_old=None): 始終可達（client collection 等不涉及收斂的場景）

    Args:
        is_old: 是否為舊設備（由 FetchContext.is_old_device 傳入）
        elapsed: 經過時間（秒）
        converge_time: 收斂時間（秒）

    Returns:
        bool: True 表示應該失敗
    """
    if is_old is None:
        return False

    if converge_time <= 0:
        # 立即收斂：OLD 失敗，NEW 成功
        return is_old

    switch_time = converge_time / 2
    has_converged = elapsed >= switch_time

    if is_old:
        return has_converged
    else:
        return not has_converged


# ── Mock Network State ─────────────────────────────────────────────


# ┌──────────────────────────────────────────────────────────────────┐
# │  WARNING: test_data/mock_network_state.csv 為所有 Mock Fetcher  │
# │  的基礎真值表 (ground truth)，請勿任意修改。                      │
# │  多個 Fetcher（ARP、MAC table、Ping、Interface Status 等）      │
# │  皆依賴此檔案的格式與內容。                                       │
# │  若需變更，請同步更新所有相關元件。                                │
# └──────────────────────────────────────────────────────────────────┘
_mock_network_state_cache: list[dict] | None = None


def _load_mock_network_state() -> list[dict]:
    """
    載入模擬網路狀態設定檔。

    從 test_data/mock_network_state.csv 讀取，定義哪些 MAC 在模擬網路中存在。
    這與用戶輸入 (MaintenanceMacList) 分開，避免循環論證。

    WARNING: mock_network_state.csv 是所有 Mock Fetcher 的基礎真值表，
    請勿任意修改。若需變更請同步更新所有相關元件。

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
            h = row["switch_hostname"].strip()
            hu = h.upper()
            # 從 CSV hostname 推斷 is_old（僅用於 mock 內部收斂）
            is_old: bool | None = None
            if any(p in hu for p in ("-OLD-", "_OLD_")) or hu.endswith(("-OLD", "_OLD", "-O", "_O")):
                is_old = True
            elif any(p in hu for p in ("-NEW-", "_NEW_")) or hu.endswith(("-NEW", "_NEW", "-N", "_N")):
                is_old = False
            entries.append({
                "mac_address": row["mac_address"].strip().upper(),
                "ip_address": row["ip_address"].strip(),
                "switch_hostname": h,
                "interface": row["interface"].strip(),
                "vlan": int(row["vlan"]) if row.get("vlan") else 10,
                "ping_reachable": row.get("ping_reachable", "true").lower() == "true",
                "is_old": is_old,
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
# FNA Mock Fetchers (3)
#
# FNA (FAB Network API) 內部自動偵測廠牌，只需 switch_ip。
# ══════════════════════════════════════════════════════════════════


class MockTransceiverFetcher(BaseFetcher):
    """
    Mock: 根據設備 vendor 產生對應格式的光模組診斷資料。

    - HPE Comware  → display transceiver (key-value blocks)
    - Cisco IOS    → show interfaces transceiver (table format)
    - Cisco NX-OS  → show interface transceiver (key-value blocks, different layout)

    歲修模擬（與 Ping 一致的二元切換）：
    - 切換點前：OLD 設備正常，NEW 設備光功率異常（超出規格）
    - 切換點後：OLD 設備光功率異常，NEW 設備正常
    """

    fetch_type = "transceiver"

    # 正常值（符合規格）
    TX_NORMAL = -2.0   # dBm
    RX_NORMAL = -5.0   # dBm
    TEMP_NORMAL = 38.0  # °C
    VOLT_NORMAL = 3.30  # V

    # 異常值（超出規格，會導致驗收失敗）
    TX_BAD = -18.0     # dBm（過低）
    RX_BAD = -22.0     # dBm（過低）
    TEMP_BAD = 65.0    # °C（過高）

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        should_fail = _should_device_fail(
            is_old=ctx.is_old_device if ctx.is_old_device else None,
            elapsed=tracker.get_elapsed_seconds(ctx.maintenance_id),
            converge_time=settings.mock_ping_converge_time,
        )

        if ctx.device_type == DeviceType.CISCO_NXOS:
            output = self._generate_nxos(should_fail)
        elif ctx.device_type == DeviceType.CISCO_IOS:
            output = self._generate_ios(should_fail)
        else:
            output = self._generate_hpe(should_fail)

        return FetchResult(raw_output=output)

    def _gen_values(self, should_fail: bool) -> tuple[float, float, float, float]:
        """產生一組光模組數值 (tx, rx, temp, voltage)。"""
        if should_fail:
            tx = self.TX_BAD + random.gauss(0, 1.0)
            rx = self.RX_BAD + random.gauss(0, 1.0)
            temp = self.TEMP_BAD + random.gauss(0, 2.0)
        else:
            tx = self.TX_NORMAL + random.gauss(0, 1.0)
            rx = self.RX_NORMAL + random.gauss(0, 1.0)
            temp = self.TEMP_NORMAL + random.gauss(0, 3.0)

        tx = max(-25.0, min(5.0, tx))
        rx = max(-30.0, min(5.0, rx))
        temp = max(20.0, min(80.0, temp))
        volt = self.VOLT_NORMAL + random.gauss(0, 0.05)
        volt = max(2.5, min(4.0, volt))

        return tx, rx, temp, volt

    def _generate_hpe(self, should_fail: bool) -> str:
        """HPE Comware 'display transceiver' format."""
        port_count = 6
        lines: list[str] = []
        for i in range(1, port_count + 1):
            tx, rx, temp, _volt = self._gen_values(should_fail)
            lines.append(f"GigabitEthernet1/0/{i}")
            lines.append(f"  TX Power : {tx:.1f} dBm")
            lines.append(f"  RX Power : {rx:.1f} dBm")
            lines.append(f"  Temperature : {temp:.1f} C")
            lines.append("")
        return "\n".join(lines)

    def _generate_ios(self, should_fail: bool) -> str:
        """Cisco IOS 'show interfaces transceiver' table format."""
        port_count = 6
        lines: list[str] = [
            "                                   Optical   Optical",
            "                 Temperature  Voltage  Tx Power  Rx Power",
            "Port             (Celsius)    (Volts)  (dBm)     (dBm)",
            "---------        -----------  -------  --------  --------",
        ]
        for i in range(1, port_count + 1):
            tx, rx, temp, volt = self._gen_values(should_fail)
            lines.append(
                f"Gi1/0/{i:<12}{temp:<13.1f}{volt:<9.2f}{tx:<10.1f}{rx:.1f}"
            )
        return "\n".join(lines)

    def _generate_nxos(self, should_fail: bool) -> str:
        """Cisco NX-OS 'show interface transceiver' key-value format."""
        port_count = 6
        lines: list[str] = []
        for i in range(1, port_count + 1):
            tx, rx, temp, volt = self._gen_values(should_fail)
            lines.append(f"Ethernet1/{i}")
            lines.append("    transceiver is present")
            lines.append("    type is 10Gbase-SR")
            lines.append("    name is CISCO-FINISAR")
            lines.append(f"    Temperature            {temp:.2f} C")
            lines.append(f"    Voltage                {volt:.2f} V")
            lines.append(f"    Tx Power               {tx:.2f} dBm")
            lines.append(f"    Rx Power               {rx:.2f} dBm")
            lines.append("")
        return "\n".join(lines)


class MockPortChannelFetcher(BaseFetcher):
    """
    Mock: 根據設備 vendor 產生對應格式的 Port-Channel 狀態。

    - HPE → display link-aggregation summary (AggID/Interface/Link/Attr/Mode/Members)
    - Cisco IOS → show etherchannel summary (Group/Port-channel/Protocol/Ports)
    - Cisco NXOS → show port-channel summary (Group/Po(Status)/Type/Protocol/Members)

    歲修模擬：
    - 舊設備 (OLD): Port-Channel 狀態隨時間惡化（模擬設備逐漸故障）
    - 新設備 (NEW): Port-Channel 狀態隨時間改善（模擬設備逐漸穩定）
    """

    fetch_type = "port_channel"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        fails = _should_device_fail(
            is_old=ctx.is_old_device,
            elapsed=tracker.get_elapsed_seconds(ctx.maintenance_id),
            converge_time=settings.mock_ping_converge_time,
        )

        # 使用 IP 決定介面名稱
        parts = ctx.switch_ip.split(".")
        third_octet = int(parts[2]) if len(parts) == 4 else 0

        if ctx.device_type == DeviceType.CISCO_NXOS:
            output = self._generate_nxos(fails, third_octet)
        elif ctx.device_type == DeviceType.CISCO_IOS:
            output = self._generate_ios(fails, third_octet)
        else:
            output = self._generate_hpe(fails, third_octet)

        return FetchResult(raw_output=output)

    @staticmethod
    def _generate_hpe(fails: bool, third_octet: int) -> str:
        """HPE Comware 'display link-aggregation summary' format."""
        m1_status = "U" if fails else "S"
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
        return "\n".join(lines)

    @staticmethod
    def _generate_nxos(fails: bool, third_octet: int) -> str:
        """Cisco NX-OS 'show port-channel summary' format."""
        m1_flag = "D" if fails else "P"
        if third_octet == 20:
            m1, m2 = "Eth1/25", "Eth1/26"
        else:
            m1, m2 = "Eth1/51", "Eth1/52"
        pc_status = "SD" if fails else "SU"
        lines = [
            "--------------------------------------------------------------------------------",
            "Group Port-       Type     Protocol  Member Ports",
            "      Channel",
            "--------------------------------------------------------------------------------",
            f"1     Po1({pc_status})     Eth      LACP      {m1}({m1_flag})    {m2}(P)",
        ]
        return "\n".join(lines)

    @staticmethod
    def _generate_ios(fails: bool, third_octet: int) -> str:
        """Cisco IOS 'show etherchannel summary' format."""
        m1_flag = "D" if fails else "P"
        if third_octet == 20:
            m1, m2 = "Gi1/0/25", "Gi1/0/26"
        else:
            m1, m2 = "Gi1/0/51", "Gi1/0/52"
        pc_status = "SD" if fails else "SU"
        lines = [
            "Group  Port-channel  Protocol    Ports",
            "------+-------------+-----------+-------",
            f"1      Po1({pc_status})       LACP        {m1}({m1_flag}) {m2}(P)",
        ]
        return "\n".join(lines)


class MockArpTableFetcher(BaseFetcher):
    """
    Mock: ARP table (CSV format) 基於 mock_network_state.csv 生成。

    資料流邏輯：
    1. 從 mock_network_state.csv 讀取模擬網路狀態
    2. 根據 ctx.is_old_device 判斷收斂方向
    3. 根據時間收斂狀態決定是否返回 ARP 資料：
       - OLD 設備：收斂前返回 ARP，收斂後不返回（設備已下線）
       - NEW 設備：收斂前不返回 ARP，收斂後返回（設備已上線）

    這確保 ARP 資料來自獨立的模擬網路狀態，而非用戶輸入。
    """

    fetch_type = "arp_table"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        hostname = ctx.switch_hostname or ""

        # 收斂判斷：設備不可達時返回錯誤
        if ctx.is_old_device is not None:
            tracker = MockTimeTracker()
            device_fails = _should_device_fail(
                is_old=ctx.is_old_device,
                elapsed=tracker.get_elapsed_seconds(ctx.maintenance_id),
                converge_time=settings.mock_ping_converge_time,
            )
            if device_fails:
                return FetchResult(
                    raw_output="IP,MAC",
                    success=False,
                    error=f"Device {hostname} is not reachable",
                )

        # 設備可達，返回 ARP 資料
        is_router = "EDGE" not in hostname.upper()

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
# DNA Mock Fetchers (8)
#
# DNA (Data Center Network API) 需要指定 vendor_os + switch_ip。
# ══════════════════════════════════════════════════════════════════


class MockVersionFetcher(BaseFetcher):
    """
    Mock: 根據設備 vendor 產生對應格式的版本資訊。

    - HPE → display version (HPE Comware Platform Software)
    - Cisco IOS → show version (Cisco IOS Software)
    - Cisco NXOS → show version (Cisco NX-OS Software)

    歲修模擬：
    - 舊設備 (OLD): 版本正確率隨時間下降（模擬設備逐漸離線/故障）
    - 新設備 (NEW): 版本正確率隨時間上升（模擬設備逐漸上線/穩定）
    """

    fetch_type = "version"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        fails = _should_device_fail(
            is_old=ctx.is_old_device,
            elapsed=tracker.get_elapsed_seconds(ctx.maintenance_id),
            converge_time=settings.mock_ping_converge_time,
        )

        if ctx.device_type == DeviceType.CISCO_NXOS:
            output = self._generate_nxos(fails)
        elif ctx.device_type == DeviceType.CISCO_IOS:
            output = self._generate_ios(fails)
        else:
            output = self._generate_hpe(fails)

        return FetchResult(raw_output=output)

    @staticmethod
    def _generate_hpe(fails: bool) -> str:
        """HPE Comware 'display version' format."""
        release = "6635P05" if fails else "6635P07"
        return (
            "HPE Comware Platform Software\n"
            f"Comware Software, Version 7.1.070, Release {release}\n"
            "Copyright (c) 2010-2024 Hewlett Packard Enterprise "
            "Development LP\n"
            "HPE FF 5710 48SFP+ 6QS 2SL Switch\n"
            "Uptime is 0 weeks, 1 day, 3 hours, 22 minutes\n"
        )

    @staticmethod
    def _generate_nxos(fails: bool) -> str:
        """Cisco NX-OS 'show version' format."""
        ver = "9.3.8" if fails else "10.3.3"
        return (
            "Cisco Nexus Operating System (NX-OS) Software\n"
            "TAC support: http://www.cisco.com/tac\n"
            "Copyright (c) 2002-2024, Cisco Systems, Inc.\n"
            f"NXOS: version {ver}\n"
            "Hardware\n"
            "  cisco Nexus9000 C9336C-FX2 Chassis\n"
            "Uptime is 0 weeks, 1 day, 3 hours\n"
        )

    @staticmethod
    def _generate_ios(fails: bool) -> str:
        """Cisco IOS 'show version' format."""
        ver = "16.12.4" if fails else "17.9.4"
        return (
            f"Cisco IOS Software, Version {ver}\n"
            "Copyright (c) 1986-2024 by Cisco Systems, Inc.\n"
            "Cisco Catalyst C9200L-48P-4G Switch\n"
            "Uptime is 0 weeks, 1 day, 3 hours\n"
        )


class MockUplinkFetcher(BaseFetcher):
    """
    Mock: 根據設備 vendor 產生對應格式的鄰居資料。

    - HPE/Aruba → HPE Comware LLDP 格式
    - Cisco IOS → CDP 格式
    - Cisco NXOS → NXOS LLDP 格式

    歲修模擬：
    - 舊設備 (OLD): 鄰居連線隨時間減少（模擬設備逐漸離線）
    - 新設備 (NEW): 鄰居連線隨時間增加（模擬設備逐漸上線）
    """

    fetch_type = "uplink"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        fails = _should_device_fail(
            is_old=ctx.is_old_device,
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

        # 根據 device_type 產生對應格式
        if ctx.device_type == DeviceType.CISCO_NXOS:
            raw_output = self._generate_nxos_lldp(neighbors)
        elif ctx.device_type == DeviceType.CISCO_IOS:
            raw_output = self._generate_cisco_cdp(neighbors)
        else:
            raw_output = self._generate_hpe_lldp(neighbors, ctx.switch_ip)

        return FetchResult(raw_output=raw_output)

    @staticmethod
    def _generate_hpe_lldp(
        neighbors: list[tuple[str, str, str]], switch_ip: str | None,
    ) -> str:
        """產生 HPE Comware LLDP 格式。"""
        lines: list[str] = []
        dev_num = int(switch_ip.split(".")[-1]) if switch_ip else 1

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

        return "\n".join(lines)

    @staticmethod
    def _generate_cisco_cdp(neighbors: list[tuple[str, str, str]]) -> str:
        """產生 Cisco IOS CDP 格式。"""
        lines: list[str] = []

        for local_intf, remote_host, remote_intf in neighbors:
            lines.append("-------------------------")
            lines.append(f"Device ID: {remote_host}")
            lines.append("Entry address(es):")
            lines.append("  IP address: 10.0.0.1")
            lines.append(
                "Platform: cisco WS-C3750X-48,  "
                "Capabilities: Router Switch IGMP"
            )
            lines.append(
                f"Interface: {local_intf},  "
                f"Port ID (outgoing port): {remote_intf}"
            )
            lines.append("Holdtime : 179 sec")
            lines.append("")

        if neighbors:
            lines.append("-------------------------")

        return "\n".join(lines)

    @staticmethod
    def _generate_nxos_lldp(neighbors: list[tuple[str, str, str]]) -> str:
        """產生 Cisco NX-OS LLDP 格式。"""
        lines: list[str] = []

        for local_intf, remote_host, remote_intf in neighbors:
            lines.append("Chassis id: 0012.3456.789a")
            lines.append(f"Port id: {remote_intf}")
            lines.append(f"Local Port id: {local_intf}")
            lines.append("Port Description: not advertised")
            lines.append(f"System Name: {remote_host}")
            lines.append(
                "System Description: "
                "Cisco Nexus Operating System (NX-OS) Software"
            )
            lines.append("Time remaining: 112 seconds")
            lines.append("")

        return "\n".join(lines)


class MockFanFetcher(BaseFetcher):
    """
    Mock: 依廠牌產生對應格式的 fan 狀態 output。

    - HPE Comware  → display fan
    - Cisco IOS    → show environment
    - Cisco NX-OS  → show environment fan

    歲修模擬：
    - 舊設備 (OLD): 風扇狀態隨時間惡化（模擬設備逐漸故障）
    - 新設備 (NEW): 風扇狀態隨時間改善（模擬設備逐漸穩定）
    """

    fetch_type = "fan"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        fails = _should_device_fail(
            is_old=ctx.is_old_device,
            elapsed=tracker.get_elapsed_seconds(ctx.maintenance_id),
            converge_time=settings.mock_ping_converge_time,
        )

        if ctx.device_type == DeviceType.CISCO_NXOS:
            output = self._generate_nxos(fails)
        elif ctx.device_type == DeviceType.CISCO_IOS:
            output = self._generate_ios(fails)
        else:
            output = self._generate_hpe(fails)

        return FetchResult(raw_output=output)

    @staticmethod
    def _generate_hpe(fails: bool) -> str:
        """HPE Comware 'display fan' 格式。"""
        fan3 = "Absent" if fails else "Normal"
        return (
            "Slot 1:\n"
            "FanID    Status      Direction\n"
            "1        Normal      Back-to-front\n"
            "2        Normal      Back-to-front\n"
            f"3        {fan3}      Back-to-front\n"
            "4        Normal      Back-to-front\n"
        )

    @staticmethod
    def _generate_nxos(fails: bool) -> str:
        """Cisco NX-OS 'show environment fan' 格式。"""
        fan3 = "Absent" if fails else "Ok"
        return (
            "Fan             Model                Hw     Status\n"
            "--------------------------------------------------------------\n"
            "Fan1(Sys_Fan1)  NXA-FAN-30CFM-F      --     Ok\n"
            "Fan2(Sys_Fan2)  NXA-FAN-30CFM-F      --     Ok\n"
            f"Fan3(Sys_Fan3)  NXA-FAN-30CFM-F      --     {fan3}\n"
            "Fan4(Sys_Fan4)  NXA-FAN-30CFM-F      --     Ok\n"
        )

    @staticmethod
    def _generate_ios(fails: bool) -> str:
        """Cisco IOS 'show environment' 格式。"""
        fan3 = "NOT OK" if fails else "OK"
        return (
            "FAN 1 is OK\n"
            "FAN 2 is OK\n"
            f"FAN 3 is {fan3}\n"
            "FAN 4 is OK\n"
        )


class MockPowerFetcher(BaseFetcher):
    """
    Mock: 依廠牌產生對應格式的電源供應器狀態 output。

    - HPE Comware  → display power
    - Cisco IOS    → show environment power
    - Cisco NX-OS  → show environment power
    """

    fetch_type = "power"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        fails = _should_device_fail(
            is_old=ctx.is_old_device,
            elapsed=tracker.get_elapsed_seconds(ctx.maintenance_id),
            converge_time=settings.mock_ping_converge_time,
        )

        if ctx.device_type == DeviceType.CISCO_NXOS:
            output = self._generate_nxos(fails)
        elif ctx.device_type == DeviceType.CISCO_IOS:
            output = self._generate_ios(fails)
        else:
            output = self._generate_hpe(fails)

        return FetchResult(raw_output=output)

    @staticmethod
    def _generate_hpe(fails: bool) -> str:
        ps2 = "Absent" if fails else "Normal"
        return (
            "Slot 1:\n"
            "PowerID State    Mode   Current(A)  Voltage(V)  "
            "Power(W)  FanDirection\n"
            "1       Normal   AC     --          --          "
            "--        Back-to-front\n"
            f"2       {ps2}   AC     --          --          "
            "--        Back-to-front\n"
        )

    @staticmethod
    def _generate_nxos(fails: bool) -> str:
        ps2_status = "Absent" if fails else "Ok"
        ps2_output = "0" if fails else "132"
        return (
            "Power                              Actual        Total\n"
            "Supply    Model                    Output     Capacity    Status\n"
            "-------  -------------------  -----------  -----------  ----------\n"
            f"1        NXA-PAC-1100W-PE           186       1100     Ok\n"
            f"2        NXA-PAC-1100W-PE           {ps2_output}       1100     {ps2_status}\n"
        )

    @staticmethod
    def _generate_ios(fails: bool) -> str:
        ps2 = "NOT OK" if fails else "OK"
        return (
            "PS1 is OK\n"
            f"PS2 is {ps2}\n"
        )


class MockErrorCountFetcher(BaseFetcher):
    """
    Mock: 根據設備 vendor 產生對應格式的介面錯誤計數。

    - HPE → display counters error (Interface / Input / Output)
    - Cisco IOS → show interfaces counters errors (Interface / Input / Output)
    - Cisco NXOS → show interface counters errors (6-column)

    歲修模擬：
    - 舊設備 (OLD): 錯誤計數隨時間增加（模擬設備逐漸故障）
    - 新設備 (NEW): 錯誤計數隨時間減少（模擬設備逐漸穩定）
    """

    fetch_type = "error_count"

    async def fetch(self, ctx: FetchContext) -> FetchResult:
        from app.core.config import settings

        tracker = MockTimeTracker()
        has_error = _should_device_fail(
            is_old=ctx.is_old_device,
            elapsed=tracker.get_elapsed_seconds(ctx.maintenance_id),
            converge_time=settings.mock_ping_converge_time,
        )

        if ctx.device_type == DeviceType.CISCO_NXOS:
            output = self._generate_nxos(has_error)
        elif ctx.device_type == DeviceType.CISCO_IOS:
            output = self._generate_ios(has_error)
        else:
            output = self._generate_hpe(has_error)

        return FetchResult(raw_output=output)

    @staticmethod
    def _generate_hpe(has_error: bool) -> str:
        """HPE Comware 'display counters error' format."""
        lines = ["Interface            Input(errs)       Output(errs)"]
        for i in range(1, 21):
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
        return "\n".join(lines)

    @staticmethod
    def _generate_nxos(has_error: bool) -> str:
        """Cisco NX-OS 'show interface counters errors' format."""
        lines = [
            "--------------------------------------------------------------------------------",
            "Port          Align-Err    FCS-Err   Xmit-Err    Rcv-Err  UnderSize OutDiscards",
            "--------------------------------------------------------------------------------",
        ]
        for i in range(1, 21):
            if has_error:
                fcs = random.randint(1, 10)
                rcv = random.randint(1, 15)
                xmit = random.randint(0, 5)
            else:
                fcs = 0
                rcv = 0
                xmit = 0
            lines.append(
                f"Eth1/{i:<14d}{0:>9d}{fcs:>11d}{xmit:>11d}"
                f"{rcv:>11d}{0:>11d}{0:>12d}"
            )
        return "\n".join(lines)

    @staticmethod
    def _generate_ios(has_error: bool) -> str:
        """Cisco IOS 'show interfaces counters errors' format."""
        lines = ["Interface            Input(errs)       Output(errs)"]
        for i in range(1, 21):
            if has_error:
                in_err = random.randint(1, 15)
                out_err = random.randint(0, 5)
            else:
                in_err = 0
                out_err = 0
            lines.append(
                f"Gi1/0/{i}                        "
                f"{in_err}                  {out_err}"
            )
        return "\n".join(lines)


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

        # 收斂判斷：設備不可達時返回錯誤
        if ctx.is_old_device is not None:
            tracker = MockTimeTracker()
            device_fails = _should_device_fail(
                is_old=ctx.is_old_device,
                elapsed=tracker.get_elapsed_seconds(ctx.maintenance_id),
                converge_time=settings.mock_ping_converge_time,
            )
            if device_fails:
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
            is_down = _should_device_fail(
                is_old=ctx.is_old_device,
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
        switch_ip = ctx.switch_ip

        is_unreachable = _should_device_fail(
            is_old=ctx.is_old_device,
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
                ping_reachable = entry.get("ping_reachable", True)

                # 檢查 switch 是否可達（基於收斂邏輯）
                switch_reachable = not _should_device_fail(
                    is_old=entry.get("is_old"),
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
    # FNA (3)
    MockTransceiverFetcher,
    MockPortChannelFetcher,
    MockAclFetcher,
    # DNA (8)
    MockVersionFetcher,
    MockUplinkFetcher,
    MockFanFetcher,
    MockPowerFetcher,
    MockErrorCountFetcher,
    MockMacTableFetcher,
    MockInterfaceStatusFetcher,
    MockArpTableFetcher,
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
