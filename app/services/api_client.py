"""
External API Client.

Handles communication with the external network management API.
"""
from __future__ import annotations

import hashlib
import time
from abc import ABC, abstractmethod
from typing import Protocol

import httpx

from app.core.config import settings

# Session start time for time-based mock convergence
# All devices will converge to "reachable" over time from this point
_SESSION_START_TIME = time.time()


class ApiClientProtocol(Protocol):
    """Protocol for API clients (for dependency injection)."""

    async def fetch(
        self,
        site: str,
        function: str,
        switch_ip: str,
    ) -> str:
        """Fetch data from API."""
        ...


class BaseApiClient(ABC):
    """Abstract base class for API clients."""

    @abstractmethod
    async def fetch(
        self,
        site: str,
        function: str,
        switch_ip: str,
    ) -> str:
        """
        Fetch data from the external API.

        Args:
            site: Site identifier (t_site, m_site, etc.)
            function: API function name (get_transceiver, etc.)
            switch_ip: Target switch IP address

        Returns:
            str: Raw CLI output from the switch
        """
        ...


class ExternalApiClient(BaseApiClient):
    """
    Client for the external network management API.

    URL format: http://{server}/{site}/{function}/{switch_ip}
    """

    def __init__(
        self,
        server: str | None = None,
        timeout: int | None = None,
    ) -> None:
        """
        Initialize the API client.

        Args:
            server: API server URL (default from settings)
            timeout: Request timeout in seconds (default from settings)
        """
        self.server = server or settings.external_api_server
        self.timeout = timeout or settings.external_api_timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def fetch(
        self,
        site: str,
        function: str,
        switch_ip: str,
    ) -> str:
        """
        Fetch data from the external API.

        Args:
            site: Site identifier (t_site, m_site, etc.)
            function: API function name
            switch_ip: Target switch IP address

        Returns:
            str: Raw CLI output from the switch

        Raises:
            httpx.HTTPError: On network errors
            ValueError: On invalid response
        """
        client = await self._get_client()

        # Build URL: http://{server}/{site}/{function}/{switch_ip}
        url = f"{self.server}/{site}/{function}/{switch_ip}"

        try:
            response = await client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            raise ValueError(
                f"API error for {switch_ip}: {e.response.status_code}"
            ) from e
        except httpx.RequestError as e:
            raise ConnectionError(
                f"Failed to connect to API for {switch_ip}: {e}"
            ) from e

    async def __aenter__(self) -> ExternalApiClient:
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit."""
        await self.close()


def _ip_hash(switch_ip: str, salt: str = "") -> int:
    """Deterministic hash from IP + salt for reproducible mock data."""
    digest = hashlib.md5(
        f"{switch_ip}:{salt}".encode()
    ).hexdigest()
    return int(digest, 16)


class MockApiClient(BaseApiClient):
    """
    Mock API client for testing and development.

    Generates HPE Comware CLI format that HPE parsers can parse.
    Uses deterministic randomness based on switch_ip for consistency.
    """

    def __init__(self) -> None:
        """Initialize with mock data storage."""
        self._mock_responses: dict[str, str] = {}

    def set_mock_response(
        self,
        site: str,
        function: str,
        switch_ip: str,
        response: str,
    ) -> None:
        """Set a mock response for a specific request."""
        key = f"{site}/{function}/{switch_ip}"
        self._mock_responses[key] = response

    async def fetch(
        self,
        site: str,
        function: str,
        switch_ip: str,
        switch_hostname: str = "",
    ) -> str:
        """Return mock response."""
        key = f"{site}/{function}/{switch_ip}"

        if key in self._mock_responses:
            return self._mock_responses[key]

        return self._generate_mock_data(function, switch_ip, switch_hostname)

    def _generate_mock_data(
        self, function: str, switch_ip: str, switch_hostname: str = ""
    ) -> str:
        """Generate mock data based on function type."""
        fn = function.lower()
        if "transceiver" in fn:
            return self._generate_transceiver_mock(switch_ip)
        if "version" in fn:
            return self._generate_version_mock(switch_ip)
        if "uplink" in fn or "neighbor" in fn:
            return self._generate_neighbor_mock(switch_ip)
        # ping_many must be checked before ping
        if "ping_many" in fn:
            return self._generate_ping_many_mock(switch_ip)
        if "ping" in fn:
            return self._generate_ping_mock(switch_ip, switch_hostname)
        if "power" in fn:
            return self._generate_power_mock(switch_ip)
        if "fan" in fn:
            return self._generate_fan_mock(switch_ip)
        if "error" in fn:
            return self._generate_error_mock(switch_ip)
        if "port_channel" in fn:
            return self._generate_port_channel_mock(switch_ip)
        # Client data fetchers
        if "mac_table" in fn:
            return self._generate_mac_table_mock(switch_ip)
        if "arp_table" in fn:
            return self._generate_arp_table_mock(switch_ip)
        if "interface_status" in fn:
            return self._generate_interface_status_mock(switch_ip)
        if "acl_number" in fn:
            return self._generate_acl_mock(switch_ip)
        return f"Mock data for {function} on {switch_ip}"

    # ── HPE Comware format mock generators ───────────────────────

    def _generate_transceiver_mock(self, switch_ip: str) -> str:
        """
        Generate HPE Comware 'display transceiver' output.

        Format parsed by HpeComwareTransceiverParser.
        ~5% of ports get out-of-range power values.
        """
        port_count = 6
        lines = []

        for i in range(1, port_count + 1):
            ph = _ip_hash(switch_ip, f"xcvr-{i}")
            # ~5% chance of bad Tx or Rx power
            if ph % 20 == 0:
                tx = -14.5  # below TX_POWER_MIN (-12)
                rx = -20.1  # below RX_POWER_MIN (-18)
            else:
                tx = -2.0 + (ph % 40) / 10.0 - 2.0  # -4.0 ~ 0.0
                rx = -5.0 + (ph % 60) / 10.0 - 3.0  # -8.0 ~ 1.0
            temp = 30.0 + (ph % 200) / 10.0  # 30.0 ~ 50.0

            lines.append(f"GigabitEthernet1/0/{i}")
            lines.append(f"  TX Power : {tx:.1f} dBm")
            lines.append(f"  RX Power : {rx:.1f} dBm")
            lines.append(f"  Temperature : {temp:.1f} C")
            lines.append("")

        return "\n".join(lines)

    def _generate_version_mock(self, switch_ip: str) -> str:
        """
        Generate HPE Comware 'display version' output.

        Format parsed by HpeVersionParser.
        ~5% of devices have wrong version.
        """
        h = _ip_hash(switch_ip, "version")
        if h % 20 == 0:
            release = "6635P05"  # wrong version
        else:
            release = "6635P07"  # expected version

        return (
            "HPE Comware Platform Software\n"
            f"Comware Software, Version 7.1.070, Release {release}\n"
            "Copyright (c) 2010-2024 Hewlett Packard Enterprise "
            "Development LP\n"
            "HPE FF 5710 48SFP+ 6QS 2SL Switch\n"
            f"Uptime is 0 weeks, 1 day, 3 hours, 22 minutes\n"
        )

    def _generate_neighbor_mock(self, switch_ip: str) -> str:
        """
        Generate HPE Comware 'display lldp neighbor-information' output.

        Format parsed by HpeComwareNeighborParser.
        Neighbors match init_factory_data topology:
        - AGG (10.x.2.x) → CORE switches
        - EDGE (10.x.3.x) → AGG switches (round-robin)
        ~5% miss one expected neighbor.
        """
        h = _ip_hash(switch_ip, "neighbor")
        parts = switch_ip.split(".")
        third_octet = int(parts[2]) if len(parts) == 4 else 0
        dev_num = int(parts[-1]) if len(parts) == 4 else 1

        if third_octet == 2:
            # AGG → CORE uplinks
            neighbors = [
                ("SW-NEW-001-CORE", "HGE1/0/1"),
                ("SW-NEW-002-CORE", "HGE1/0/1"),
            ]
        elif third_octet == 3:
            # EDGE → AGG uplinks (round-robin matching init_factory_data)
            edge_idx = dev_num - 11
            agg_num_1 = (edge_idx % 8) + 3
            agg_num_2 = ((edge_idx + 1) % 8) + 3
            neighbors = [
                (f"SW-NEW-{agg_num_1:03d}-AGG", f"XGE1/0/{edge_idx + 1}"),
                (f"SW-NEW-{agg_num_2:03d}-AGG", f"XGE1/0/{edge_idx + 1}"),
            ]
        else:
            # CORE or unknown → generic neighbors
            neighbors = [
                ("SW-NEW-001-CORE", "HGE1/0/49"),
                ("SW-NEW-002-CORE", "HGE1/0/49"),
            ]

        # ~5% chance: missing second neighbor
        if h % 20 == 0:
            neighbors = neighbors[:1]

        lines = []
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

        return "\n".join(lines)

    def _generate_ping_mock(self, switch_ip: str, switch_hostname: str = "") -> str:
        """
        Generate standard ping output with unified convergence logic.

        Format parsed by HpePingParser (generic ping format).

        統一收斂邏輯（基於 hostname 判斷設備類型）：
        - 使用 hostname 中的 -OLD/-NEW 判斷設備類型
        - 收斂時間點 = MOCK_PING_CONVERGE_TIME / 2
        - 收斂前：OLD 設備可達，NEW 設備不可達
        - 收斂後：OLD 設備不可達，NEW 設備可達

        This simulates a maintenance scenario where:
        1. PRE phase: Old devices online, new devices offline
        2. Transition at converge_time/2
        3. POST phase: Old devices offline, new devices online
        """
        hostname_upper = switch_hostname.upper()
        is_old_device = "-OLD" in hostname_upper
        is_new_device = "-NEW" in hostname_upper

        # Calculate time-based convergence
        elapsed = time.time() - _SESSION_START_TIME
        converge_time = settings.mock_ping_converge_time

        if converge_time <= 0:
            # Instant convergence
            has_converged = True
        else:
            # 統一收斂時間點 = converge_time / 2
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

        # Generate ping output
        if is_reachable:
            return (
                f"PING {switch_ip} ({switch_ip}): 56 data bytes\n"
                f"64 bytes from {switch_ip}: icmp_seq=0 ttl=64 time=1.2 ms\n"
                f"64 bytes from {switch_ip}: icmp_seq=1 ttl=64 time=1.1 ms\n"
                f"64 bytes from {switch_ip}: icmp_seq=2 ttl=64 time=1.3 ms\n"
                f"\n"
                f"--- {switch_ip} ping statistics ---\n"
                f"5 packets transmitted, 5 packets received, "
                f"0% packet loss\n"
                f"round-trip min/avg/max = 1.1/1.2/1.3 ms\n"
            )
        else:
            return (
                f"PING {switch_ip} ({switch_ip}): 56 data bytes\n"
                f"Request timeout for icmp_seq 0\n"
                f"Request timeout for icmp_seq 1\n"
                f"Request timeout for icmp_seq 2\n"
                f"\n"
                f"--- {switch_ip} ping statistics ---\n"
                f"5 packets transmitted, 0 packets received, "
                f"100% packet loss\n"
            )

    def _generate_power_mock(self, switch_ip: str) -> str:
        """
        Generate HPE Comware 'display power' output.

        Format parsed by HpePowerParser.
        ~5% of devices have a failed PSU.
        """
        h = _ip_hash(switch_ip, "power")
        if h % 20 == 0:
            ps2_status = "Absent"
        else:
            ps2_status = "Normal"

        return (
            "Slot 1:\n"
            "PowerID State    Mode   Current(A)  Voltage(V)  "
            "Power(W)  FanDirection\n"
            "1       Normal   AC     --          --          "
            "--        Back-to-front\n"
            f"2       {ps2_status}   AC     --          --          "
            "--        Back-to-front\n"
        )

    def _generate_fan_mock(self, switch_ip: str) -> str:
        """
        Generate HPE Comware 'display fan' output.

        Format parsed by HpeFanParser.
        ~3% of devices have a failed fan.
        """
        h = _ip_hash(switch_ip, "fan")
        if h % 30 == 0:
            fan3_status = "Absent"
        else:
            fan3_status = "Normal"

        return (
            "Slot 1:\n"
            "FanID    Status      Direction\n"
            "1        Normal      Back-to-front\n"
            "2        Normal      Back-to-front\n"
            f"3        {fan3_status}      Back-to-front\n"
            "4        Normal      Back-to-front\n"
        )

    def _generate_error_mock(self, switch_ip: str) -> str:
        """
        Generate HPE Comware 'display counters error' output.

        Format parsed by HpeErrorParser.
        ~5% of interfaces have errors.
        """
        lines = [
            "Interface            Input(errs)       Output(errs)"
        ]

        for i in range(1, 21):
            ph = _ip_hash(switch_ip, f"err-{i}")
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

        return "\n".join(lines)

    def _generate_port_channel_mock(self, switch_ip: str) -> str:
        """
        Generate HPE Comware 'display link-aggregation summary' output.

        Format parsed by HpePortChannelParser.
        Members match init_factory_data expectations:
        - AGG (10.x.2.x): HGE1/0/25, HGE1/0/26
        - EDGE (10.x.3.x): XGE1/0/51, XGE1/0/52
        ~5% of port-channels have a down member.
        """
        h = _ip_hash(switch_ip, "port_channel")

        # Member status: S = Selected (UP), U = Unselected (DOWN)
        if h % 20 == 0:
            m1_status = "U"  # DOWN
        else:
            m1_status = "S"  # UP

        # Determine device type from IP pattern
        parts = switch_ip.split(".")
        third_octet = int(parts[2]) if len(parts) == 4 else 0

        if third_octet == 2:
            # AGG switches: HGE1/0/25, HGE1/0/26
            m1, m2 = "HGE1/0/25", "HGE1/0/26"
        else:
            # EDGE switches: XGE1/0/51, XGE1/0/52
            m1, m2 = "XGE1/0/51", "XGE1/0/52"

        lines = [
            "AggID   Interface   Link   Attribute   Mode   Members",
        ]
        lines.append(
            f"1       BAGG1       UP     A           LACP   "
            f"{m1}({m1_status}) {m2}(S)"
        )

        return "\n".join(lines)

    # ── Client data mock generators ────────────────────────────

    def _generate_mac_table_mock(self, switch_ip: str) -> str:
        """
        Generate mock MAC table output.

        Format: CSV with header.
        Parsers should expect: mac_address, interface_name, vlan_id

        Uses fixed MAC pattern (AA:BB:CC:DD:EE:01-10) to match
        typical MaintenanceMacList entries for testing.
        """
        lines = ["MAC,Interface,VLAN"]
        # Use fixed MAC pattern to match typical Client list entries
        for i in range(1, 11):  # Generate 10 clients per switch
            mac = f"AA:BB:CC:DD:EE:{i:02d}"
            vlan = 100 + (i % 5) * 10  # 100, 110, 120, 130, 140
            lines.append(f"{mac},GE1/0/{i},{vlan}")
        return "\n".join(lines)

    def _generate_arp_table_mock(self, switch_ip: str) -> str:
        """
        Generate mock ARP table output with time-based MAC migration.

        Format: CSV with header.
        Parsers should expect: ip_address, mac_address

        時間軸模型 (MAC 遷移):
        - OLD devices (IP last octet 10-19):
          t=0 有 MAC → 收斂後沒有 MAC (客戶端已遷移)
        - NEW devices (IP last octet 20-29):
          t=0 沒有 MAC → 收斂後有 MAC (客戶端已遷移到新設備)
        - Other devices: always show MACs

        Client MAC patterns (matching test data):
        - AA:BB:CC:11:11:01~03 (10.1.1.1~3) - R1 區域
        - AA:BB:CC:22:22:01~03 (10.1.2.1~3) - R2 區域
        - AA:BB:CC:33:33:01~02 (10.1.3.1~2) - 跨區域
        """
        # Parse last octet of IP address
        try:
            last_octet = int(switch_ip.split(".")[-1])
        except (ValueError, IndexError):
            last_octet = 0

        # Calculate time-based convergence
        h = _ip_hash(switch_ip, "arp")
        elapsed = time.time() - _SESSION_START_TIME
        converge_time = settings.mock_ping_converge_time

        if converge_time <= 0:
            device_converged = True
        else:
            device_switch_time = h % converge_time
            device_converged = elapsed >= device_switch_time

        # Determine if this device should show MACs
        # OLD devices (10-19): 收斂前有 MAC，收斂後沒有
        if 10 <= last_octet <= 19:
            show_macs = not device_converged
        # NEW devices (20-29): 收斂前沒有 MAC，收斂後有
        elif 20 <= last_octet <= 29:
            show_macs = device_converged
        # Other devices: always show
        else:
            show_macs = True

        lines = ["IP,MAC"]

        if show_macs:
            # ArpSource (通常是 Core Router) 會看到所有客戶端的 ARP 記錄
            # 每個 ArpSource 都返回完整的客戶端清單，確保不會遺漏任何 MAC
            all_clients = [
                # R1 區域客戶端
                ("AA:BB:CC:11:11:01", "10.1.1.1"),
                ("AA:BB:CC:11:11:02", "10.1.1.2"),
                ("AA:BB:CC:11:11:03", "10.1.1.3"),
                # R2 區域客戶端
                ("AA:BB:CC:22:22:01", "10.1.2.1"),
                ("AA:BB:CC:22:22:02", "10.1.2.2"),
                ("AA:BB:CC:22:22:03", "10.1.2.3"),
                # 跨區域客戶端
                ("AA:BB:CC:33:33:01", "10.1.3.1"),
                ("AA:BB:CC:33:33:02", "10.1.3.2"),
            ]

            for mac, ip in all_clients:
                lines.append(f"{ip},{mac}")

        return "\n".join(lines)

    def _generate_interface_status_mock(self, switch_ip: str) -> str:
        """
        Generate mock interface status output.

        Format: CSV with header.
        Parsers should expect: interface_name, link_status, speed, duplex
        """
        lines = ["Interface,Status,Speed,Duplex"]
        port_count = 20
        for i in range(1, port_count + 1):
            h = _ip_hash(switch_ip, f"if-{i}")
            status = "DOWN" if h % 25 == 0 else "UP"
            speed = "10G" if i <= 4 else "1000M"
            duplex = "full"
            lines.append(f"GE1/0/{i},{status},{speed},{duplex}")
        return "\n".join(lines)

    def _generate_acl_mock(self, switch_ip: str) -> str:
        """
        Generate mock ACL-per-interface output.

        Format: CSV with header.
        Parsers should expect: interface_name, acl_number (empty = no ACL)
        """
        lines = ["Interface,ACL"]
        port_count = 20
        for i in range(1, port_count + 1):
            h = _ip_hash(switch_ip, f"acl-{i}")
            # ~70% of ports have ACL 3001 applied
            acl = "3001" if h % 10 < 7 else ""
            lines.append(f"GE1/0/{i},{acl}")
        return "\n".join(lines)

    def _generate_ping_many_mock(self, switch_ip: str) -> str:
        """
        Generate mock ping_many output for client IP reachability.

        Format: CSV with header.
        Parsers should expect: ip_address, is_reachable

        Client IPs matching test data:
        - 10.1.1.1~3 - R1 區域客戶端
        - 10.1.2.1~3 - R2 區域客戶端
        - 10.1.3.1~2 - 跨區域客戶端

        ~10% of clients are randomly unreachable to simulate issues.
        """
        lines = ["IP,Reachable"]

        # Client IPs matching test data
        client_ips = [
            "10.1.1.1", "10.1.1.2", "10.1.1.3",  # R1 區域
            "10.1.2.1", "10.1.2.2", "10.1.2.3",  # R2 區域
            "10.1.3.1", "10.1.3.2",              # 跨區域
        ]

        for ip in client_ips:
            h = _ip_hash(ip, "ping-client")
            # ~10% of clients are unreachable
            reachable = "false" if h % 10 == 0 else "true"
            lines.append(f"{ip},{reachable}")

        return "\n".join(lines)


# Factory function for getting API client
def get_api_client(use_mock: bool = False) -> BaseApiClient:
    """
    Get an API client instance.

    Priority:
    1. use_mock parameter (explicit override from code)
    2. USE_MOCK_API env var (from .env)

    Args:
        use_mock: If True, return MockApiClient

    Returns:
        BaseApiClient: API client instance
    """
    if use_mock or settings.use_mock_api:
        return MockApiClient()
    return ExternalApiClient()
