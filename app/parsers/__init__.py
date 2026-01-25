"""
Parser package.

Provides plugin-based parsers for different network device vendors.
"""
from app.parsers.protocols import (
    BaseParser,
    FanStatusData,
    InterfaceErrorData,
    NeighborData,
    ParsedData,
    ParserKey,
    TransceiverData,
    VersionData,
)
from app.parsers.registry import (
    auto_discover_parsers,
    parser_registry,
    register_parser,
)

# Import plugins to trigger parser registration
from app.parsers import plugins  # noqa: F401

__all__ = [
    "BaseParser",
    "ParsedData",
    "TransceiverData",
    "InterfaceErrorData",
    "FanStatusData",
    "VersionData",
    "NeighborData",
    "ParserKey",
    "parser_registry",
    "register_parser",
    "auto_discover_parsers",
]
