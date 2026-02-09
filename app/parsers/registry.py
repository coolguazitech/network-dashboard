"""
Parser Registry — Parser 的全域註冊中心與自動發現機制。

==========================================================================
本模組負責管理所有已註冊的 Parser 實例，讓系統能透過
(device_type, indicator_type) 二元組快速找到對應的 Parser。
==========================================================================

核心概念：
    1. ParserRegistry 是 Singleton（全域唯一實例）
       - 整個應用程式共用同一個 registry
       - 透過 parser_registry = ParserRegistry() 取得全域實例

    2. ParserKey 是查詢鍵（定義在 protocols.py）
       - 由 (device_type, indicator_type) 組成
       - 例如：ParserKey(device_type=DeviceType.CISCO_NXOS, indicator_type="transceiver")

    3. 自動發現機制
       - app/parsers/plugins/ 目錄下的所有 .py 檔案都是 parser plugin
       - plugins/__init__.py 中的 import 觸發每個 plugin 的模組載入
       - 每個 plugin 在模組底部呼叫 parser_registry.register() 完成自註冊

資料流：如何從 DataCollectionService 找到 Parser
    DataCollectionService:
        1. 從設備資料取得 device_type=DeviceType.CISCO_NXOS
        2. 要採集 indicator_type="transceiver"
        3. 呼叫 parser_registry.get(device_type, indicator_type)
        4. 取回 CiscoNxosTransceiverParser 實例
        5. 呼叫 parser.parse(raw_output) 取得 list[TransceiverData]

重要關係：fetch_type == indicator_type
    - Fetcher 的 fetch_type（採集哪種資料）必須與 Parser 的 indicator_type 一致
    - 這是系統自動配對 Fetcher ↔ Parser 的關鍵

如何新增一個全新設備類型的 Parser：
    1. 確認 app/core/enums.py 中已有對應的 DeviceType 值
    2. 建立 app/parsers/plugins/xxx_transceiver.py（見 BaseParser docstring）
    3. 在檔案底部 parser_registry.register(XxxTransceiverParser())
    4. 在 app/parsers/plugins/__init__.py 加上 from . import xxx_transceiver
    5. 系統啟動時自動載入，registry 中就有了新的 Parser
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
        # 註冊（通常在 plugin 檔案底部）
        parser_registry.register(MyParser())

        # 查詢（通常在 DataCollectionService 中）
        parser = parser_registry.get(DeviceType.CISCO_NXOS, "transceiver")
        if parser:
            results = parser.parse(raw_output)

        # 查詢（找不到就拋錯）
        parser = parser_registry.get_or_raise(device_type, indicator_type)

        # 列出所有已註冊的 parser
        all_keys = parser_registry.list_parsers()

        # 依設備類型篩選
        cisco_parsers = parser_registry.list_by_device_type(DeviceType.CISCO_NXOS)

    內部結構：
        _parsers: dict[ParserKey, BaseParser]
        - key = ParserKey(device_type, indicator_type)
        - value = Parser 實例
        - 同一個 ParserKey 只能註冊一個 Parser（後註冊的會覆蓋前者）
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
            device_type=parser.device_type,
            indicator_type=parser.indicator_type,
        )
        self._parsers[key] = parser

    def get(
        self,
        device_type: DeviceType,
        indicator_type: str,
    ) -> BaseParser[Any] | None:
        """
        Get a parser by device type and indicator type.

        Lookup order:
            1. Exact match: (device_type, indicator_type)
            2. Generic fallback: (None, indicator_type)

        Args:
            device_type: Device type (e.g., DeviceType.CISCO_NXOS)
            indicator_type: Type of indicator (e.g., "transceiver")

        Returns:
            Parser instance or None if not found
        """
        # 1. Exact match
        key = ParserKey(
            device_type=device_type,
            indicator_type=indicator_type,
        )
        parser = self._parsers.get(key)
        if parser is not None:
            return parser

        # 2. Generic fallback (device_type=None)
        generic_key = ParserKey(
            device_type=None,
            indicator_type=indicator_type,
        )
        return self._parsers.get(generic_key)

    def get_or_raise(
        self,
        device_type: DeviceType,
        indicator_type: str,
    ) -> BaseParser[Any]:
        """
        Get a parser, raising exception if not found.

        Args:
            device_type: Device type
            indicator_type: Type of indicator

        Returns:
            Parser instance

        Raises:
            ValueError: If no parser found
        """
        parser = self.get(device_type, indicator_type)
        if parser is None:
            raise ValueError(
                f"No parser found for {device_type}/{indicator_type}"
                f" (no generic fallback either)"
            )
        return parser

    def list_parsers(self) -> list[ParserKey]:
        """List all registered parser keys."""
        return list(self._parsers.keys())

    def list_by_device_type(self, device_type: DeviceType) -> list[ParserKey]:
        """List parsers for a specific device type."""
        return [k for k in self._parsers.keys() if k.device_type == device_type]

    def list_by_indicator(self, indicator_type: str) -> list[ParserKey]:
        """List parsers for a specific indicator type."""
        return [
            k for k in self._parsers.keys()
            if k.indicator_type == indicator_type
        ]

    def clear(self) -> None:
        """Clear all registered parsers (mainly for testing)."""
        self._parsers.clear()


# Global registry instance
parser_registry = ParserRegistry()


def register_parser(parser: BaseParser[Any]) -> BaseParser[Any]:
    """
    註冊 Parser 的便捷函式（可當 decorator 或直接呼叫）。

    Args:
        parser: Parser 類別（會自動實例化）或 Parser 實例

    Returns:
        傳入的 parser（方便 decorator 鏈式使用）
    """
    if isinstance(parser, type):
        instance = parser()
        parser_registry.register(instance)
        return parser  # type: ignore
    else:
        parser_registry.register(parser)
        return parser


def auto_discover_parsers(package_path: str = "app.parsers.plugins") -> int:
    """
    自動掃描 plugins 目錄，載入所有 parser 模組。

    Args:
        package_path: plugins package 的 dotted path

    Returns:
        int: 成功載入的模組數量
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
                print(f"Warning: Failed to import {module_name}: {e}")

    except ImportError:
        pass

    return count
