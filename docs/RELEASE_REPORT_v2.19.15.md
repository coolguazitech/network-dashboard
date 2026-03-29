# Release Report v2.19.15

> **Date**: 2026-03-29
> **Image**: `coolguazi/network-dashboard-base:v2.19.15`
> **Platform**: linux/amd64
> **CVE Scan**: Trivy CRITICAL = 0

---

## Changes in v2.19.15

### Bugfix: Topology Per-Port Physical Constraint Dedup

**Problem**: LLDP neighbor discovery is bidirectional — both ends report the same link. The topology API could show the same physical port connected to two different remote ports simultaneously, which is physically impossible.

**Fix**: Added `used_ports: set[tuple[str, str]]` tracking in topology API. Each `(hostname, interface)` can only appear once across all links. First-seen link wins; subsequent links referencing an already-used port are skipped.

### Bugfix: expected_fail Links Respect Per-Port Dedup

**Problem**: Unmatched uplink expectations generated `expected_fail` links even when their ports were already used by discovered links, causing the same port to appear in two links on the graph.

**Fix**: Extended `used_ports` dedup to Section 6 (expected_fail generation). If an expectation's local or remote port is already occupied by a discovered link, the expected_fail link is suppressed.

### Enhancement: Mixed-Status Link Label Annotations

**Problem**: When the same device pair has both discovered and expected_fail links, users couldn't tell which line in the label was actual vs expected.

**Fix**: Frontend `Topology.vue` now annotates each line with `[實際]` or `[✗ 期望]` when an aggregated edge contains links with different statuses.

**Affected Files**:
- `app/api/endpoints/topology.py` (sections 4, 5, 6)
- `frontend/src/views/Topology.vue` (link aggregation logic)

---

## Deployment Scenarios

| Scenario | Behavior |
|----------|----------|
| **Fresh DB** | `create_all` uses corrected ORM model → `stamp head` |
| **Existing v2.19.14 DB** | No new migrations — code-only changes |
| **Older DB (pre-v2.19.14)** | Runs migrations up to `o0p1q2r3s4t5` → correct state |

---

## Test Results

- **Unit tests**: 1,272 passed
- **CVE scan**: 0 Critical vulnerabilities
- **Integration test**: Full CRUD + topology + CSV import verified
