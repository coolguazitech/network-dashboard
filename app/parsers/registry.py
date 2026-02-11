"""
Parser Registry — Parser 的全域註冊中心與自動發現機制。

本模組負責管理所有已註冊的 Parser 實例，讓系統能透過
(device_type, command) 二元組快速找到對應的 Parser。

核心概念：
    1. ParserRegistry 是 Singleton（全域唯一實例）
    2. ParserKey = (device_type, command)
    3. 自動發現：auto_discover_parsers() 掃描 plugins/ 目錄

Parser 與 Indicator 完全解耦：
    - Parser 只負責 raw text → ParsedData
    - Indicator 自己決定需要哪些 Parser 的資料
"""
from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path
from typing import Any

from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, ParserKey


class ParserRegistry:
    """
    Parser 的全域註冊中心（Singleton 模式）。

    使用方式：
        # 註冊
        parser_registry.register(MyParser())

        # 查詢 by command
        parser = parser_registry.get("get_fan_hpe_dna")

        # 查詢 by device_type + command
        parser = parser_registry.get("get_fan_hpe_dna", device_type=DeviceType.HPE)

        # 列出所有已註冊的 parser
        all_keys = parser_registry.list_parsers()
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
        """Register a parser."""
        key = ParserKey(
            device_type=parser.device_type,
            command=parser.command,
        )
        self._parsers[key] = parser

    def get(
        self,
        command: str,
        device_type: DeviceType | None = None,
    ) -> BaseParser[Any] | None:
        """
        Get a parser by command (and optionally device_type).

        Lookup order:
            1. Exact match: (device_type, command)
            2. Generic fallback: (None, command)

        Args:
            command: API name (e.g., "get_fan_hpe_dna")
            device_type: Optional device type for exact match

        Returns:
            Parser instance or None if not found
        """
        if device_type is not None:
            key = ParserKey(device_type=device_type, command=command)
            parser = self._parsers.get(key)
            if parser is not None:
                return parser

        # Generic fallback (device_type=None)
        generic_key = ParserKey(device_type=None, command=command)
        return self._parsers.get(generic_key)

    def get_or_raise(
        self,
        command: str,
        device_type: DeviceType | None = None,
    ) -> BaseParser[Any]:
        """Get a parser, raising exception if not found."""
        parser = self.get(command, device_type)
        if parser is None:
            raise ValueError(
                f"No parser found for command='{command}'"
                f" device_type={device_type}"
            )
        return parser

    def list_parsers(self) -> list[ParserKey]:
        """List all registered parser keys."""
        return list(self._parsers.keys())

    def list_by_device_type(self, device_type: DeviceType) -> list[ParserKey]:
        """List parsers for a specific device type."""
        return [k for k in self._parsers.keys() if k.device_type == device_type]

    def list_by_command(self, command: str) -> list[ParserKey]:
        """List parsers for a specific command."""
        return [k for k in self._parsers.keys() if k.command == command]

    def clear(self) -> None:
        """Clear all registered parsers (mainly for testing)."""
        self._parsers.clear()


# Global registry instance
parser_registry = ParserRegistry()


def register_parser(parser: BaseParser[Any]) -> BaseParser[Any]:
    """Register a parser (can be used as decorator or direct call)."""
    if isinstance(parser, type):
        instance = parser()
        parser_registry.register(instance)
        return parser  # type: ignore
    else:
        parser_registry.register(parser)
        return parser


def auto_discover_parsers(package_path: str = "app.parsers.plugins") -> int:
    """Auto-discover and load all parser modules in plugins directory."""
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
                print(f"Warning: Failed to import {module_name}: {e}")

    except ImportError:
        pass

    return count
