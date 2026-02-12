#!/usr/bin/env python3
"""
Mock API Server for local testing

Usage:
    python scripts/mock_api_server.py

This will start a mock server on http://localhost:8001
that simulates DNA/FNA/GNMSPING API responses.

Covers all 21 APIs defined in config/api_test.yaml.
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse


class MockAPIHandler(BaseHTTPRequestHandler):
    """Mock API handler that simulates network device APIs."""

    def do_GET(self):
        """Handle GET requests."""
        path = urlparse(self.path).path

        # ── FNA APIs (generic, path param: /switch/get_xxx/{ip}) ──
        if "/switch/network/get_gbic_details/" in path:
            self._send_mock_response(FNA_TRANSCEIVER_RESPONSE)
        elif "/switch/network/get_channel_group/" in path:
            self._send_mock_response(FNA_PORT_CHANNEL_RESPONSE)
        elif "/switch/network/get_neighbors/" in path:
            self._send_mock_response(FNA_UPLINK_RESPONSE)
        elif "/switch/network/get_error_count/" in path:
            self._send_mock_response(FNA_ERROR_COUNT_RESPONSE)
        elif "/switch/network/get_acl/" in path:
            self._send_mock_response(FNA_ACL_RESPONSE)
        elif "/switch/network/get_arp_table/" in path:
            self._send_mock_response(FNA_ARP_TABLE_RESPONSE)
        elif "/switch/network/get_static_vlan/" in path:
            self._send_mock_response(FNA_STATIC_VLAN_RESPONSE)
        elif "/switch/network/get_dynamic_vlan/" in path:
            self._send_mock_response(FNA_DYNAMIC_VLAN_RESPONSE)

        # ── DNA APIs (device-specific, query_params: ?hosts={ip}) ──
        elif "/api/v1/hpe/mac-table" in path:
            self._send_mock_response(HPE_MAC_TABLE_RESPONSE)
        elif "/api/v1/ios/mac-table" in path:
            self._send_mock_response(IOS_MAC_TABLE_RESPONSE)
        elif "/api/v1/nxos/mac-table" in path:
            self._send_mock_response(NXOS_MAC_TABLE_RESPONSE)
        elif "/api/v1/hpe/fan" in path:
            self._send_mock_response(HPE_FAN_RESPONSE)
        elif "/api/v1/ios/fan" in path:
            self._send_mock_response(IOS_FAN_RESPONSE)
        elif "/api/v1/nxos/fan" in path:
            self._send_mock_response(NXOS_FAN_RESPONSE)
        elif "/api/v1/hpe/power" in path:
            self._send_mock_response(HPE_POWER_RESPONSE)
        elif "/api/v1/ios/power" in path:
            self._send_mock_response(IOS_POWER_RESPONSE)
        elif "/api/v1/nxos/power" in path:
            self._send_mock_response(NXOS_POWER_RESPONSE)
        elif "/api/v1/hpe/version" in path:
            self._send_mock_response(HPE_VERSION_RESPONSE)
        elif "/api/v1/ios/version" in path:
            self._send_mock_response(IOS_VERSION_RESPONSE)
        elif "/api/v1/nxos/version" in path:
            self._send_mock_response(NXOS_VERSION_RESPONSE)

        else:
            self._send_error_response(404, f"Endpoint not found: {path}")

    def do_POST(self):
        """Handle POST requests."""
        path = urlparse(self.path).path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode()

        # ── GNMSPING API (body-based auth) ──
        if "/api/v1/ping" in path:
            try:
                data = json.loads(body)
                addresses = data.get("addresses", [])
                response = {
                    "results": [
                        {"ip": addr, "reachable": True, "latency_ms": 10.5}
                        for addr in addresses
                    ]
                }
                self._send_mock_response(json.dumps(response, indent=2))
            except Exception as e:
                self._send_error_response(400, f"Invalid JSON: {str(e)}")
        else:
            self._send_error_response(404, f"Endpoint not found: {path}")

    def _send_mock_response(self, content: str):
        """Send a successful mock response."""
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(content.encode())

    def _send_error_response(self, status_code: int, message: str):
        """Send an error response."""
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"error": message}).encode())

    def log_message(self, format, *args):
        """Override to add colored output."""
        print(f"[Mock API] {self.address_string()} - {format % args}")


# =============================================================================
# Mock Response Data — FNA APIs (generic, same endpoint for all device types)
# =============================================================================

FNA_TRANSCEIVER_RESPONSE = """GigabitEthernet1/0/1 transceiver diagnostic information:
Current diagnostic parameters:
  Temp(°C)  Voltage(V)
  36        3.31

  Channel   Bias(mA)  RX power(dBm)  TX power(dBm)
  1         6.13      -3.10          -2.50

