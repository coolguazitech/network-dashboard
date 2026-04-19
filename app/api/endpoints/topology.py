"""
Topology API endpoint.

以設備清單 (MaintenanceDeviceList) 為基礎節點，
疊加 LLDP/CDP 鄰居連線，並比對 UplinkExpectation 標記連線狀態。
BFS 計算階層：degree 最高的節點為 root (Core)，逐層展開。
"""
from __future__ import annotations

from collections import defaultdict, deque

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.endpoints.auth import get_current_user
from app.db.base import get_async_session as get_session
from app.db.models import (
    MaintenanceDeviceList,
    NeighborRecord,
    UplinkExpectation,
)
from app.core.interfaces import is_topology_management_link
from app.repositories.typed_records import get_typed_repo
from app.services.indicator_service import IndicatorService

router = APIRouter(tags=["topology"])

_UPLINK_COLLECTION_TYPES = ("get_uplink_lldp", "get_uplink_cdp")


class TopologyNode(BaseModel):
    name: str
    category: int       # 0=設備清單, 1=外部設備
    neighbor_count: int
    ip_address: str | None = None
    vendor: str | None = None
    in_device_list: bool
    level: int          # BFS 階層 (0=Core, 1=Agg, 2=Edge, ...)
    indicator_failures: list[str] | None = None  # 驗收失敗的指標名稱列表
    ping_failed: bool = False                    # Ping 不可達


class TopologyLink(BaseModel):
    source: str
    target: str
    local_interface: str
    remote_interface: str
    status: str          # "expected_pass" | "expected_fail" | "discovered"
    is_management: bool


class TopologyResponse(BaseModel):
    nodes: list[TopologyNode]
    links: list[TopologyLink]
    categories: list[dict]
    stats: dict


import re as _re

# Hostname 關鍵字優先級（數字越小 = 層級越高）
# 兩條 chain 合併：CORE/RT/BDR > AGG/SSPN > SPN > LAGG > EDGE/.../LEAF
_HOSTNAME_TIER_PATTERNS: list[tuple[int, _re.Pattern]] = [
    (0, _re.compile(r"(?:CORE|RT|BDR)", _re.IGNORECASE)),
    (1, _re.compile(r"(?:AGG|SSPN)", _re.IGNORECASE)),
    (2, _re.compile(r"SPN", _re.IGNORECASE)),
    (3, _re.compile(r"LAGG", _re.IGNORECASE)),
    (4, _re.compile(r"(?:EDGE|EQP|AMHS|OTHERS|SNR|TOR|ENG|GDS|LEAF)",
                     _re.IGNORECASE)),
]
_FW_PATTERN = _re.compile(r"FW", _re.IGNORECASE)
_DEFAULT_TIER = 5


def _hostname_tier(hostname: str) -> int:
    """回傳 hostname 的層級優先度（數字越小越高層）。"""
    for tier, pat in _HOSTNAME_TIER_PATTERNS:
        if pat.search(hostname):
            return tier
    return _DEFAULT_TIER


