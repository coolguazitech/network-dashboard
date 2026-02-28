"""
SNMP Collector — Firmware Version.

All vendors: SNMP GET sysDescr.0, then regex-extract the version string.
"""
from __future__ import annotations

import logging
import re

from app.core.enums import DeviceType
from app.parsers.protocols import ParsedData, VersionData
from app.snmp.collector_base import BaseSnmpCollector
from app.snmp.engine import AsyncSnmpEngine, SnmpTarget
from app.snmp.oid_maps import SYS_DESCR
from app.snmp.session_cache import SnmpSessionCache

logger = logging.getLogger(__name__)

# ── Version extraction patterns ────────────────────────────────────
# HPE Comware: "Version 7.1.070, Release 6728P06"
_HPE_VERSION_RE = re.compile(
    r"Version\s+(\S+),\s*Release\s+(\S+)",
)
# HPE fallback: "Software Version 5.20.99"
_HPE_SOFTWARE_VERSION_RE = re.compile(
    r"Software\s+Version\s+(\S+)",
)
# Cisco IOS / NXOS: "Version 15.2(7)E2" or "Version 9.3(8)"
_CISCO_VERSION_RE = re.compile(
    r"Version\s+(\S+)",
)


def _parse_version(sys_descr: str, device_type: DeviceType) -> str:
    """Extract version string from sysDescr based on device type."""
    if device_type == DeviceType.HPE:
        # Try full "Version X, Release Y" first
        m = _HPE_VERSION_RE.search(sys_descr)
        if m:
            return f"{m.group(1)} {m.group(2)}"
        # Fallback: "Software Version X"
        m = _HPE_SOFTWARE_VERSION_RE.search(sys_descr)
        if m:
            return m.group(1)
    elif device_type in (DeviceType.CISCO_IOS, DeviceType.CISCO_NXOS):
        m = _CISCO_VERSION_RE.search(sys_descr)
        if m:
            return m.group(1)

    # Ultimate fallback: use the entire sysDescr
    return sys_descr.strip()


class VersionCollector(BaseSnmpCollector):
    """Collect firmware version via SNMPv2-MIB::sysDescr.0."""

    api_name = "get_version"

    async def collect(
        self,
        target: SnmpTarget,
        device_type: DeviceType,
        session_cache: SnmpSessionCache,
        engine: AsyncSnmpEngine,
    ) -> tuple[str, list[ParsedData]]:
        # SNMP GET sysDescr.0 (scalar)
        result = await engine.get(target, SYS_DESCR)

        sys_descr = result.get(SYS_DESCR, "")
        version = _parse_version(sys_descr, device_type)

        varbinds = [(SYS_DESCR, sys_descr)]
        raw_text = self.format_raw(
            self.api_name, target.ip, device_type, varbinds,
        )

        results: list[ParsedData] = [VersionData(version=version)]
        return raw_text, results