GigabitEthernet1/0/2 transceiver diagnostic information:
Current diagnostic parameters:
  Temp(°C)  Voltage(V)
  35        3.30

  Channel   Bias(mA)  RX power(dBm)  TX power(dBm)
  1         6.10      -3.00          -2.30

FortyGigE1/0/25 transceiver diagnostic information:
Current diagnostic parameters:
  Temp(°C)  Voltage(V)
  34        3.29

  Channel   Bias(mA)  RX power(dBm)  TX power(dBm)
  1         6.50      -2.10          -1.50
  2         6.48      -2.30          -1.55
  3         6.52      -2.05          -1.48
  4         6.45      -2.20          -1.52
"""

FNA_PORT_CHANNEL_RESPONSE = """Port-Channel    Status    Protocol    Members
Po1             up        LACP        GE1/0/1, GE1/0/2
Po2             up        LACP        GE1/0/3, GE1/0/4
"""

FNA_UPLINK_RESPONSE = """Local Interface    Remote Host        Remote Interface    Platform
GE1/0/25           CORE-SW-01         GE0/0/1             Cisco IOS
GE1/0/26           CORE-SW-02         GE0/0/1             Cisco IOS
"""

FNA_ERROR_COUNT_RESPONSE = """Interface            CRC Errors
GE1/0/1                        0
GE1/0/2                       15
GE1/0/3                        0
XGE1/0/25                      0
"""

FNA_ACL_RESPONSE = """Interface    ACL Number
GE1/0/1      100
GE1/0/2      101
GE1/0/3      --
XGE1/0/25    200
"""

FNA_ARP_TABLE_RESPONSE = """IP Address        MAC Address            Interface
192.168.1.1       aa:bb:cc:dd:ee:01      GE1/0/1
192.168.1.2       aa:bb:cc:dd:ee:02      GE1/0/2
192.168.1.3       aa:bb:cc:dd:ee:03      GE1/0/3
"""

FNA_STATIC_VLAN_RESPONSE = """Interface    VLAN
GE1/0/1      10
GE1/0/2      20
GE1/0/3      10
XGE1/0/25    100
"""

FNA_DYNAMIC_VLAN_RESPONSE = """Interface    VLAN
GE1/0/1      10
GE1/0/2      30
GE1/0/3      10
XGE1/0/25    100
"""

# =============================================================================
# Mock Response Data — DNA APIs (device-specific)
# =============================================================================

# ── MAC Table ──
HPE_MAC_TABLE_RESPONSE = """MAC Address          VLAN    Interface
aa:bb:cc:dd:ee:01    10      GE1/0/1
aa:bb:cc:dd:ee:02    20      GE1/0/2
aa:bb:cc:dd:ee:03    10      GE1/0/3
"""

IOS_MAC_TABLE_RESPONSE = """          Mac Address Table
-------------------------------------------
Vlan    Mac Address       Type        Ports
----    -----------       --------    -----
  10    aabb.ccdd.ee01    DYNAMIC     Gi0/1
  20    aabb.ccdd.ee02    DYNAMIC     Gi0/2
"""

NXOS_MAC_TABLE_RESPONSE = """Legend:
        * - primary entry, G - Gateway MAC, (R) - Routed MAC

   VLAN     MAC Address      Type      age     Secure   NTFY   Ports
