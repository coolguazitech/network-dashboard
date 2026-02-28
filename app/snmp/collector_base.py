"""
BaseSnmpCollector — SNMP Collector 抽象基底類別。

每個指標的 collector 繼承此類別，實作 collect() 方法。
提供 collect_with_retry() 自動重試 timeout 錯誤。
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel

from app.core.enums import DeviceType
from app.snmp.engine import AsyncSnmpEngine, SnmpTarget, SnmpTimeoutError
from app.snmp.session_cache import SnmpSessionCache

logger = logging.getLogger(__name__)


class BaseSnmpCollector(ABC):
    """
    Abstract base for all SNMP collectors.

    Each collector knows:
    - Which OIDs to walk/get for each vendor
    - How to transform SNMP varbinds into ParsedData objects
    - How to format raw SNMP data as a readable string
    """

    # Subclasses set this to match the api_name from scheduler.yaml
    api_name: str

    @abstractmethod
    async def collect(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        session_cache: SnmpSessionCache,
        engine: AsyncSnmpEngine,
    ) -> tuple[str, list[BaseModel]]:
        """
        Collect data from a single device via SNMP.

        Returns:
            (raw_text_representation, list_of_parsed_items)
        """
        ...

    async def collect_with_retry(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        session_cache: SnmpSessionCache,
        engine: AsyncSnmpEngine,
        max_retries: int = 2,
    ) -> tuple[str, list[BaseModel]]:
        """
        collect() with automatic retry on timeout.
        """
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return await self.collect(
                    target, device_type, session_cache, engine,
                )
            except (SnmpTimeoutError, asyncio.TimeoutError) as e:
                last_error = e
                if attempt < max_retries:
                    wait = 1.0 * (attempt + 1)
                    logger.warning(
                        "%s: timeout for %s, retry %d/%d (wait %.1fs)",
                        self.api_name, target.ip,
                        attempt + 1, max_retries, wait,
                    )
                    await asyncio.sleep(wait)
                    continue
                break

        raise SnmpTimeoutError(
            f"{self.api_name}: all retries exhausted for {target.ip}: "
            f"{last_error}"
        )

    @staticmethod
    def format_raw(
        api_name: str,
        ip: str,
        device_type: DeviceType,
        varbinds: list[tuple[str, Any]],
    ) -> str:
        """Format SNMP varbinds as readable text for raw_data storage."""
        lines = [
            f"SNMP Collector: {api_name}",
            f"Device: {ip} ({device_type.value})",
            f"Timestamp: {datetime.now(timezone.utc).isoformat()}",
            f"OID count: {len(varbinds)}",
            "---",
        ]
        for oid, val in varbinds:
            lines.append(f"  {oid} = {val}")
        return "\n".join(lines)

    @staticmethod
    def extract_index(oid_str: str, prefix: str) -> str:
        """Extract the index portion after the OID prefix."""
        # e.g. prefix="1.3.6.1.2.1.2.2.1.8", oid="1.3.6.1.2.1.2.2.1.8.5"
        # → returns "5"
        return oid_str[len(prefix) + 1:]  # +1 for the dot

    @staticmethod
    def safe_int(val: str, default: int = 0) -> int:
        """Parse an integer value, returning default on failure."""
        try:
            return int(val)
        except (ValueError, TypeError):
            return default
