#!/usr/bin/env python3
"""
Mock API server for testing fetch_raw.py progress bar and timeout behavior.

Simulates FNA and DNA API endpoints with configurable response delays.
Each endpoint returns realistic-looking JSON responses.

Usage:
    python scripts/mock_api_server.py              # default port 9999
    python scripts/mock_api_server.py --port 8888  # custom port
"""
from __future__ import annotations

import argparse
import json
import random
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

# ── Mock response templates ──

MOCK_RESPONSES = {
    "get_gbic_details": {
        "status": "success",
        "data": [
            {"port": "1/1", "type": "SFP-10G-SR", "tx_power": -2.3, "rx_power": -3.1, "status": "OK"},
            {"port": "1/2", "type": "SFP-10G-LR", "tx_power": -1.8, "rx_power": -5.2, "status": "OK"},
            {"port": "1/3", "type": "SFP-1G-SX", "tx_power": -3.5, "rx_power": -4.0, "status": "OK"},
        ],
    },
    "get_channel_group": {
        "status": "success",
        "data": [
            {"group": "Po1", "protocol": "LACP", "members": ["Eth1/1", "Eth1/2"], "status": "up"},
            {"group": "Po2", "protocol": "LACP", "members": ["Eth1/3", "Eth1/4"], "status": "up"},
        ],
    },
    "get_uplink": {
        "status": "success",
        "data": [
            {"local_port": "Eth1/49", "neighbor": "core-sw-01", "neighbor_port": "Eth1/1", "protocol": "LLDP"},
            {"local_port": "Eth1/50", "neighbor": "core-sw-02", "neighbor_port": "Eth1/1", "protocol": "CDP"},
        ],
    },
    "get_error_count": {
        "status": "success",
        "data": [
            {"interface": "Eth1/1", "in_errors": 0, "out_errors": 0, "crc": 0, "collisions": 0},
            {"interface": "Eth1/2", "in_errors": 2, "out_errors": 0, "crc": 1, "collisions": 0},
        ],
    },
    "get_static_acl": {
        "status": "success",
        "data": [{"interface": "Vlan10", "acl_name": "STATIC_ACL_IN", "direction": "in"}],
    },
    "get_dynamic_acl": {
        "status": "success",
        "data": [{"interface": "Vlan20", "acl_name": "DYN_ACL_01", "direction": "in"}],
    },
"get_mac_table": {
        "status": "success",
        "data": [
            {"vlan": 10, "mac": "aa:bb:cc:dd:ee:01", "type": "dynamic", "port": "Eth1/1"},
            {"vlan": 20, "mac": "aa:bb:cc:dd:ee:03", "type": "dynamic", "port": "Eth1/2"},
        ],
    },
    "get_fan": {
        "status": "success",
        "data": [
            {"id": "Fan1", "status": "OK", "speed_rpm": 5200},
            {"id": "Fan2", "status": "OK", "speed_rpm": 5100},
        ],
    },
    "get_power": {
        "status": "success",
        "data": [
            {"id": "PSU1", "status": "OK", "watts": 350, "model": "PWR-650W-AC"},
            {"id": "PSU2", "status": "OK", "watts": 340, "model": "PWR-650W-AC"},
        ],
    },
    "get_version": {
        "status": "success",
        "data": {"hostname": "switch-01", "version": "16.12.4", "uptime": "45 days"},
    },
}


class MockAPIHandler(BaseHTTPRequestHandler):
    """Handle GET requests with simulated delays."""

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        # Match any known API name in the path
        response_data = None
        for api_name, data in MOCK_RESPONSES.items():
            if api_name in path:
                response_data = data
                break

        if response_data is None:
            response_data = {"status": "success", "data": [], "mock": True}

        # Random delay: 0.3s ~ 2.5s to simulate real network latency
        delay = random.uniform(0.3, 2.5)
        time.sleep(delay)

        body = json.dumps(response_data, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        """Suppress default logging — print minimal info."""
        pass


def main():
    parser = argparse.ArgumentParser(description="Mock API server for fetch testing")
    parser.add_argument("--port", type=int, default=9999, help="Port to listen on (default: 9999)")
    args = parser.parse_args()

    server = HTTPServer(("127.0.0.1", args.port), MockAPIHandler)
    print(f"Mock API server running on http://127.0.0.1:{args.port}")
    print(f"Response delay: 0.3s ~ 2.5s (random)")
    print(f"Press Ctrl+C to stop\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")
        server.server_close()


if __name__ == "__main__":
    main()
