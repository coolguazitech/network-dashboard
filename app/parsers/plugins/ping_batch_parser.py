"""Parser for 'ping_batch' API."""
from __future__ import annotations

import json
import re

from app.parsers.protocols import BaseParser, PingResultData
from app.parsers.registry import parser_registry


class PingBatchParser(BaseParser[PingResultData]):
    """
    Parser for ping_batch API response.

    Supports two input formats:

    **Format A -- Standard ping output (from MockPingFetcher)**::

        PING 10.1.1.1 (10.1.1.1): 56 data bytes
        64 bytes from 10.1.1.1: icmp_seq=0 ttl=64 time=1.2 ms
        ...
        --- 10.1.1.1 ping statistics ---
        3 packets transmitted, 3 packets received, 0.0% packet loss
        round-trip min/avg/max = 1.1/1.2/1.3 ms

    - IP extracted from ``PING X.X.X.X`` line.
    - Reachability from ``X% packet loss`` -- is_reachable when loss < 100%.
    - Returns a single-element list.

    **Format B -- JSON batch format (from GNMS Ping API)**::

        {"results": [{"ip": "10.1.1.1", "reachable": true, ...}, ...]}

    - Parsed as JSON; each entry in ``results`` yields one PingResultData.

    The parser attempts JSON first. If the input is not valid JSON (or lacks
    a ``results`` key), it falls back to standard ping text parsing.
    """

    device_type = None
    command = "ping_batch"

    # "PING 10.1.1.1 ..." -- extract the target IP.
    _PING_IP_PATTERN = re.compile(
        r"^PING\s+(?P<ip>\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\b",
        re.MULTILINE,
    )

    # "X% packet loss" -- extract the loss percentage.
    _PACKET_LOSS_PATTERN = re.compile(
        r"(?P<loss>\d+(?:\.\d+)?)%\s+packet\s+loss",
        re.IGNORECASE,
    )

    def parse(self, raw_output: str) -> list[PingResultData]:
        results = self._try_parse_json(raw_output)
        if results is not None:
            return results

        return self._parse_standard_ping(raw_output)

    # ── Format B: JSON ──────────────────────────────────────────

    def _try_parse_json(self, raw_output: str) -> list[PingResultData] | None:
        """Attempt to parse the output as JSON batch format.

        Returns a list of PingResultData on success, or None if the input
        is not valid JSON or does not contain a ``results`` array.
        """
        stripped = raw_output.strip()
        if not stripped:
            return None

        try:
            data = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            return None

        # Must be a dict with a "results" list
        if not isinstance(data, dict):
            return None

        results_list = data.get("results")
        if not isinstance(results_list, list):
            return None

        parsed: list[PingResultData] = []
        for entry in results_list:
            if not isinstance(entry, dict):
                continue

            ip = entry.get("ip")
            reachable = entry.get("reachable")

            # Both fields are required
            if ip is None or reachable is None:
                continue

            # Coerce reachable to bool
            if isinstance(reachable, str):
                reachable = reachable.lower() in ("true", "1", "yes")
            else:
                reachable = bool(reachable)

            parsed.append(
                PingResultData(
                    target=str(ip),
                    is_reachable=reachable,
                    success_rate=100.0 if reachable else 0.0,
                )
            )

        return parsed

    # ── Format A: Standard ping text ────────────────────────────

    def _parse_standard_ping(self, raw_output: str) -> list[PingResultData]:
        """Parse standard ping command output (single IP)."""
        ip_match = self._PING_IP_PATTERN.search(raw_output)
        if not ip_match:
            return []

        target = ip_match.group("ip")

        loss_match = self._PACKET_LOSS_PATTERN.search(raw_output)
        if not loss_match:
            # No packet-loss line found; cannot determine reachability.
            return []

        packet_loss = float(loss_match.group("loss"))
        is_reachable = packet_loss < 100.0
        success_rate = 100.0 - packet_loss

        return [
            PingResultData(
                target=target,
                is_reachable=is_reachable,
                success_rate=success_rate,
            )
        ]


# Register parser
parser_registry.register(PingBatchParser())
