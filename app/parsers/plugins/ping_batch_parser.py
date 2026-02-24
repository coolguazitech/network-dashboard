"""Parser for 'ping_batch' API."""
from __future__ import annotations

import json
from typing import Any, cast

from app.parsers.protocols import BaseParser, PingResultData
from app.parsers.registry import parser_registry


class PingBatchParser(BaseParser[PingResultData]):
    """
    Parser for ping_batch API response.

    Expected JSON format (from real Ping API)::

        {
            "result": {
                "10.1.1.1": {
                    "min_rtt": 0.5, "avg_rtt": 1.2, "max_rtt": 1.8,
                    "rtts": [0.5, 1.2, 1.8],
                    "packets_sent": 3, "packets_received": 3,
                    "packet_loss": 0, "jitter": 0.3, "is_alive": true
                },
                ...
            }
        }

    Parser only extracts ``is_alive`` per IP to determine reachability.
    """

    device_type = None
    command = "ping_batch"

    def parse(self, raw_output: str) -> list[PingResultData]:
        stripped = raw_output.strip()
        if not stripped:
            return []

        try:
            data: Any = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            return []

        if not isinstance(data, dict):
            return []

        typed_data = cast(dict[str, Any], data)
        result_dict = typed_data.get("result")
        if not isinstance(result_dict, dict):
            return []

        parsed: list[PingResultData] = []
        for ip, stats in cast(dict[str, Any], result_dict).items():
            if not isinstance(stats, dict):
                continue

            is_alive = bool(stats.get("is_alive", False))

            parsed.append(
                PingResultData(
                    target=str(ip),
                    is_reachable=is_alive,
                )
            )

        return parsed


# Register parser
parser_registry.register(PingBatchParser())
