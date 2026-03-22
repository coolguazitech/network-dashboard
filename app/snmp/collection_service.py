"""
SNMP Collection Service.

Provides two interfaces:
1. collect() — legacy per-api_name interface (used by old scheduler path)
2. collect_round() — new device-centric round interface (preferred)

ACL and Ping automatically delegate to ApiCollectionService (not SNMP-capable).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.config import settings
from app.snmp.collector_base import BaseSnmpCollector
from app.snmp.engine import AsyncSnmpEngine, SnmpEngineConfig

logger = logging.getLogger(__name__)

# APIs that stay on REST regardless of COLLECTION_MODE
_API_PASSTHROUGH = frozenset({
    "get_static_acl",
    "get_dynamic_acl",
    "gnms_ping",
    "ping_batch",
})

# SNMP collectors grouped by collection round
FAST_ROUND_COLLECTORS = [
    "get_mac_table",
    "get_interface_status",
]

FULL_ROUND_COLLECTORS = [
    "get_fan",
    "get_power",
    "get_version",
    "get_gbic_details",
    "get_error_count",
    "get_channel_group",
    "get_uplink_lldp",
    "get_uplink_cdp",
]

# ACL collectors that use REST API passthrough (not SNMP)
# These need separate legacy jobs even in SNMP mode.
API_PASSTHROUGH_COLLECTORS = [
    "get_static_acl",
    "get_dynamic_acl",
]


def _build_collector_map() -> dict[str, BaseSnmpCollector]:
    """Build registry of api_name -> SNMP collector instances."""
    from app.snmp.collectors.channel_group import ChannelGroupCollector
    from app.snmp.collectors.error_count import ErrorCountCollector
    from app.snmp.collectors.fan import FanCollector
    from app.snmp.collectors.interface_status import InterfaceStatusCollector
    from app.snmp.collectors.mac_table import MacTableCollector
    from app.snmp.collectors.neighbor_cdp import NeighborCdpCollector
    from app.snmp.collectors.neighbor_lldp import NeighborLldpCollector
    from app.snmp.collectors.power import PowerCollector
    from app.snmp.collectors.transceiver import TransceiverCollector
    from app.snmp.collectors.version import VersionCollector

    collectors: list[BaseSnmpCollector] = [
        FanCollector(),
        PowerCollector(),
        VersionCollector(),
        TransceiverCollector(),
        ErrorCountCollector(),
        ChannelGroupCollector(),
        NeighborLldpCollector(),
        NeighborCdpCollector(),
        MacTableCollector(),
        InterfaceStatusCollector(),
    ]
    return {c.api_name: c for c in collectors}


class SnmpCollectionService:
    """
    SNMP collection service.

    Primary interface: collect_round() for device-centric collection.
    Legacy interface: collect() for backward compatibility.
    """

    def __init__(self) -> None:
        if settings.snmp_mock:
            from app.snmp.mock_engine import MockSnmpEngine
            self._engine: Any = MockSnmpEngine()
            logger.info("SNMP collection using MOCK engine (no real devices)")
        else:
            engine_config = SnmpEngineConfig(
                max_repetitions=settings.snmp_max_repetitions,
                walk_timeout=settings.snmp_walk_timeout,
            )
            self._engine = AsyncSnmpEngine(config=engine_config)
        self._collectors = _build_collector_map()
        self._api_fallback: Any = None  # lazy init
        # Global semaphore: bounds total concurrent SNMP device walks
        # across ALL rounds. One slot = one device being collected.
        self._global_sem = asyncio.Semaphore(settings.snmp_concurrency)
        self._coordinator = None  # lazy init
        logger.info(
            "SNMP global concurrency semaphore: max %d concurrent device walks",
            settings.snmp_concurrency,
        )

    def _get_coordinator(self) -> Any:
        """Lazy-init CollectionCoordinator."""
        if self._coordinator is None:
            from app.snmp.collection_coordinator import CollectionCoordinator
            self._coordinator = CollectionCoordinator(
                engine=self._engine,
                collectors=self._collectors,
                semaphore=self._global_sem,
            )
        return self._coordinator

    def _get_api_fallback(self) -> Any:
        """Lazy-init ApiCollectionService to avoid circular imports."""
        if self._api_fallback is None:
            from app.services.data_collection import ApiCollectionService
            self._api_fallback = ApiCollectionService()
        return self._api_fallback

    async def collect_round(
        self,
        round_name: str,
        collector_names: list[str],
        maintenance_id: str,
    ) -> dict[str, Any]:
        """
        Device-centric collection round.

        Iterates all devices once, running all specified collectors
        per device. Each device's community is probed only once.

        Returns:
            Dict with round stats (total, ok, unreachable, elapsed, etc.)
        """
        coordinator = self._get_coordinator()
        result = await coordinator.run_round(
            round_name=round_name,
            collector_names=collector_names,
            maintenance_id=maintenance_id,
        )
        return {
            "round_name": result.round_name,
            "total": result.total_devices,
            "ok": result.ok,
            "unreachable": result.unreachable,
            "partial": result.partial,
            "elapsed": result.elapsed,
            "per_collector": result.per_collector,
        }

    async def collect(
        self,
        api_name: str,
        source: str,
        maintenance_id: str,
    ) -> dict[str, Any]:
        """
        Legacy per-api_name interface.

        For non-SNMP APIs (ACL, ping), delegates to ApiCollectionService.
        For SNMP APIs, runs a single-collector round via the coordinator.
        """
        # Passthrough to API for non-SNMP indicators
        if api_name in _API_PASSTHROUGH:
            return await self._get_api_fallback().collect(
                api_name=api_name,
                source=source,
                maintenance_id=maintenance_id,
            )

        collector = self._collectors.get(api_name)
        if collector is None:
            logger.warning(
                "No SNMP collector for '%s', falling back to API", api_name,
            )
            return await self._get_api_fallback().collect(
                api_name=api_name,
                source=source,
                maintenance_id=maintenance_id,
            )

        # Delegate to coordinator for a single-collector round
        round_result = await self.collect_round(
            round_name=f"single_{api_name}",
            collector_names=[api_name],
            maintenance_id=maintenance_id,
        )

        # Convert to legacy format
        return {
            "api_name": api_name,
            "total": round_result["total"],
            "success": round_result["ok"],
            "failed": round_result["unreachable"] + round_result["partial"],
            "errors": [],
        }


# Singleton
_service: SnmpCollectionService | None = None


def get_snmp_collection_service() -> SnmpCollectionService:
    """Get or create SnmpCollectionService instance."""
    global _service
    if _service is None:
        _service = SnmpCollectionService()
    return _service


def reset_snmp_collection_service() -> None:
    """Discard singleton so next call creates a fresh engine."""
    global _service
    _service = None
    logger.info("SNMP collection service singleton reset")
