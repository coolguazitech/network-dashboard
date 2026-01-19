"""
Parser Registry - Auto-discovery and registration of parsers.

Implements Singleton pattern for global registry access.
Follows Open-Closed Principle: add new parsers without modifying this file.
"""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any

from app.core.enums import PlatformType, VendorType
from app.parsers.protocols import BaseParser, ParserKey


class ParserRegistry:
    """
    Registry for all available parsers.

    Singleton pattern ensures global access to parser registry.
    Supports auto-discovery of parser plugins.
    """

    _instance: ParserRegistry | None = None
    _parsers: dict[ParserKey, BaseParser[Any]]
    _initialized: bool = False

    def __new__(cls) -> ParserRegistry:
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._parsers = {}
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize registry (only once due to singleton)."""
        if not self._initialized:
            self._initialized = True

    def register(self, parser: BaseParser[Any]) -> None:
        """
        Register a parser.

        Args:
            parser: Parser instance to register
        """
        key = ParserKey(
            vendor=parser.vendor,
            platform=parser.platform,
            indicator_type=parser.indicator_type,
        )
        self._parsers[key] = parser

    def get(
        self,
        vendor: VendorType,
        platform: PlatformType,
        indicator_type: str,
    ) -> BaseParser[Any] | None:
        """
        Get a parser by vendor, platform, and indicator type.

        Args:
            vendor: Vendor type (e.g., CISCO)
            platform: Platform type (e.g., NXOS)
            indicator_type: Type of indicator (e.g., "transceiver")

        Returns:
            Parser instance or None if not found
        """
        key = ParserKey(
            vendor=vendor,
            platform=platform,
            indicator_type=indicator_type,
        )
        return self._parsers.get(key)

    def get_or_raise(
        self,
        vendor: VendorType,
        platform: PlatformType,
        indicator_type: str,
    ) -> BaseParser[Any]:
        """
        Get a parser, raising exception if not found.

        Args:
            vendor: Vendor type
            platform: Platform type
            indicator_type: Type of indicator

        Returns:
            Parser instance

        Raises:
            ValueError: If no parser found
        """
        parser = self.get(vendor, platform, indicator_type)
        if parser is None:
            raise ValueError(
                f"No parser found for {vendor}/{platform}/{indicator_type}"
            )
        return parser

    def list_parsers(self) -> list[ParserKey]:
        """List all registered parser keys."""
        return list(self._parsers.keys())

    def list_by_vendor(self, vendor: VendorType) -> list[ParserKey]:
        """List parsers for a specific vendor."""
        return [k for k in self._parsers.keys() if k.vendor == vendor]

    def list_by_indicator(self, indicator_type: str) -> list[ParserKey]:
        """List parsers for a specific indicator type."""
        return [
            k for k in self._parsers.keys()
            if k.indicator_type == indicator_type
        ]

    def unregister(
        self,
        vendor: VendorType,
        platform: PlatformType,
        indicator_type: str,
    ) -> bool:
        """
        Unregister a parser.

        Args:
            vendor: Vendor type
            platform: Platform type
            indicator_type: Type of indicator

        Returns:
            True if parser was removed, False if not found
        """
        key = ParserKey(
            vendor=vendor,
            platform=platform,
            indicator_type=indicator_type,
        )
        if key in self._parsers:
            del self._parsers[key]
            return True
        return False

    def clear(self) -> None:
        """Clear all registered parsers (mainly for testing)."""
        self._parsers.clear()


# Global registry instance
parser_registry = ParserRegistry()


def register_parser(parser: BaseParser[Any]) -> BaseParser[Any]:
    """
    Decorator/function to register a parser.

    Can be used as a decorator:
        @register_parser
        class MyParser(BaseParser[MyData]):
            ...

    Or called directly:
        register_parser(MyParser())

    Args:
        parser: Parser class or instance

    Returns:
        The parser (for decorator use)
    """
    if isinstance(parser, type):
        # It's a class, instantiate it
        instance = parser()
        parser_registry.register(instance)
        return parser  # type: ignore
    else:
        # It's an instance
        parser_registry.register(parser)
        return parser


def auto_discover_parsers(package_path: str = "app.parsers.plugins") -> int:
    """
    Auto-discover and register all parsers in the plugins package.

    Scans the plugins directory for parser modules and imports them.
    Parsers should self-register using the @register_parser decorator.

    Args:
        package_path: Dotted path to the plugins package

    Returns:
        int: Number of modules loaded
    """
    count = 0
    try:
        package = importlib.import_module(package_path)
        package_dir = Path(package.__file__).parent  # type: ignore

        for module_info in pkgutil.iter_modules([str(package_dir)]):
            module_name = f"{package_path}.{module_info.name}"
            try:
                importlib.import_module(module_name)
                count += 1
            except ImportError as e:
                # Log warning but continue
                print(f"Warning: Failed to import {module_name}: {e}")

    except ImportError:
        # Package doesn't exist yet, that's okay
        pass

    return count