def _compute_hierarchy(
    all_hostnames: set[str],
    adjacency: dict[str, set[str]],
) -> dict[str, int]:
    """
    基於圖心 (eccentricity) + hostname 關鍵字的階層計算。

    算法：
    1. 分離連通分量
    2. 對每個分量計算各節點的離心率 (eccentricity)
    3. 離心率平手時，以 hostname 關鍵字優先級打破平手
       CORE/RT/BDR > AGG/SSPN > SPN > LAGG > EDGE/EQP/LEAF/...
    4. 從圖心做 BFS 逐層展開
    5. FW 節點拉到與直連鄰居相同的層級
    6. 孤立節點放到最底層
    """
    if not all_hostnames:
        return {}

    adj = {h: adjacency.get(h, set()) for h in all_hostnames}

    # ── 找連通分量 ──
    visited: set[str] = set()
    components: list[set[str]] = []
    for h in all_hostnames:
        if h in visited:
            continue
        comp: set[str] = set()
        q: deque[str] = deque([h])
        while q:
            node = q.popleft()
            if node in comp:
                continue
            comp.add(node)
            visited.add(node)
            for nb in adj.get(node, set()):
                if nb not in comp:
                    q.append(nb)
        components.append(comp)

    components.sort(key=len, reverse=True)

    levels: dict[str, int] = {}
    global_max_level = 0

    for comp in components:
        if len(comp) == 1:
            continue

        # ── 計算離心率 ──
        eccentricity: dict[str, int] = {}
        for node in comp:
            dist: dict[str, int] = {node: 0}
            q = deque([node])
            while q:
                curr = q.popleft()
                for nb in adj.get(curr, set()):
                    if nb in comp and nb not in dist:
                        dist[nb] = dist[curr] + 1
                        q.append(nb)
            eccentricity[node] = max(dist.values())

        # ── 找圖心：離心率最小 + hostname 優先級最高 ──
        min_ecc = min(eccentricity.values())
        candidates = {h for h, e in eccentricity.items() if e == min_ecc}

        # 平手時，只保留 hostname tier 最高（數字最小）的
        if len(candidates) > 1:
            best_tier = min(_hostname_tier(h) for h in candidates)
            center = {
                h for h in candidates if _hostname_tier(h) == best_tier
            }
        else:
            center = candidates

        # ── 從圖心 BFS 展開 ──
        comp_levels: dict[str, int] = {}
        q = deque()
        for c in center:
            comp_levels[c] = 0
            q.append(c)

        while q:
            node = q.popleft()
            for nb in sorted(adj.get(node, set())):
                if nb in comp and nb not in comp_levels:
                    comp_levels[nb] = comp_levels[node] + 1
                    q.append(nb)

        # ── BFS 同層平手：hostname tier 低的應該在更深層 ──
        # 收集每層的節點，若同層內 tier 差異大則拆分
        max_lv = max(comp_levels.values()) if comp_levels else 0
        for lv in range(max_lv + 1):
            nodes_at_lv = [h for h, l in comp_levels.items() if l == lv]
            if len(nodes_at_lv) <= 1:
                continue
            tiers_at_lv = {_hostname_tier(h) for h in nodes_at_lv}
            if len(tiers_at_lv) <= 1:
                continue
            # 同一 BFS 層有不同 tier → tier 較大的往下推
            best = min(tiers_at_lv)
            for h in nodes_at_lv:
                if _hostname_tier(h) > best:
                    # 推到下一層，同時級聯推動其 BFS 子樹
                    _push_down(h, comp_levels, adj, comp)

        # ── FW 節點：與直連鄰居同層 ──
        for node in comp:
            if _FW_PATTERN.search(node) and node in comp_levels:
                neighbor_levels = [
                    comp_levels[nb] for nb in adj.get(node, set())
                    if nb in comp_levels
                ]
                if neighbor_levels:
                    comp_levels[node] = min(neighbor_levels)

        levels.update(comp_levels)
        comp_max = max(comp_levels.values()) if comp_levels else 0
        if comp_max > global_max_level:
            global_max_level = comp_max

    # 孤立節點 / 未分配的放最底層
    for h in all_hostnames:
        if h not in levels:
            levels[h] = global_max_level + 1

    return levels


def _push_down(
    node: str,
    levels: dict[str, int],
    adj: dict[str, set[str]],
    comp: set[str],
) -> None:
    """將節點推到下一層，並級聯推動其子樹（BFS children）。"""
    old_lv = levels[node]
    new_lv = old_lv + 1
    levels[node] = new_lv
    # 級聯：如果鄰居的層 == old_lv + 1（原本的下一層），也要推
    for nb in adj.get(node, set()):
        if nb in comp and levels.get(nb, -1) == old_lv + 1:
            _push_down(nb, levels, adj, comp)


