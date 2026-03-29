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


def _compute_hierarchy(
    all_hostnames: set[str],
    adjacency: dict[str, set[str]],
) -> dict[str, int]:
    """
    基於圖心 (graph center) 的階層計算，不依賴命名或外部資訊。

    算法：
    1. 分離連通分量
    2. 對每個分量計算各節點的離心率 (eccentricity)
       eccentricity(v) = max{ shortest_path(v, u) | u ∈ component }
    3. 離心率最小的節點群 = 圖心 (center) = level 0
    4. 從圖心做 BFS 逐層展開
    5. 孤立節點放到最底層

    為何用離心率而不是 degree：
    - degree 高只代表連線多，但如果一台 AGG 接了很多 Edge，
      degree 可能比 Core 還高，階層就會算錯。
    - 離心率衡量的是「離最遠節點的距離」，真正的 Core 設備
      在網路中心，到任何節點的最遠距離最短，不受起點影響。
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

    # 按大小排序（最大的在前），小分量會被排在更高的 level
    components.sort(key=len, reverse=True)

    levels: dict[str, int] = {}
    global_max_level = 0

    for comp in components:
        if len(comp) == 1:
            # 孤立節點稍後處理
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

        # ── 找圖心 (最小離心率) ──
        min_ecc = min(eccentricity.values())
        center = {h for h, e in eccentricity.items() if e == min_ecc}

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

        # 合併到全域 levels
        levels.update(comp_levels)
        comp_max = max(comp_levels.values()) if comp_levels else 0
        if comp_max > global_max_level:
            global_max_level = comp_max

    # 孤立節點 / 未分配的放最底層
    for h in all_hostnames:
        if h not in levels:
            levels[h] = global_max_level + 1

    return levels


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

    # ── 4. 建構鄰居關係 (去重 LLDP+CDP) ──
    seen_links: set[tuple[str, str, str, str]] = set()
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
        seen_links.add(link_key)

        raw_links.append({
            "source": src,
            "target": dst,
            "local_interface": local_if,
            "remote_interface": remote_if,
        })

    # ── 5. 判斷連線狀態 + 管理介面 ──
    links: list[TopologyLink] = []
    stats = {"expected_pass": 0, "expected_fail": 0, "discovered": 0}

    for lnk in raw_links:
        src, dst = lnk["source"], lnk["target"]
        local_if = lnk["local_interface"]
        remote_if = lnk["remote_interface"]

        pair_key = frozenset({src, dst})
        is_mgmt = (
            is_topology_management_link(local_if)
            or is_topology_management_link(remote_if)
        )

        if pair_key in exp_pairs:
            status = "expected_pass"
        else:
            status = "discovered"

        links.append(TopologyLink(
            source=src, target=dst,
            local_interface=local_if, remote_interface=remote_if,
            status=status, is_management=is_mgmt,
        ))
        stats[status] += 1

    # ── 6. 期望中有但實際不存在 → expected_fail ──
    for (hostname, expected_neighbor), exps in exp_lookup.items():
        actual_set = actual_neighbors.get(hostname, set())
        reverse_set = actual_neighbors.get(expected_neighbor, set())

        if expected_neighbor not in actual_set and hostname not in reverse_set:
            for exp in exps:
                links.append(TopologyLink(
                    source=hostname, target=expected_neighbor,
                    local_interface=exp.local_interface,
                    remote_interface=exp.expected_interface,
                    status="expected_fail", is_management=False,
                ))
                stats["expected_fail"] += 1

    # ── 7. 載入指標驗收失敗資料 ──
    device_failures: dict[str, list[str]] = defaultdict(list)
    try:
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
                if device:
                    label = _INDICATOR_LABELS.get(ind_name, ind_name)
                    reason = f.get("reason", "")
                    short = f"{label}: {reason}" if reason else label
                    device_failures[device].append(short)
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
