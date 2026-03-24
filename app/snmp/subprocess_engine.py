"""
SNMP Engine — net-snmp subprocess wrapper.

Drop-in replacement for AsyncSnmpEngine that uses `snmpget` / `snmpbulkwalk`
CLI tools via asyncio.create_subprocess_exec().

Why subprocess instead of pysnmp:
- Complete process isolation: each SNMP operation runs in its own PID/socket
- Clean timeout: proc.kill() instantly reclaims all resources (no callback races)
- Proven at scale: net-snmp is the core of LibreNMS / Nagios / Zabbix
- OS handles 200+ concurrent subprocesses without issue
- Identical get()/walk() interface: zero collector changes needed
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from app.snmp.engine import SnmpEngineConfig, SnmpError, SnmpTarget, SnmpTimeoutError

logger = logging.getLogger(__name__)

# Sentinel values that indicate "no data" — skip these lines
_SKIP_SENTINELS = frozenset({
    "No Such Object available on this agent at this OID",
    "No Such Instance currently exists at this OID",
    "No more variables left in this MIB View",
})

# Type prefix pattern: "INTEGER: ", "STRING: ", "OID: ", "Gauge32: ", etc.
_TYPE_PREFIX_RE = re.compile(r"^[A-Za-z][A-Za-z0-9 -]*:\s*")


def _parse_snmp_line(line: str) -> tuple[str, str] | None:
    """
    Parse a single line of net-snmp `-On` output.

    Format: `.1.3.6.1.2.1.1.2.0 = OID: .1.3.6.1.4.1.25506.11.2.2`

    Returns:
        (oid_str, value_str) or None if line should be skipped.
    """
    line = line.strip()
    if not line or line.startswith("No "):
        return None

    parts = line.split(" = ", 1)
    if len(parts) != 2:
        return None

    oid_raw, val_raw = parts

    # Strip leading dot from OID
    oid_str = oid_raw.lstrip(".")

    # Check for sentinel values
    val_stripped = val_raw.strip()
    if val_stripped in _SKIP_SENTINELS:
        return None
    # Also check after stripping quotes
    if val_stripped.strip('"') in _SKIP_SENTINELS:
        return None

    # Strip type prefix (e.g., "INTEGER: ", "STRING: ", "OID: ")
    val_clean = _TYPE_PREFIX_RE.sub("", val_stripped)

    # Strip surrounding quotes from STRING values
    if val_clean.startswith('"') and val_clean.endswith('"'):
        val_clean = val_clean[1:-1]

    # OID values: strip leading dot
    if val_clean.startswith("."):
        val_clean = val_clean.lstrip(".")

    return oid_str, val_clean


def _is_timeout_error(returncode: int, stderr: str) -> bool:
    """Check if subprocess exit indicates an SNMP timeout."""
    # net-snmp exit code 2 = timeout
    if returncode == 2:
        return True
    # Some versions use exit code 1 with "Timeout" in stderr
    if returncode != 0 and "timeout" in stderr.lower():
        return True
    return False


class SubprocessSnmpEngine:
    """
    SNMP engine using net-snmp CLI tools (snmpget / snmpbulkwalk).

    Drop-in replacement for AsyncSnmpEngine — same get()/walk() interface.
    Each operation spawns an isolated subprocess with its own PID and socket.
    On timeout, proc.kill() instantly and cleanly reclaims all resources.
    """

    def __init__(self, config: SnmpEngineConfig | None = None) -> None:
        self._config = config or SnmpEngineConfig()

    async def get(
        self, target: SnmpTarget, *oids: str,
    ) -> dict[str, Any]:
        """
        SNMP GET for one or more scalar OIDs.

        Returns:
            {oid_str: value} dict.

        Raises:
            SnmpTimeoutError: if request times out.
            SnmpError: on other SNMP errors.
        """
        if not oids:
            return {}

        # Build command: snmpget -v2c -c <community> -t <timeout> -r <retries> -On <ip>:<port> <oids...>
        cmd = [
            "snmpget",
            "-v2c",
            "-c", target.community,
            "-t", str(target.timeout),
            "-r", str(target.retries),
            "-On",  # numeric OID output (consistent with _parse_snmp_line)
            f"{target.ip}:{target.port}",
        ]
        # Use dotted OID format
        cmd.extend(f".{oid}" if not oid.startswith(".") else oid for oid in oids)

        # Deadline: PDU timeout + 2s buffer for process overhead
        deadline = target.timeout * (target.retries + 1) + 2.0

        stdout, stderr, returncode = await self._run_subprocess(cmd, deadline)

        if returncode != 0:
            if _is_timeout_error(returncode, stderr):
                raise SnmpTimeoutError(
                    f"SNMP GET timeout: {target.ip} OIDs={oids}"
                )
            raise SnmpError(
                f"SNMP GET error (exit {returncode}): {target.ip} "
                f"stderr={stderr.strip()}"
            )

        result: dict[str, Any] = {}
        for line in stdout.splitlines():
            parsed = _parse_snmp_line(line)
            if parsed:
                result[parsed[0]] = parsed[1]

        return result

    async def walk(
        self,
        target: SnmpTarget,
        oid_prefix: str,
        max_repetitions: int | None = None,
    ) -> list[tuple[str, str]]:
        """
        Full SNMP walk of a subtree using GETBULK.

        Returns:
            List of (oid_str, value_str) tuples within the subtree.

        Raises:
            SnmpTimeoutError: if walk times out or exceeds deadline.
            SnmpError: on other errors.
        """
        max_rep = max_repetitions or self._config.max_repetitions
        prefix = oid_prefix.rstrip(".")
        dotted_prefix = f".{prefix}" if not prefix.startswith(".") else prefix

        # Build command: snmpbulkwalk -v2c -c <community> -t <timeout> -r <retries> -Cr<max_rep> -On <ip>:<port> <prefix>
        cmd = [
            "snmpbulkwalk",
            "-v2c",
            "-c", target.community,
            "-t", str(target.timeout),
            "-r", str(target.retries),
            f"-Cr{max_rep}",
            "-On",  # numeric OID output
            f"{target.ip}:{target.port}",
            dotted_prefix,
        ]

        # Walk deadline from config
        deadline = self._config.walk_timeout

        stdout, stderr, returncode = await self._run_subprocess(cmd, deadline)

        if returncode != 0:
            if _is_timeout_error(returncode, stderr):
                raise SnmpTimeoutError(
                    f"SNMP WALK timeout: {target.ip} prefix={prefix}"
                )
            # Exit code 1 can also mean "end of MIB" (normal for walk)
            # If we got some output, treat it as success
            if returncode == 1 and stdout.strip():
                pass  # fall through to parse output
            else:
                raise SnmpError(
                    f"SNMP WALK error (exit {returncode}): {target.ip} "
                    f"stderr={stderr.strip()}"
                )

        results: list[tuple[str, str]] = []
        for line in stdout.splitlines():
            parsed = _parse_snmp_line(line)
            if parsed is None:
                continue
            oid_str, val_str = parsed
            # Verify OID is within the requested subtree
            if not oid_str.startswith(prefix + ".") and oid_str != prefix:
                break
            results.append((oid_str, val_str))

        return results

    async def _run_subprocess(
        self,
        cmd: list[str],
        deadline: float,
    ) -> tuple[str, str, int]:
        """
        Run an SNMP subprocess with timeout.

        Returns:
            (stdout, stderr, returncode)

        Raises:
            SnmpTimeoutError: if process exceeds deadline.
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as e:
            raise SnmpError(
                f"SNMP CLI tool not found: {cmd[0]}. "
                f"Install net-snmp: apt-get install snmp"
            ) from e

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=deadline,
            )
        except asyncio.TimeoutError:
            # Clean kill: immediately reclaim all resources
            proc.kill()
            await proc.wait()
            raise SnmpTimeoutError(
                f"SNMP subprocess exceeded deadline ({deadline:.0f}s): "
                f"{' '.join(cmd[:5])}..."
            )

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        returncode = proc.returncode or 0

        return stdout, stderr, returncode
