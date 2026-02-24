"""Mock: 設備連通性 (ping_batch)。

產出與真實 Ping API 相同的 JSON 格式::

    {
        "result": {
            "10.0.0.1": {
                "min_rtt": 1.1, "avg_rtt": 1.2, "max_rtt": 1.3,
                "rtts": [1.1, 1.2, 1.3],
                "packets_sent": 3, "packets_received": 3,
                "packet_loss": 0, "jitter": 0.1, "is_alive": true
            }
        }
    }
"""
from __future__ import annotations

import json


def generate(
    device_type: str,
    fails: bool = False,
    switch_ip: str = "10.0.0.1",
    **_kw: object,
) -> str:
    if fails:
        result = {
            switch_ip: {
                "min_rtt": 0,
                "avg_rtt": 0,
                "max_rtt": 0,
                "rtts": [],
                "packets_sent": 3,
                "packets_received": 0,
                "packet_loss": 100.0,
                "jitter": 0,
                "is_alive": False,
            }
        }
    else:
        result = {
            switch_ip: {
                "min_rtt": 1.1,
                "avg_rtt": 1.2,
                "max_rtt": 1.3,
                "rtts": [1.1, 1.2, 1.3],
                "packets_sent": 3,
                "packets_received": 3,
                "packet_loss": 0,
                "jitter": 0.1,
                "is_alive": True,
            }
        }

    return json.dumps({"result": result})
