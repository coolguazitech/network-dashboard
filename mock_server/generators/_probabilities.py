"""Per-MAC / per-interface randomness probability constants.

Each value is the probability that a given attribute changes for a given
MAC (or interface) on a single collection cycle.  Values are intentionally
small (1-5%) so most items remain stable most of the time — realistic
network behavior where only a handful of clients experience changes.
"""
from __future__ import annotations

# ── MAC table mutations ─────────────────────────────────────────────
VLAN_CHANGE_PROB = 0.03        # 3% chance VLAN shifts
PORT_CHANGE_PROB = 0.02        # 2% chance port changes
NOT_DETECTED_PROB = 0.03       # 3% chance MAC disappears from table

# ── Interface status mutations (per-interface, per-cycle) ───────────
SPEED_CHANGE_PROB = 0.05       # 5% chance speed flips
DUPLEX_CHANGE_PROB = 0.02      # 2% chance duplex flips
LINK_DOWN_PROB = 0.03          # 3% chance link status toggles

# ── ACL mutations (per-interface, per-cycle) ────────────────────────
STATIC_ACL_CHANGE_PROB = 0.02  # 2% chance static ACL number changes
DYNAMIC_ACL_CHANGE_PROB = 0.03 # 3% chance dynamic ACL number changes

# ── Ping mutations (per-IP, per-cycle) ──────────────────────────────
PING_FAIL_PROB = 0.05          # 5% chance reachable IP becomes unreachable

# ── Valid value pools ───────────────────────────────────────────────
VALID_VLANS = [10, 20, 100, 200]

HPE_SPEEDS = ["100M(a)", "1G(a)", "10G(a)"]
IOS_SPEEDS = ["a-100", "a-1000", "10G"]
NXOS_SPEEDS = ["100", "1000", "10G"]

HPE_DUPLEXES = ["F(a)", "H(a)"]
IOS_DUPLEXES = ["a-full", "a-half"]
NXOS_DUPLEXES = ["full", "half"]

STATIC_ACL_ALTERNATIVES = [3001, 3002, 3003, 3010, 3099]
