"""
SNMP Collector — Port-Channel / LAG (IEEE8023-LAG-MIB + IF-MIB).

Walks dot3adAggPortAttachedAggID and dot3adAggPortActorOperState to
discover LAG membership and member synchronization status.

For each aggregate interface (Port-Channel):
- Collects all member interfaces attached to it
- Checks IF-MIB::ifOperStatus for the aggregate interface link status
- For each member: checks bit 2 (Synchronization) of
  dot3adAggPortActorOperState — set means "up", unset means "down"

Maps ifIndex to ifName for both aggregate and member interfaces via
session_cache.

Output: PortChannelData(interface_name, status, members, member_status)
"""
from __future__ import annotations

import logging
from collections import defaultdict

from app.core.enums import DeviceType
from app.parsers.protocols import ParsedData, PortChannelData
from app.snmp.collector_base import BaseSnmpCollector
from app.snmp.engine import AsyncSnmpEngine, SnmpTarget
from app.snmp.oid_maps import (
    DOT3AD_AGG_PORT_ACTOR_OPER_STATE,
    DOT3AD_AGG_PORT_ATTACHED_AGG_ID,
    IF_OPER_STATUS,
    IF_OPER_STATUS_MAP,
)
from app.snmp.session_cache import SnmpSessionCache

logger = logging.getLogger(__name__)

# Bit 3 (0-indexed) of dot3adAggPortActorOperState = Synchronization
# Bits: 0=lacpActivity, 1=lacpTimeout, 2=aggregation, 3=synchronization
_SYNC_BIT_MASK = 0x08  # bit 3 = 0b00001000


def _parse_oper_state_byte(val_str: str) -> int:
    """
    Parse dot3adAggPortActorOperState value.

    This OID is SYNTAX OCTET STRING (SIZE(1)), so pysnmp renders it
    as hex (e.g. "0xa2") via prettyPrint(). We need to parse it back
    to an integer for bitmask operations.
    """
    # Try decimal first (some agents return integer)
    try:
        return int(val_str)
    except (ValueError, TypeError):
        pass
    # Try auto-detect base (handles "0xa2", "0o12", "0b101" prefixes)
    try:
        return int(val_str, 0)
    except (ValueError, TypeError):
        pass
    # Try raw hex without prefix (e.g., "A2", "a2")
    try:
        return int(val_str, 16)
    except (ValueError, TypeError):
        return 0


class ChannelGroupCollector(BaseSnmpCollector):
    """Collect Port-Channel (LAG) information via IEEE8023-LAG-MIB."""

    api_name = "get_channel_group"

    async def collect(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        session_cache: SnmpSessionCache,
        engine: AsyncSnmpEngine,
    ) -> tuple[str, list[ParsedData]]:
        # Walk LAG MIB OIDs
        agg_id_varbinds = await engine.walk(target, DOT3AD_AGG_PORT_ATTACHED_AGG_ID)
        oper_state_varbinds = await engine.walk(target, DOT3AD_AGG_PORT_ACTOR_OPER_STATE)

        # Build ifIndex -> ifName mapping
        ifindex_map = await session_cache.get_ifindex_map(target.ip)

        # Parse dot3adAggPortAttachedAggID: member ifIndex -> aggregate ifIndex
        # Index is the member port's ifIndex
        member_to_agg: dict[int, int] = {}
        for oid_str, val_str in agg_id_varbinds:
            idx_str = self.extract_index(oid_str, DOT3AD_AGG_PORT_ATTACHED_AGG_ID)
            member_ifindex = self.safe_int(idx_str, -1)
            agg_ifindex = self.safe_int(val_str, 0)
            if member_ifindex >= 0 and agg_ifindex > 0:
                member_to_agg[member_ifindex] = agg_ifindex

        # Parse dot3adAggPortActorOperState: member ifIndex -> oper state byte
        # NOTE: This OID is OCTET STRING(1), pysnmp renders as hex string
        member_oper_state: dict[int, int] = {}
        for oid_str, val_str in oper_state_varbinds:
            idx_str = self.extract_index(oid_str, DOT3AD_AGG_PORT_ACTOR_OPER_STATE)
            member_ifindex = self.safe_int(idx_str, -1)
            if member_ifindex >= 0:
                member_oper_state[member_ifindex] = _parse_oper_state_byte(val_str)

        # Group members by aggregate ifIndex
        agg_members: dict[int, list[int]] = defaultdict(list)
        for member_ifindex, agg_ifindex in member_to_agg.items():
            agg_members[agg_ifindex].append(member_ifindex)

        # Collect unique aggregate ifIndexes and walk their oper status
        agg_ifindexes = set(agg_members.keys())
        agg_oper_status: dict[int, str] = {}
        if agg_ifindexes:
            oper_varbinds = await engine.walk(target, IF_OPER_STATUS)
            for oid_str, val_str in oper_varbinds:
                idx_str = self.extract_index(oid_str, IF_OPER_STATUS)
                ifindex = self.safe_int(idx_str, -1)
                if ifindex in agg_ifindexes:
                    oper_val = self.safe_int(val_str)
                    agg_oper_status[ifindex] = IF_OPER_STATUS_MAP.get(oper_val, "unknown")

        # Build results
        results: list[ParsedData] = []
        for agg_ifindex in sorted(agg_members.keys()):
            agg_ifname = ifindex_map.get(agg_ifindex)
            if not agg_ifname:
                logger.debug(
                    "ChannelGroup: no ifName for aggregate ifIndex %d on %s",
                    agg_ifindex, target.ip,
                )
                continue

            # Aggregate interface status
            status = agg_oper_status.get(agg_ifindex, "unknown")

            # Build member list and member status
            members: list[str] = []
            member_status_map: dict[str, str] = {}

            for member_ifindex in sorted(agg_members[agg_ifindex]):
                member_ifname = ifindex_map.get(member_ifindex)
                if not member_ifname:
                    logger.debug(
                        "ChannelGroup: no ifName for member ifIndex %d on %s",
                        member_ifindex, target.ip,
                    )
                    continue

                members.append(member_ifname)

                # Check bit 2 (Synchronization) of actor oper state
                oper_byte = member_oper_state.get(member_ifindex, 0)
                if oper_byte & _SYNC_BIT_MASK:
                    member_status_map[member_ifname] = "up"
                else:
                    member_status_map[member_ifname] = "down"

            if not members:
                continue

            results.append(
                PortChannelData(
                    interface_name=agg_ifname,
                    status=status,
                    members=members,
                    member_status=member_status_map,
                )
            )

        all_varbinds = agg_id_varbinds + oper_state_varbinds
        raw_text = self.format_raw(
            self.api_name, target.ip, device_type, all_varbinds,
        )
        return raw_text, results
