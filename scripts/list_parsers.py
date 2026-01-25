#!/usr/bin/env python3
"""List all registered parsers."""
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.parsers.registry import parser_registry
from app.core.enums import VendorType, PlatformType

# Import plugins to trigger registration
import app.parsers.plugins  # noqa: F401

print("=" * 60)
print("Registered Parsers")
print("=" * 60)

all_parsers = parser_registry.list_parsers()
print(f"\nTotal: {len(all_parsers)} parsers")

# Group by indicator type
by_indicator = {}
for key in all_parsers:
    if key.indicator_type not in by_indicator:
        by_indicator[key.indicator_type] = []
    by_indicator[key.indicator_type].append(key)

for indicator_type in sorted(by_indicator.keys()):
    print(f"\n{indicator_type}:")
    for key in sorted(by_indicator[indicator_type], key=lambda k: f"{k.vendor}/{k.platform}"):
        print(f"  - {key.vendor.value}/{key.platform.value}")

# Check for specific parsers we need
print("\n" + "=" * 60)
print("Checking for required parsers...")
print("=" * 60)

required = [
    (VendorType.CISCO, PlatformType.CISCO_NXOS, "transceiver"),
    (VendorType.HPE, PlatformType.HPE_COMWARE, "transceiver"),
    (VendorType.CISCO, PlatformType.CISCO_NXOS, "uplink"),
    (VendorType.HPE, PlatformType.HPE_COMWARE, "uplink"),
]

for vendor, platform, indicator in required:
    parser = parser_registry.get(vendor, platform, indicator)
    status = "✅" if parser else "❌"
    print(f"{status} {vendor.value}/{platform.value}/{indicator}")
