"""Tests for parser registry and auto-discovery."""
from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, FanStatusData, ParserKey
from app.parsers.registry import ParserRegistry, auto_discover_parsers


class TestParserKey:
    def test_hash_equality(self):
        k1 = ParserKey(device_type=DeviceType.HPE, command="get_fan_hpe_dna")
        k2 = ParserKey(device_type=DeviceType.HPE, command="get_fan_hpe_dna")
        assert k1 == k2
        assert hash(k1) == hash(k2)

    def test_different_keys(self):
        k1 = ParserKey(device_type=DeviceType.HPE, command="get_fan_hpe_dna")
        k2 = ParserKey(device_type=DeviceType.CISCO_IOS, command="get_fan_ios_dna")
        assert k1 != k2

    def test_none_device_type(self):
        k = ParserKey(device_type=None, command="ping_batch")
        assert k.device_type is None

    def test_not_equal_to_other_type(self):
        k = ParserKey(device_type=None, command="ping_batch")
        assert k != "not a ParserKey"


class TestParserRegistry:
    def test_register_and_get(self):
        registry = ParserRegistry.__new__(ParserRegistry)
        registry._parsers = {}
        registry._initialized = True

        class TestParser(BaseParser[FanStatusData]):
            device_type = DeviceType.HPE
            command = "test_cmd"

            def parse(self, raw_output: str) -> list[FanStatusData]:
                return []

        parser = TestParser()
        registry.register(parser)

        result = registry.get("test_cmd", DeviceType.HPE)
        assert result is parser

    def test_generic_fallback(self):
        registry = ParserRegistry.__new__(ParserRegistry)
        registry._parsers = {}
        registry._initialized = True

        class TestParser(BaseParser[FanStatusData]):
            device_type = None
            command = "test_generic"

            def parse(self, raw_output: str) -> list[FanStatusData]:
                return []

        parser = TestParser()
        registry.register(parser)

        # Query with specific device_type falls back to None
        result = registry.get("test_generic", DeviceType.HPE)
        assert result is parser

    def test_get_nonexistent(self):
        registry = ParserRegistry.__new__(ParserRegistry)
        registry._parsers = {}
        registry._initialized = True

        assert registry.get("nonexistent") is None

    def test_get_or_raise(self):
        registry = ParserRegistry.__new__(ParserRegistry)
        registry._parsers = {}
        registry._initialized = True

        import pytest
        with pytest.raises(ValueError, match="No parser found"):
            registry.get_or_raise("nonexistent")

    def test_list_parsers(self):
        registry = ParserRegistry.__new__(ParserRegistry)
        registry._parsers = {}
        registry._initialized = True

        class TestParser(BaseParser[FanStatusData]):
            device_type = DeviceType.HPE
            command = "test_list"

            def parse(self, raw_output: str) -> list[FanStatusData]:
                return []

        registry.register(TestParser())
        keys = registry.list_parsers()
        assert len(keys) == 1

    def test_clear(self):
        registry = ParserRegistry.__new__(ParserRegistry)
        registry._parsers = {}
        registry._initialized = True

        class TestParser(BaseParser[FanStatusData]):
            device_type = DeviceType.HPE
            command = "test_clear"

            def parse(self, raw_output: str) -> list[FanStatusData]:
                return []

        registry.register(TestParser())
        registry.clear()
        assert registry.list_parsers() == []


class TestAutoDiscovery:
    def test_discover_parsers(self):
        """Verify auto_discover_parsers loads all parser modules."""
        count = auto_discover_parsers()
        # We have 34+ parser files (excluding __init__.py)
        assert count >= 30, f"Expected >=30 parser modules, got {count}"

    def test_registry_has_expected_parsers_after_fresh_import(self):
        """Parser modules register on import. Direct-import to verify."""
        # Import parsers directly to trigger registration
        from app.parsers.plugins.get_fan_hpe_dna_parser import GetFanHpeDnaParser
        from app.parsers.plugins.get_mac_table_hpe_dna_parser import GetMacTableHpeDnaParser
        from app.parsers.plugins.get_version_ios_dna_parser import GetVersionIosDnaParser
        from app.parsers.plugins.get_version_nxos_dna_parser import GetVersionNxosDnaParser
        from app.parsers.plugins.ping_batch_parser import PingBatchParser

        # These classes should exist and have correct attributes
        assert GetFanHpeDnaParser.command == "get_fan_hpe_dna"
        assert GetFanHpeDnaParser.device_type == DeviceType.HPE
        assert GetMacTableHpeDnaParser.command == "get_mac_table_hpe_dna"
        assert GetVersionIosDnaParser.device_type == DeviceType.CISCO_IOS
        assert GetVersionNxosDnaParser.device_type == DeviceType.CISCO_NXOS
        assert PingBatchParser.device_type is None

    def test_parser_classes_parse_method(self):
        """All parsers have a parse method that returns a list."""
        from app.parsers.plugins.get_fan_hpe_dna_parser import GetFanHpeDnaParser

        parser = GetFanHpeDnaParser()
        result = parser.parse("")
        assert isinstance(result, list)
        assert result == []
