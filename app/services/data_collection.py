"""
Data Collection Service.

Responsible for collecting raw data from external API and storing to DB.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.enums import MaintenancePhase, PlatformType, VendorType
from app.db.base import get_session_context
from app.db.models import Switch
from app.parsers import BaseParser, parser_registry
from app.repositories.collection_record import CollectionRecordRepository
from app.repositories.switch import SwitchRepository
from app.services.api_client import BaseApiClient, get_api_client

logger = logging.getLogger(__name__)


class DataCollectionService:
    """
    Service for collecting data from external API.

    Flow:
    1. Get list of active switches
    2. For each switch, call external API
    3. Parse raw output using appropriate parser
    4. Store parsed data to collection_records table
    """

    def __init__(
        self,
        api_client: BaseApiClient | None = None,
        use_mock: bool = False,
    ) -> None:
        """
        Initialize service.

        Args:
            api_client: API client instance (optional)
            use_mock: Use mock API client for testing
        """
        self.api_client = api_client or get_api_client(use_mock=use_mock)

    async def collect_indicator_data(
        self,
        indicator_type: str,
        phase: MaintenancePhase = MaintenancePhase.POST,
        maintenance_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Collect data for a specific indicator from all active switches.

        Args:
            indicator_type: Type of indicator (e.g., "transceiver")
            phase: Maintenance phase (PRE/POST)
            maintenance_id: Maintenance job ID (optional)

        Returns:
            dict: Collection summary with success/fail counts
        """
        results = {
            "indicator_type": indicator_type,
            "phase": phase.value,
            "total": 0,
            "success": 0,
            "failed": 0,
            "errors": [],
        }

        async with get_session_context() as session:
            switch_repo = SwitchRepository(session)
            record_repo = CollectionRecordRepository(session)

            # Get all active switches
            switches = await switch_repo.get_active_switches()
            results["total"] = len(switches)

            for switch in switches:
                try:
                    await self._collect_for_switch(
                        switch=switch,
                        indicator_type=indicator_type,
                        phase=phase,
                        maintenance_id=maintenance_id,
                        record_repo=record_repo,
                    )
                    results["success"] += 1

                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append({
                        "switch": switch.hostname,
                        "error": str(e),
                    })
                    logger.error(
                        f"Failed to collect {indicator_type} "
                        f"from {switch.hostname}: {e}"
                    )

        return results

    async def _collect_for_switch(
        self,
        switch: Switch,
        indicator_type: str,
        phase: MaintenancePhase,
        maintenance_id: str | None,
        record_repo: CollectionRecordRepository,
    ) -> None:
        """
        Collect data for a single switch.

        Args:
            switch: Switch model instance
            indicator_type: Type of indicator
            phase: Maintenance phase
            maintenance_id: Maintenance job ID
            record_repo: Repository for saving records
        """
        # Get appropriate parser
        parser = parser_registry.get(
            vendor=switch.vendor,
            platform=switch.platform,
            indicator_type=indicator_type,
        )

        if parser is None:
            raise ValueError(
                f"No parser found for {switch.vendor}/{switch.platform}"
                f"/{indicator_type}"
            )

        # Build API function name from indicator type
        api_function = f"get_{indicator_type}"

        # Call external API
        raw_output = await self.api_client.fetch(
            site=switch.site.value,
            function=api_function,
            switch_ip=switch.ip_address,
        )

        # Parse raw output
        parsed_items = parser.parse(raw_output)

        # Convert parsed items to dict for JSON storage
        parsed_data = {
            "items": [item.model_dump() for item in parsed_items],
            "count": len(parsed_items),
        }

        # Save to database
        await record_repo.save_collection(
            indicator_type=indicator_type,
            switch_hostname=switch.hostname,
            raw_data=raw_output,
            parsed_data=parsed_data,
            phase=phase,
            maintenance_id=maintenance_id,
        )

        logger.info(
            f"Collected {indicator_type} from {switch.hostname}: "
            f"{len(parsed_items)} items"
        )

    async def collect_for_specific_switches(
        self,
        switch_hostnames: list[str],
        indicator_type: str,
        phase: MaintenancePhase = MaintenancePhase.POST,
        maintenance_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Collect data for specific switches only.

        Args:
            switch_hostnames: List of switch hostnames
            indicator_type: Type of indicator
            phase: Maintenance phase
            maintenance_id: Maintenance job ID

        Returns:
            dict: Collection summary
        """
        results = {
            "indicator_type": indicator_type,
            "phase": phase.value,
            "total": len(switch_hostnames),
            "success": 0,
            "failed": 0,
            "errors": [],
        }

        async with get_session_context() as session:
            switch_repo = SwitchRepository(session)
            record_repo = CollectionRecordRepository(session)

            for hostname in switch_hostnames:
                switch = await switch_repo.get_by_hostname(hostname)

                if switch is None:
                    results["failed"] += 1
                    results["errors"].append({
                        "switch": hostname,
                        "error": "Switch not found",
                    })
                    continue

                try:
                    await self._collect_for_switch(
                        switch=switch,
                        indicator_type=indicator_type,
                        phase=phase,
                        maintenance_id=maintenance_id,
                        record_repo=record_repo,
                    )
                    results["success"] += 1

                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append({
                        "switch": hostname,
                        "error": str(e),
                    })

        return results


# Singleton instance
_collection_service: DataCollectionService | None = None


def get_collection_service(use_mock: bool = False) -> DataCollectionService:
    """
    Get or create DataCollectionService instance.

    Args:
        use_mock: Use mock API client

    Returns:
        DataCollectionService instance
    """
    global _collection_service
    if _collection_service is None:
        _collection_service = DataCollectionService(use_mock=use_mock)
    return _collection_service
