"""
External API Client.

Handles communication with the external network management API.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Protocol

import httpx

from app.core.config import settings


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


class MockApiClient(BaseApiClient):
    """
    Mock API client for testing and development.

    Returns predefined mock data instead of making real API calls.
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
        """
        Set a mock response for a specific request.

        Args:
            site: Site identifier
            function: API function name
            switch_ip: Target switch IP
            response: Mock response to return
        """
        key = f"{site}/{function}/{switch_ip}"
        self._mock_responses[key] = response

    async def fetch(
        self,
        site: str,
        function: str,
        switch_ip: str,
    ) -> str:
        """
        Return mock response.

        Args:
            site: Site identifier
            function: API function name
            switch_ip: Target switch IP

        Returns:
            str: Mock CLI output
        """
        key = f"{site}/{function}/{switch_ip}"

        if key in self._mock_responses:
            return self._mock_responses[key]

        # Return generic mock data based on function
        return self._generate_mock_data(function, switch_ip)

    def _generate_mock_data(self, function: str, switch_ip: str) -> str:
        """Generate mock data based on function type."""
        if "transceiver" in function.lower():
            return self._generate_transceiver_mock(switch_ip)
        if "version" in function.lower():
            return self._generate_version_mock()
        if "neighbor" in function.lower():
            return self._generate_neighbor_mock()
        return f"Mock data for {function} on {switch_ip}"

    def _generate_transceiver_mock(self, switch_ip: str) -> str:
        """Generate mock transceiver data."""
        import random

        lines = []
        for i in range(1, 9):
            interface = f"Ethernet1/{i}"
            tx = round(random.uniform(-4.0, -1.0), 2)
            rx = round(random.uniform(-8.0, -2.0), 2)
            temp = round(random.uniform(30.0, 45.0), 1)
            voltage = round(random.uniform(3.2, 3.4), 2)

            lines.append(f"{interface}")
            lines.append("    transceiver is present")
            lines.append("    type is QSFP-40G-SR4")
            lines.append(f"    Temperature            {temp} C")
            lines.append(f"    Voltage                {voltage} V")
            lines.append(f"    Tx Power               {tx} dBm")
            lines.append(f"    Rx Power               {rx} dBm")
            lines.append("")

        return "\n".join(lines)

    def _generate_version_mock(self) -> str:
        """Generate mock version data."""
        return """
Cisco Nexus Operating System (NX-OS) Software
Software
  BIOS: version 08.38
  NXOS: version 9.3(8)
  BIOS compile time: 06/07/2022
  NXOS image file is: bootflash:///nxos.9.3.8.bin
Hardware
  cisco Nexus9000 C9336C-FX2 Chassis
  Memory:  16388352 kB
"""

    def _generate_neighbor_mock(self) -> str:
        """Generate mock neighbor data."""
        return """
Device ID        Local Intrfc  Hldtme Capability  Port ID
switch-02        Eth1/1        120    R S         Eth1/1
switch-03        Eth1/2        120    R S         Eth1/1
"""


# Factory function for getting API client
def get_api_client(use_mock: bool = False) -> BaseApiClient:
    """
    Get an API client instance.

    Args:
        use_mock: If True, return MockApiClient

    Returns:
        BaseApiClient: API client instance
    """
    if use_mock or settings.app_env == "testing":
        return MockApiClient()
    return ExternalApiClient()
