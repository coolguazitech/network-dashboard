"""
Mock SNMP Engine.

Drop-in replacement for AsyncSnmpEngine that generates mock OID data
internally without sending any UDP packets. Used when SNMP_MOCK=true.

Implements the same get() / walk() interface so all collectors work
unchanged.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.snmp.mock_data import mock_get, mock_walk

logger = logging.getLogger(__name__)


class MockSnmpEngine:
    """
    Mock SNMP engine — same interface as AsyncSnmpEngine.

    All data comes from mock_data.py generators, deterministic per IP.
    Adds a tiny async sleep to simulate network latency.
    """

    def __init__(self, latency: float = 0.005) -> None:
        self._latency = latency
        logger.info("MockSnmpEngine initialized (no real SNMP traffic)")

    async def get(
        self, target: Any, *oids: str,
    ) -> dict[str, Any]:
        """Mock SNMP GET — returns deterministic values per IP + OID."""
        await asyncio.sleep(self._latency)
        result: dict[str, Any] = {}
        for oid in oids:
            result.update(mock_get(target.ip, oid))
        return result

    async def walk(
        self,
        target: Any,
        oid_prefix: str,
        max_repetitions: int | None = None,
    ) -> list[tuple[str, str]]:
        """Mock SNMP WALK — returns deterministic varbind list per IP + OID prefix."""
        await asyncio.sleep(self._latency)
        return mock_walk(target.ip, oid_prefix, community=target.community)
