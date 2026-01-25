# Testing Guide

This directory contains the Mock API Server and test scenarios for the Network Dashboard project.

## Quick Start

### 1. Start the Mock API Server

```bash
# Option 1: Use the startup script
./scripts/run_mock_server.sh

# Option 2: Start manually
cd tests
uvicorn mock_api_server:app --port 8001 --reload
```

The server will start on `http://localhost:8001`

### 2. Test the Mock Server

In another terminal:

```bash
# Run Mock Server tests
python tests/test_mock_server.py
```

### 3. Seed Test Data

```bash
# Seed a specific scenario
python scripts/seed_test_data.py --scenario 01_baseline

# Seed a scenario to specific maintenance ID
python scripts/seed_test_data.py --scenario 02_transceiver_failure --maintenance-id TEST-200

# Seed all scenarios
python scripts/seed_test_data.py --all
```

## Mock API Server

The Mock API Server simulates the external network management API with realistic device states and failure scenarios.

### Features

- **Scenario Loading**: Load different device states from YAML files
- **All Endpoints**: Supports all 8 indicator endpoints (transceiver, neighbor, version, etc.)
- **Failure Injection**: Inject failures dynamically for testing
- **State Management**: Update device states on the fly
- **Realistic Responses**: Returns actual CLI output format

### API Endpoints

#### Data Endpoints
- `GET /{site}/get_transceiver/{switch_ip}` - Optical module data
- `GET /{site}/get_neighbor/{switch_ip}` - LLDP/CDP neighbor data
- `GET /{site}/get_version/{switch_ip}` - Firmware version
- `GET /{site}/get_port_channel/{switch_ip}` - Port-channel status
- `GET /{site}/get_fan/{switch_ip}` - Fan status
- `GET /{site}/get_power/{switch_ip}` - Power supply status
- `GET /{site}/get_error_count/{switch_ip}` - Interface errors
- `GET /{site}/get_ping/{switch_ip}` - Reachability test

#### Admin Endpoints
- `GET /admin/devices` - List all configured devices
- `GET /admin/device/{hostname}` - Get device state
- `POST /admin/device/{hostname}` - Update device state
- `POST /admin/inject_failure` - Inject failure scenario
- `POST /admin/load_scenario/{scenario_name}` - Load a scenario
- `POST /admin/reset` - Reset to baseline

### Example Usage

```python
import httpx

# Get transceiver data
response = await client.get("http://localhost:8001/t_site/get_transceiver/10.0.1.1")
print(response.text)

# Power off a device
await client.post(
    "http://localhost:8001/admin/device/switch-new-01",
    json={"power": "off"}
)

# Inject fan failure
await client.post(
    "http://localhost:8001/admin/inject_failure",
    json={
        "scenario": "fan_failure",
        "target_devices": ["switch-new-01"]
    }
)

# Load a scenario
await client.post("http://localhost:8001/admin/load_scenario/02_transceiver_failure")
```

## Test Scenarios

Located in `tests/scenarios/`, these YAML files define different device states.

### Available Scenarios

1. **01_baseline.yaml** - All devices healthy ✅
   - Normal transceiver power levels
   - All uplinks connected
   - All fans and PSUs operational
   - No interface errors
   - Correct firmware versions

2. **02_transceiver_failure.yaml** - Optical degradation ⚠️
   - Tx/Rx power below thresholds
   - High temperatures
   - Low voltage

3. **03_uplink_down.yaml** - Connectivity loss ❌
   - No LLDP/CDP neighbors detected
   - Port-channels down

4. **04_power_failure.yaml** - Device offline 🔌
   - Device unreachable (power off)
   - All API calls timeout

5. **05_fan_failure.yaml** - Cooling issues 🌡️
   - Multiple fans in failed state
   - Elevated temperatures

6. **06_version_mismatch.yaml** - Wrong firmware 📦
   - Devices running incorrect versions

7. **07_port_channel_degraded.yaml** - LAG degradation ⚡
   - Some port-channel members down

8. **08_error_spike.yaml** - Interface errors 📊
   - High CRC error counts
   - Input/output errors

### Scenario Format

```yaml
switch-new-01:
  ip_address: "10.0.1.1"
  vendor: "Cisco"
  platform: "NXOS"
  site: "t_site"
  power: "on"  # or "off"
  ping_reachable: true

  transceiver_output: |
    Ethernet1/1
        transceiver is present
        Tx Power               -2.1 dBm
        Rx Power               -3.2 dBm

  neighbor_output: |
    System Name: spine-01.example.com
    Port id: Ethernet1/1

  version_output: |
    NXOS: version 9.3(10)

  # ... other outputs ...
```

## Workflow

### Testing a New Feature

1. **Start Mock Server**
   ```bash
   ./scripts/run_mock_server.sh
   ```

2. **Start Dashboard Backend**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```

3. **Configure to Use Mock Server**
   ```bash
   export EXTERNAL_API_SERVER="http://localhost:8001"
   ```

4. **Seed Test Data**
   ```bash
   python scripts/seed_test_data.py --scenario 01_baseline
   ```

5. **Access Dashboard**
   - Open browser: `http://localhost:5173`
   - View TEST-100 maintenance

### Testing Failure Scenarios

```bash
# Seed baseline first
python scripts/seed_test_data.py --scenario 01_baseline --maintenance-id TEST-BASELINE

# Seed failure scenario
python scripts/seed_test_data.py --scenario 02_transceiver_failure --maintenance-id TEST-FAILURE

# Compare in dashboard
```

### Creating New Scenarios

1. Copy an existing scenario YAML
2. Modify device states as needed
3. Load it into Mock Server:
   ```bash
   curl -X POST http://localhost:8001/admin/load_scenario/my_scenario
   ```

4. Seed the data:
   ```bash
   python scripts/seed_test_data.py --scenario my_scenario
   ```

## Troubleshooting

### Mock Server Won't Start

```bash
# Check if port 8001 is in use
lsof -i :8001

# Kill the process if needed
kill -9 <PID>

# Try again
./scripts/run_mock_server.sh
```

### Data Collection Fails

1. Verify Mock Server is running:
   ```bash
   curl http://localhost:8001/
   ```

2. Check switches are in database:
   ```bash
   # From Django shell or SQL
   SELECT hostname, ip_address FROM switches WHERE is_active = true;
   ```

3. Verify scenario loaded:
   ```bash
   curl http://localhost:8001/admin/devices
   ```

### Empty Dashboard

1. Ensure maintenance ID matches:
   - Seed script uses `TEST-100` by default
   - Dashboard expects `TEST-100` or create one in admin

2. Check data was collected:
   ```bash
   # Check collection_records table has data
   ```

3. Run evaluation manually:
   ```bash
   # Trigger evaluation via API or admin panel
   ```

## Integration with Real API

To switch between Mock Server and real external API:

```python
# Use Mock Server (for testing)
export EXTERNAL_API_SERVER="http://localhost:8001"

# Use Real API (for production)
export EXTERNAL_API_SERVER="http://real-api-server.example.com"
```

The data collection service automatically uses the configured server.
