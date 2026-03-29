# Release Report v2.19.14

> **Date**: 2026-03-29
> **Image**: `coolguazi/network-dashboard-base:v2.19.14`
> **Platform**: linux/amd64
> **CVE Scan**: Trivy CRITICAL = 0

---

## Changes in v2.19.14

### Bugfix: Uplink Expectation Unique Constraint

**Problem**: Migration `i4c5d6e7f8g9` incorrectly changed the `uk_uplink_expectation` unique constraint from `(maintenance_id, hostname, local_interface)` to `(maintenance_id, hostname, expected_neighbor)`. This caused CSV imports to fail with "資料重複：該記錄已存在" when a device has multiple uplinks to the same neighbor (e.g., CORE-SW-01 → CORE-SW-02 via Te1/0/1 and Te1/0/2).

**Root Cause**: The constraint on `expected_neighbor` prevents multiple links between the same device pair, which is a valid network topology (dual uplinks, MLAG, etc.).

**Fix**:
- `app/db/models.py`: UniqueConstraint changed back to `(maintenance_id, hostname, local_interface)`
- New migration `o0p1q2r3s4t5_fix_uplink_unique_to_local_interface.py` with idempotent checks

**Affected Files**:
- `app/db/models.py`
- `alembic/versions/o0p1q2r3s4t5_fix_uplink_unique_to_local_interface.py`

### Bugfix: Topology Status Interface-Level Matching

**Problem**: The topology API (`/api/v1/topology/{maintenance_id}`) determined link status by checking if the hostname pair existed in uplink expectations — without verifying that the specific interfaces matched. This meant any LLDP-discovered link between two devices with expectations would be marked `expected_pass`, even if the actual interfaces differed from the expected ones.

**Example**:
- Expectation: CORE-SW-01 `TE1/0/1` ↔ CORE-SW-02 `TE1/0/1`
- Discovered: CORE-SW-01 `TE1/1/1` ↔ CORE-SW-02 `TE1/0/1`
- Old behavior: `expected_pass` (wrong — interfaces don't match)
- New behavior: `discovered` (correct — this is not the expected link)

**Fix**: Changed from `frozenset({src, dst}) in exp_pairs` (pair-level) to per-expectation matching of `(hostname, local_interface, expected_neighbor, expected_interface)`. Unmatched expectations now correctly show as `expected_fail`.

**Affected Files**:
- `app/api/endpoints/topology.py` (sections 5 and 6)

---

## Deployment Scenarios

All three deployment paths are safe with this release:

| Scenario | Behavior |
|----------|----------|
| **Fresh DB** | `create_all` uses corrected ORM model → `stamp head` |
| **Existing v2.19.13 DB** | Runs migration `o0p1q2r3s4t5` → drops wrong constraint, creates correct one |
| **Older DB (pre-v2.19.8)** | Chain: `i4c5d6e7f8g9` (wrong) → `o0p1q2r3s4t5` (fix) → net result correct |

---

## Cumulative Changes Since v2.19.0 (SNMP Subprocess Engine Era)

### SNMP Engine (v2.19.4)
- Replaced pysnmp with subprocess-based `snmpget`/`snmpbulkwalk`
- Eliminated asyncio callback race conditions that caused event loop deadlock at 50+ concurrent devices
- Process isolation: each SNMP operation runs as independent PID with its own socket
- Clean timeout handling: `proc.kill()` immediately releases all resources
- Drop-in replacement: all 11 collectors unchanged

### Collection Architecture (v2.19.0 - v2.19.6)
- **Device-centric rounds** (v2.19.0): 4,800 DB sessions/round → 400
- **Dual-frequency scheduling**: Fast round (180s, client data) + Full round (600s, indicators)
- **Two-phase collection** (v2.19.5): Probe reachability first, collect reachable devices immediately
- **Parallel collectors** (v2.19.6): Per-device time 80s → 12s, full cycle 10 min → 2 min
- **Negative cache**: Unreachable devices skipped before semaphore acquisition (600s TTL)

### Performance Summary

| Metric | v2.18 (pysnmp) | v2.19.6 (subprocess+parallel) |
|--------|---------------|-------------------------------|
| 50 devices concurrent | **crash** | stable |
| 200 devices concurrent | impossible | stable |
| Per-device collection | ~200s | ~12s |
| Full cycle (200 devices) | N/A | ~2 min |
| DB sessions per round | 4,800 | 400 |

### Topology (v2.19.9 - v2.19.14)
- Interface name normalization: 70+ formats (GigabitEthernet→GE, Port-Channel→Po, etc.)
- Link deduplication via normalized remote_interface
- Interface-level expectation matching (v2.19.14)
- Uplink unique constraint fix (v2.19.14)

### Case Management (v2.19.13)
- Added `CaseStatus.IGNORED` for cases that don't need processing
- Defensive Alembic migration with `information_schema` checks

### Alembic Migrations (v2.19.8)
- All 15 migrations upgraded with idempotent `information_schema` checks
- Safe on any deployment path: fresh DB, create_all DB, or alembic-managed DB

### Scheduler Resilience (v2.19.13)
- Auto-restart on collection loop crash (10s delay)
- `write_log` exception isolation: DB log failures don't interrupt SNMP collection

### Other Fixes (v2.19.13)
- CSV template fixes: Contacts missing `department`, Device Mapping extra comma
- Dead code removal: 5 unused `device_mappings` DB queries in client_comparison_service.py
- LatestClientRecord unique constraint: corrected to `(maintenance_id, client_id)`
- SNMP probe lock race condition: `setdefault` replaces check-then-set
- hostname_map dedup: `dict[str, set]` replaces `dict[str, list]`

---

## Test Results

- **Unit tests**: 1,272 passed, 33 pre-existing failures (transceiver indicator mocks, contacts mock exhaustion, port-channel normalization)
- **CVE scan**: 0 Critical vulnerabilities
- **Integration test**: Mock SNMP mode with 10-device 3-tier topology verified