---------+-----------------+--------+---------+------+----+------------------
*   10     aabb.ccdd.ee01   dynamic  0         F      F    Eth1/1
*   20     aabb.ccdd.ee02   dynamic  0         F      F    Eth1/2
"""

# ── Fan ──
HPE_FAN_RESPONSE = """Fan Status:
Fan 1/1        Ok            3200 RPM
Fan 1/2        Ok            3150 RPM
Fan 2/1        Ok            3180 RPM
"""

IOS_FAN_RESPONSE = """SYSTEM FAN is OK
Fan 1 is OK
Fan 2 is OK
"""

NXOS_FAN_RESPONSE = """Fan             Model                Hw         Status
--------------------------------------------------------------
Chassis-1       N9K-C93180YC-FX      --         Ok
Fan_in_PS-1     --                   --         Ok
Fan_in_PS-2     --                   --         Ok
"""

# ── Power ──
HPE_POWER_RESPONSE = """Power Supply Status:
PS 1/1         Ok       Input: OK   Output: OK   Capacity: 350W   Actual: 180W
PS 1/2         Ok       Input: OK   Output: OK   Capacity: 350W   Actual: 175W
"""

IOS_POWER_RESPONSE = """Power Supply   Status
PS1            OK
PS2            OK
"""

NXOS_POWER_RESPONSE = """Power Supply    Model               Actual Output   Status
PS-1            N9K-PAC-650W-B      220 W           Ok
PS-2            N9K-PAC-650W-B      215 W           Ok
"""

# ── Version ──
HPE_VERSION_RESPONSE = """Software Version: WC.16.11.0012
Model: Aruba 6300M
Serial Number: SG12345678
Uptime: 45 days, 3 hours
"""

IOS_VERSION_RESPONSE = """Cisco IOS Software, Version 15.2(7)E4
Model number: WS-C2960X-48FPS-L
System serial number: FCW2345G0AB
uptime is 30 days, 12 hours, 5 minutes
"""

NXOS_VERSION_RESPONSE = """Cisco Nexus Operating System (NX-OS) Software
  NXOS: version 9.3(8)
Hardware
  cisco Nexus9000 C93180YC-FX
  Processor Board ID SAL2345ABCD
Kernel uptime is 60 day(s), 5 hour(s), 30 minute(s)
"""


# =============================================================================
# Main
# =============================================================================

def main():
    """Start the mock API server."""
    host = "localhost"
    port = 8001

    server = HTTPServer((host, port), MockAPIHandler)

    print("=" * 60)
    print("Mock API Server Started")
    print("=" * 60)
    print(f"Address: http://{host}:{port}")
    print()
    print("FNA APIs (generic, 8):")
    print("  GET  /switch/network/get_gbic_details/{ip}")
    print("  GET  /switch/network/get_channel_group/{ip}")
    print("  GET  /switch/network/get_neighbors/{ip}")
    print("  GET  /switch/network/get_error_count/{ip}")
    print("  GET  /switch/network/get_acl/{ip}")
    print("  GET  /switch/network/get_arp_table/{ip}")
    print("  GET  /switch/network/get_static_vlan/{ip}")
    print("  GET  /switch/network/get_dynamic_vlan/{ip}")
    print()
    print("DNA APIs (device-specific, 12):")
    print("  GET  /api/v1/{hpe,ios,nxos}/mac-table?hosts={ip}")
    print("  GET  /api/v1/{hpe,ios,nxos}/fan?hosts={ip}")
    print("  GET  /api/v1/{hpe,ios,nxos}/power?hosts={ip}")
    print("  GET  /api/v1/{hpe,ios,nxos}/version?hosts={ip}")
    print()
    print("GNMSPING APIs (1):")
    print("  POST /api/v1/ping")
    print()
    print("Press Ctrl+C to stop")
    print("=" * 60)
    print()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n\nStopping mock server...")
        server.shutdown()


if __name__ == "__main__":
    main()
