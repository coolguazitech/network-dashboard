#!/usr/bin/env python3
"""
Mock API Server for Network Dashboard Testing.

Simulates the external network management API with realistic device states
and failure scenarios.

Usage:
    uvicorn tests.mock_api_server:app --port 8001
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Network Device Mock API",
    description="Mock API for testing Network Dashboard",
    version="1.0.0",
)

# Global device states storage
# Structure: {hostname: {state_data}}
device_states: dict[str, dict[str, Any]] = {}

# IP to hostname mapping
ip_to_hostname: dict[str, str] = {}


class DeviceStateUpdate(BaseModel):
    """Request model for updating device state."""

    power: str | None = None
    transceiver_output: str | None = None
    neighbor_output: str | None = None
    version_output: str | None = None
    port_channel_output: str | None = None
    fan_output: str | None = None
    power_output: str | None = None
    error_output: str | None = None
    ping_reachable: bool | None = None


class FailureScenario(BaseModel):
    """Request model for injecting failure scenarios."""

    scenario: str
    target_devices: list[str] | None = None


@app.on_event("startup")
async def load_initial_states():
    """Load initial device states from baseline scenario."""
    global device_states, ip_to_hostname

    scenario_path = Path("tests/scenarios/01_baseline.yaml")
    if scenario_path.exists():
        with open(scenario_path, encoding="utf-8") as f:
            states = yaml.safe_load(f)
            if states:
                device_states.update(states)
                # Build IP to hostname mapping
                for hostname, state in states.items():
                    if "ip_address" in state:
                        ip_to_hostname[state["ip_address"]] = hostname
                logger.info(f"Loaded {len(device_states)} device states from baseline")
    else:
        logger.warning(f"Baseline scenario not found at {scenario_path}")
        # Load default minimal states
        device_states.update({
            "switch-new-01": {
                "ip_address": "10.0.1.1",
                "vendor": "Cisco",
                "platform": "NXOS",
                "power": "on",
            }
        })
        ip_to_hostname["10.0.1.1"] = "switch-new-01"


def _find_device_by_ip(ip: str) -> dict[str, Any] | None:
    """Find device state by IP address."""
    hostname = ip_to_hostname.get(ip)
    if hostname:
        return device_states.get(hostname)
    return None


def _device_is_reachable(device: dict[str, Any]) -> bool:
    """Check if device is reachable (power on and ping_reachable)."""
    return device.get("power", "on") == "on" and device.get("ping_reachable", True)


# ==================== Device Data Endpoints ====================


@app.get("/{site}/get_transceiver/{switch_ip}", response_class=PlainTextResponse)
async def get_transceiver(site: str, switch_ip: str) -> str:
    """Return transceiver (optical module) data."""
    device = _find_device_by_ip(switch_ip)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {switch_ip} not found",
        )

    if not _device_is_reachable(device):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Device {switch_ip} unreachable",
        )

    output = device.get("transceiver_output", "")
    if not output:
        # Generate default output
        output = "No transceivers present"

    return output


@app.get("/{site}/get_neighbor/{switch_ip}", response_class=PlainTextResponse)
async def get_neighbor(site: str, switch_ip: str) -> str:
    """Return LLDP/CDP neighbor data."""
    device = _find_device_by_ip(switch_ip)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {switch_ip} not found",
        )

    if not _device_is_reachable(device):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Device {switch_ip} unreachable",
        )

    return device.get("neighbor_output", "")


@app.get("/{site}/get_uplink/{switch_ip}", response_class=PlainTextResponse)
async def get_uplink(site: str, switch_ip: str) -> str:
    """Return uplink/neighbor data (alias for get_neighbor)."""
    device = _find_device_by_ip(switch_ip)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {switch_ip} not found",
        )

    if not _device_is_reachable(device):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Device {switch_ip} unreachable",
        )

    return device.get("neighbor_output", "")


@app.get("/{site}/get_version/{switch_ip}", response_class=PlainTextResponse)
async def get_version(site: str, switch_ip: str) -> str:
    """Return device version information."""
    device = _find_device_by_ip(switch_ip)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {switch_ip} not found",
        )

    if not _device_is_reachable(device):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Device {switch_ip} unreachable",
        )

    return device.get("version_output", "Version unknown")


@app.get("/{site}/get_port_channel/{switch_ip}", response_class=PlainTextResponse)
async def get_port_channel(site: str, switch_ip: str) -> str:
    """Return port-channel status."""
    device = _find_device_by_ip(switch_ip)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {switch_ip} not found",
        )

    if not _device_is_reachable(device):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Device {switch_ip} unreachable",
        )

    return device.get("port_channel_output", "")


@app.get("/{site}/get_fan/{switch_ip}", response_class=PlainTextResponse)
async def get_fan(site: str, switch_ip: str) -> str:
    """Return fan status."""
    device = _find_device_by_ip(switch_ip)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {switch_ip} not found",
        )

    if not _device_is_reachable(device):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Device {switch_ip} unreachable",
        )

    return device.get("fan_output", "Fan 1: ok, Fan 2: ok")


@app.get("/{site}/get_power/{switch_ip}", response_class=PlainTextResponse)
async def get_power(site: str, switch_ip: str) -> str:
    """Return power supply status."""
    device = _find_device_by_ip(switch_ip)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {switch_ip} not found",
        )

    if not _device_is_reachable(device):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Device {switch_ip} unreachable",
        )

    return device.get("power_output", "PS1: ok, PS2: ok")


@app.get("/{site}/get_error_count/{switch_ip}", response_class=PlainTextResponse)
async def get_error_count(site: str, switch_ip: str) -> str:
    """Return interface error counters."""
    device = _find_device_by_ip(switch_ip)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {switch_ip} not found",
        )

    if not _device_is_reachable(device):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Device {switch_ip} unreachable",
        )

    return device.get("error_output", "")


@app.get("/{site}/get_ping/{switch_ip}", response_class=PlainTextResponse)
async def get_ping(site: str, switch_ip: str) -> str:
    """Return ping/reachability status."""
    device = _find_device_by_ip(switch_ip)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {switch_ip} not found",
        )

    # For ping, we return success/fail based on power state
    is_reachable = _device_is_reachable(device)

    if is_reachable:
        return "Reply from 10.0.0.1: bytes=32 time<1ms TTL=64\n5 packets transmitted, 5 received, 0% packet loss"
    else:
        return "Request timeout\n5 packets transmitted, 0 received, 100% packet loss"


# ==================== Admin Endpoints ====================


@app.get("/admin/devices")
async def list_devices():
    """List all configured devices."""
    return {
        "total": len(device_states),
        "devices": list(device_states.keys()),
        "ip_mappings": ip_to_hostname,
    }


@app.get("/admin/device/{hostname}")
async def get_device_state(hostname: str):
    """Get current state of a specific device."""
    if hostname not in device_states:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {hostname} not found",
        )
    return device_states[hostname]


@app.post("/admin/device/{hostname}")
async def set_device_state(hostname: str, state: DeviceStateUpdate):
    """Update device state (for testing)."""
    if hostname not in device_states:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device {hostname} not found",
        )

    # Update only non-None fields
    updates = state.model_dump(exclude_none=True)
    device_states[hostname].update(updates)

    logger.info(f"Updated {hostname} state: {updates}")

    return {
        "status": "updated",
        "hostname": hostname,
        "updates": updates,
    }


@app.post("/admin/inject_failure")
async def inject_failure(scenario: FailureScenario):
    """
    Inject predefined failure scenarios.

    Supported scenarios:
    - power_failure: Simulate power loss
    - link_down: Remove neighbor connections
    - transceiver_degraded: Lower optical power levels
    - fan_failure: Set fan status to failed
    - version_mismatch: Change version to incorrect value
    """
    target_devices = scenario.target_devices or list(device_states.keys())
    affected = []

    for hostname in target_devices:
        if hostname not in device_states:
            continue

        device = device_states[hostname]

        if scenario.scenario == "power_failure":
            device["power"] = "off"
            device["ping_reachable"] = False
            affected.append(hostname)

        elif scenario.scenario == "link_down":
            device["neighbor_output"] = ""
            affected.append(hostname)

        elif scenario.scenario == "transceiver_degraded":
            # Modify transceiver output to show low power
            original = device.get("transceiver_output", "")
            if original:
                # Replace power values with degraded ones
                degraded = original.replace("Tx Power               -", "Tx Power               -15")
                degraded = degraded.replace("Rx Power               -", "Rx Power               -20")
                device["transceiver_output"] = degraded
                affected.append(hostname)

        elif scenario.scenario == "fan_failure":
            device["fan_output"] = "Fan 1: failed, Fan 2: ok"
            affected.append(hostname)

        elif scenario.scenario == "version_mismatch":
            device["version_output"] = "NXOS: version 9.2(1)"  # Wrong version
            affected.append(hostname)

    logger.info(f"Injected '{scenario.scenario}' to {len(affected)} devices")

    return {
        "status": "injected",
        "scenario": scenario.scenario,
        "affected_devices": affected,
    }


@app.post("/admin/load_scenario/{scenario_name}")
async def load_scenario(scenario_name: str):
    """Load a predefined scenario from YAML file."""
    global device_states, ip_to_hostname

    scenario_path = Path(f"tests/scenarios/{scenario_name}.yaml")
    if not scenario_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scenario {scenario_name} not found",
        )

    with open(scenario_path, encoding="utf-8") as f:
        new_states = yaml.safe_load(f)

    if not new_states:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid scenario file",
        )

    # Replace device states
    device_states.clear()
    ip_to_hostname.clear()
    device_states.update(new_states)

    # Rebuild IP mapping
    for hostname, state in new_states.items():
        if "ip_address" in state:
            ip_to_hostname[state["ip_address"]] = hostname

    logger.info(f"Loaded scenario '{scenario_name}' with {len(device_states)} devices")

    return {
        "status": "loaded",
        "scenario": scenario_name,
        "device_count": len(device_states),
    }


@app.post("/admin/reset")
async def reset_to_baseline():
    """Reset all devices to baseline scenario."""
    return await load_scenario("01_baseline")


@app.get("/")
async def root():
    """API information."""
    return {
        "name": "Network Device Mock API",
        "version": "1.0.0",
        "devices": len(device_states),
        "endpoints": {
            "data": "/{site}/get_{indicator_type}/{switch_ip}",
            "admin_devices": "/admin/devices",
            "admin_inject": "/admin/inject_failure",
            "admin_load": "/admin/load_scenario/{scenario_name}",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