@router.get("/topology/{maintenance_id}")
async def get_topology(
    maintenance_id: str,
    session: AsyncSession = Depends(get_session),
    _user=Depends(get_current_user),
) -> TopologyResponse:
    """
    產生拓樸圖資料。

    節點來源: MaintenanceDeviceList (new_hostname)
    連線來源: NeighborRecord (LLDP/CDP)
    連線狀態: 比對 UplinkExpectation
    階層計算: BFS from highest-degree nodes
    """
    # ── 1. 載入設備清單 ──
    device_stmt = select(MaintenanceDeviceList).where(
        MaintenanceDeviceList.maintenance_id == maintenance_id,
    )
    device_result = await session.execute(device_stmt)
    device_rows = device_result.scalars().all()

    device_map: dict[str, MaintenanceDeviceList] = {}
    for d in device_rows:
        if d.new_hostname:
            device_map[d.new_hostname] = d

    # ── 2. 載入 LLDP/CDP 最新鄰居記錄 ──
    all_records: list[NeighborRecord] = []
    for ct in _UPLINK_COLLECTION_TYPES:
        repo = get_typed_repo(ct, session)
        records = await repo.get_latest_per_device(maintenance_id)
        all_records.extend(records)

    # ── 3. 載入 UplinkExpectation ──
    exp_stmt = select(UplinkExpectation).where(
        UplinkExpectation.maintenance_id == maintenance_id,
    )
    exp_result = await session.execute(exp_stmt)
    expectations = exp_result.scalars().all()

    exp_lookup: dict[tuple[str, str], list[UplinkExpectation]] = defaultdict(list)
    for exp in expectations:
        exp_lookup[(exp.hostname, exp.expected_neighbor)].append(exp)

    exp_pairs: set[frozenset] = set()
    for exp in expectations:
        exp_pairs.add(frozenset({exp.hostname, exp.expected_neighbor}))

    # interface-level 精確比對用
    exp_if_set: set[tuple[str, str, str, str]] = set()
    for exp in expectations:
        exp_if_set.add((exp.hostname, exp.local_interface,
                        exp.expected_neighbor, exp.expected_interface))

    # ── 4. 建構鄰居關係 (去重 LLDP+CDP) ──
    seen_links: set[tuple[str, str, str, str]] = set()
    used_ports: set[tuple[str, str]] = set()  # (hostname, local_if) — 每個 port 只能一條線
    actual_neighbors: dict[str, set[str]] = defaultdict(set)
    raw_links: list[dict] = []

    for record in all_records:
        src = record.switch_hostname
        dst = record.remote_hostname
        local_if = record.local_interface
        remote_if = record.remote_interface

        actual_neighbors[src].add(dst)
        actual_neighbors[dst].add(src)

        pair = tuple(sorted([src, dst]))
        if pair[0] == src:
            link_key = (pair[0], pair[1], local_if, remote_if)
        else:
            link_key = (pair[0], pair[1], remote_if, local_if)

        if link_key in seen_links:
            continue

        # 物理約束：一個 port 只能接一條線
        if (src, local_if) in used_ports or (dst, remote_if) in used_ports:
            continue

        seen_links.add(link_key)
        used_ports.add((src, local_if))
        used_ports.add((dst, remote_if))

        raw_links.append({
            "source": src,
            "target": dst,
            "local_interface": local_if,
            "remote_interface": remote_if,
        })

    # ── 5. 判斷連線狀態 + 管理介面（interface-level 精確比對）──
    links: list[TopologyLink] = []
    stats = {"expected_pass": 0, "expected_fail": 0, "discovered": 0}
    matched_exp_ids: set[int] = set()

    for lnk in raw_links:
        src, dst = lnk["source"], lnk["target"]
        local_if = lnk["local_interface"]
        remote_if = lnk["remote_interface"]

        is_mgmt = (
            is_topology_management_link(local_if)
            or is_topology_management_link(remote_if)
        )

        # interface-level: 正向 (src→dst) 或反向 (dst→src) 比對
        status = "discovered"
        if frozenset({src, dst}) in exp_pairs:
            for exp in exp_lookup.get((src, dst), []):
                if exp.local_interface == local_if and exp.expected_interface == remote_if:
                    status = "expected_pass"
                    matched_exp_ids.add(exp.id)
                    break
            if status != "expected_pass":
                for exp in exp_lookup.get((dst, src), []):
                    if exp.local_interface == remote_if and exp.expected_interface == local_if:
                        status = "expected_pass"
                        matched_exp_ids.add(exp.id)
                        break

        links.append(TopologyLink(
            source=src, target=dst,
            local_interface=local_if, remote_interface=remote_if,
            status=status, is_management=is_mgmt,
        ))
        stats[status] += 1

    # ── 6. 未匹配的期望 → expected_fail（同樣遵守 per-port 物理約束）──
    for exp in expectations:
        if exp.id not in matched_exp_ids:
            local_port = (exp.hostname, exp.local_interface)
            remote_port = (exp.expected_neighbor, exp.expected_interface)
            if local_port in used_ports or remote_port in used_ports:
                continue
            used_ports.add(local_port)
            used_ports.add(remote_port)
            links.append(TopologyLink(
                source=exp.hostname, target=exp.expected_neighbor,
                local_interface=exp.local_interface,
                remote_interface=exp.expected_interface,
                status="expected_fail", is_management=False,
            ))
            stats["expected_fail"] += 1

    # ── 7. 載入指標驗收失敗資料（排除被忽略的指標）──
    device_failures: dict[str, list[str]] = defaultdict(list)
    ping_failed_devices: set[str] = set()
    try:
        # 查詢每台設備被忽略的指標
        ign_stmt = select(
            MaintenanceDeviceList.new_hostname,
            MaintenanceDeviceList.ignored_indicators,
        ).where(
            MaintenanceDeviceList.maintenance_id == maintenance_id,
            MaintenanceDeviceList.new_hostname.isnot(None),
        )
        ign_result = await session.execute(ign_stmt)
        device_ignored_map: dict[str, list] = {
            row[0]: (row[1] or [])
            for row in ign_result.all()
            if row[1]
        }

        indicator_svc = IndicatorService()
        results = await indicator_svc.evaluate_all(maintenance_id, session)
        _INDICATOR_LABELS = {
            "transceiver": "光模塊",
            "version": "版本",
            "uplink": "Uplink",
            "port_channel": "Port Channel",
            "power": "電源",
            "fan": "風扇",
            "error_count": "錯誤計數",
            "ping": "Ping",
        }
        for ind_name, result in results.items():
            for f in (result.failures or []):
                device = f.get("device", "")
                if not device:
                    continue
                # 跳過被忽略的指標
                if ind_name in device_ignored_map.get(device, []):
                    continue
                label = _INDICATOR_LABELS.get(ind_name, ind_name)
                reason = f.get("reason", "")
                short = f"{label}: {reason}" if reason else label
                device_failures[device].append(short)
                if ind_name == "ping":
                    ping_failed_devices.add(device)
    except Exception:
        pass  # topology 不因 indicator 失敗而中斷

    # ── 8. 建構節點列表 + BFS 階層 ──
    all_hostnames: set[str] = set(device_map.keys())
    for lnk in links:
        all_hostnames.add(lnk.source)
        all_hostnames.add(lnk.target)

    # 鄰居計數（用於所有連線，包含 mgmt）
    neighbor_count: dict[str, set[str]] = defaultdict(set)
    for lnk in links:
        neighbor_count[lnk.source].add(lnk.target)
        neighbor_count[lnk.target].add(lnk.source)

    # BFS 計算階層（排除管理介面連線，避免 mgmt 連線干擾階層判定）
    non_mgmt_adj: dict[str, set[str]] = defaultdict(set)
    for lnk in links:
        if not lnk.is_management:
            non_mgmt_adj[lnk.source].add(lnk.target)
            non_mgmt_adj[lnk.target].add(lnk.source)

    hierarchy = _compute_hierarchy(all_hostnames, non_mgmt_adj)

    nodes: list[TopologyNode] = []
    for hostname in sorted(all_hostnames):
        in_list = hostname in device_map
        dev = device_map.get(hostname)
        failures = device_failures.get(hostname)
        nodes.append(TopologyNode(
            name=hostname,
            category=0 if in_list else 1,
            neighbor_count=len(neighbor_count.get(hostname, set())),
            ip_address=dev.new_ip_address if dev else None,
            vendor=dev.new_vendor if dev else None,
            in_device_list=in_list,
            level=hierarchy.get(hostname, 0),
            indicator_failures=failures if failures else None,
            ping_failed=hostname in ping_failed_devices,
        ))

    categories = [
        {"name": "設備清單"},
        {"name": "管理設備"},
    ]

    # 階層統計
    level_counts: dict[int, int] = defaultdict(int)
    for n in nodes:
        level_counts[n.level] += 1
    max_level = max(hierarchy.values()) if hierarchy else 0

    stats["total_nodes"] = len(nodes)
    stats["device_list_nodes"] = sum(1 for n in nodes if n.in_device_list)
    stats["external_nodes"] = stats["total_nodes"] - stats["device_list_nodes"]
    stats["total_links"] = len(links)
    stats["max_level"] = max_level
    stats["level_counts"] = dict(sorted(level_counts.items()))

    return TopologyResponse(
        nodes=nodes, links=links,
        categories=categories, stats=stats,
    )
