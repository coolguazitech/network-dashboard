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
        self.server = server or settings.fetcher_source.gnmsping.base_url
        self.timeout = timeout or settings.fetcher_source.gnmsping.timeout
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


def get_api_client() -> ExternalApiClient:
    """Get an API client instance."""
    return ExternalApiClient()
