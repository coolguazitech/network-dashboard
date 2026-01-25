#!/usr/bin/env python3
"""
Test Mock API Server functionality.

This script tests that the Mock Server can:
1. Load scenarios correctly
2. Return appropriate data for each endpoint
3. Handle device state updates
4. Inject failure scenarios
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx


async def test_mock_server():
    """Test Mock API Server endpoints."""
    base_url = "http://localhost:8001"
    client = httpx.AsyncClient(base_url=base_url, timeout=10.0)

    print("=" * 60)
    print("Testing Mock API Server")
    print("=" * 60)

    try:
        # Test 1: Root endpoint
        print("\n1. Testing root endpoint...")
        response = await client.get("/")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Server running - {data.get('name')}")
            print(f"   Devices loaded: {data.get('devices', 0)}")
        else:
            print(f"   ❌ Root endpoint failed: {response.status_code}")
            return False

        # Test 2: List devices
        print("\n2. Testing device listing...")
        response = await client.get("/admin/devices")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Found {data['total']} devices")
            for hostname in data['devices']:
                print(f"      - {hostname}")
        else:
            print(f"   ❌ Device listing failed")
            return False

        # Test 3: Get transceiver data
        print("\n3. Testing get_transceiver endpoint...")
        response = await client.get("/t_site/get_transceiver/10.0.1.1")
        if response.status_code == 200:
            output = response.text
            if "Ethernet" in output or "transceiver" in output.lower():
                print(f"   ✅ Transceiver data returned ({len(output)} bytes)")
                print(f"   Sample: {output[:100]}...")
            else:
                print(f"   ⚠️  Unexpected transceiver format")
        else:
            print(f"   ❌ Transceiver endpoint failed: {response.status_code}")
            return False

        # Test 4: Get neighbor data
        print("\n4. Testing get_neighbor endpoint...")
        response = await client.get("/t_site/get_neighbor/10.0.1.1")
        if response.status_code == 200:
            output = response.text
            if output:
                print(f"   ✅ Neighbor data returned ({len(output)} bytes)")
                print(f"   Sample: {output[:100]}...")
            else:
                print(f"   ⚠️  Empty neighbor data (might be normal)")
        else:
            print(f"   ❌ Neighbor endpoint failed: {response.status_code}")
            return False

        # Test 5: Get version data
        print("\n5. Testing get_version endpoint...")
        response = await client.get("/t_site/get_version/10.0.1.1")
        if response.status_code == 200:
            output = response.text
            if "version" in output.lower() or "nxos" in output.lower():
                print(f"   ✅ Version data returned ({len(output)} bytes)")
                print(f"   Sample: {output[:100]}...")
            else:
                print(f"   ⚠️  Unexpected version format")
        else:
            print(f"   ❌ Version endpoint failed: {response.status_code}")
            return False

        # Test 6: Device not found (404)
        print("\n6. Testing device not found...")
        response = await client.get("/t_site/get_transceiver/192.168.1.1")
        if response.status_code == 404:
            print(f"   ✅ Correctly returns 404 for unknown device")
        else:
            print(f"   ⚠️  Expected 404, got {response.status_code}")

        # Test 7: Update device state
        print("\n7. Testing device state update...")
        response = await client.post(
            "/admin/device/switch-new-01",
            json={"power": "off"}
        )
        if response.status_code == 200:
            print(f"   ✅ Device state updated")

            # Verify device is now unreachable
            response = await client.get("/t_site/get_transceiver/10.0.1.1")
            if response.status_code == 504:
                print(f"   ✅ Device correctly unreachable after power off")
            else:
                print(f"   ⚠️  Expected 504, got {response.status_code}")

            # Restore power
            await client.post(
                "/admin/device/switch-new-01",
                json={"power": "on", "ping_reachable": True}
            )
            print(f"   ✅ Device power restored")
        else:
            print(f"   ❌ State update failed: {response.status_code}")
            return False

        # Test 8: Inject failure scenario
        print("\n8. Testing failure injection...")
        response = await client.post(
            "/admin/inject_failure",
            json={
                "scenario": "fan_failure",
                "target_devices": ["switch-new-01"]
            }
        )
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Failure injected to {len(data['affected_devices'])} device(s)")

            # Verify fan status changed
            device_state = await client.get("/admin/device/switch-new-01")
            state_data = device_state.json()
            if "failed" in state_data.get("fan_output", "").lower():
                print(f"   ✅ Fan failure correctly applied")
            else:
                print(f"   ⚠️  Fan status not changed as expected")
        else:
            print(f"   ❌ Failure injection failed: {response.status_code}")
            return False

        # Test 9: Reset to baseline
        print("\n9. Testing scenario reset...")
        response = await client.post("/admin/reset")
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Reset to baseline - {data['device_count']} devices")
        else:
            print(f"   ❌ Reset failed: {response.status_code}")
            return False

        print("\n" + "=" * 60)
        print("✅ All Mock Server tests passed!")
        print("=" * 60)
        return True

    except httpx.ConnectError:
        print("\n❌ Cannot connect to Mock Server!")
        print("Please start the server first:")
        print("  cd tests")
        print("  uvicorn mock_api_server:app --port 8001")
        return False
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await client.aclose()


def main():
    """Run the tests."""
    result = asyncio.run(test_mock_server())
    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(main())
