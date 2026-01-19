"""
Parser protocols and base types.

Defines the interface that all parsers must implement.
Uses Protocol for structural subtyping (duck typing with type hints).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from app.core.enums import PlatformType, VendorType

# Type variable for parsed result
TResult = TypeVar("TResult", bound=BaseModel)


class ParsedData(BaseModel):
    """Base class for all parsed data."""

    pass


class TransceiverData(ParsedData):
    """Parsed transceiver (optical module) data."""

    interface_name: str
    tx_power: float | None = None
    rx_power: float | None = None
    temperature: float | None = None
    voltage: float | None = None
    current: float | None = None
    serial_number: str | None = None
    part_number: str | None = None


class InterfaceErrorData(ParsedData):
    """Parsed interface error counters."""

    interface_name: str
    crc_errors: int = 0
    input_errors: int = 0
    output_errors: int = 0
    collisions: int = 0
    giants: int = 0
    runts: int = 0
    
class FanStatusData(ParsedData):
    """Parsed fan status data."""

    fan_id: str
    status: str
    speed_rpm: int | None = None
    speed_percent: int | None = None


class VersionData(ParsedData):
    """Parsed version/firmware data."""

    version: str
    model: str | None = None
    serial_number: str | None = None
    uptime: str | None = None


class NeighborData(ParsedData):
    """Parsed neighbor (CDP/LLDP) data."""

    local_interface: str
    remote_hostname: str
    remote_interface: str
    remote_platform: str | None = None


class BaseParser(ABC, Generic[TResult]):
    """
    Abstract base class for all parsers.

    Each parser handles one specific type of data for one vendor/platform.
    Follows Single Responsibility Principle.

    Type Parameters:
        TResult: The Pydantic model type that this parser produces
    """

    # Class attributes to be set by subclasses
    vendor: VendorType
    platform: PlatformType
    indicator_type: str  # e.g., "transceiver", "error_count"
    command: str  # CLI command to execute

    @abstractmethod
    def parse(self, raw_output: str) -> list[TResult]:
        """
        Parse raw CLI output into structured data.

        Args:
            raw_output: Raw CLI output string

        Returns:
            list[TResult]: List of parsed data objects
        """
        ...

    def can_parse(self, raw_output: str) -> bool:
        """
        Check if this parser can handle the given output.

        Default implementation returns True.
        Override for format validation.

        Args:
            raw_output: Raw CLI output string

        Returns:
            bool: True if this parser can handle the output
        """
        return True


class ParserKey(BaseModel):
    """Key for identifying a parser in the registry."""

    vendor: VendorType
    platform: PlatformType
    indicator_type: str

    def __hash__(self) -> int:
        """Make hashable for use as dict key."""
        return hash((self.vendor, self.platform, self.indicator_type))

    def __eq__(self, other: object) -> bool:
        """Equality comparison."""
        if not isinstance(other, ParserKey):
            return False
        return (
            self.vendor == other.vendor
            and self.platform == other.platform
            and self.indicator_type == other.indicator_type
        )
