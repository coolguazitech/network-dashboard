"""Mock: GNMS Topology API (POST /api/v1/topology).

根據 DB 中的設備清單，產生模擬的鄰居拓樸回應。
每台設備回傳 2-6 個 neighbor，其中 is_up_link=true 的為 uplink。
"""
from __future__ import annotations

import random

from mock_server import db

INTERFACES_HPE = [
    "GigabitEthernet1/0/{p}",
    "TenGigabitEthernet1/0/{p}",
]
INTERFACES_CISCO = [
    "Ethernet1/{p}",
    "Ethernet1/{p}/1",
]
MODELS = {
    "HPE": ("HPE", "5130-48G-PoE+", "switch"),
    "Cisco-IOS": ("Cisco", "C9300-48T", "switch"),
    "Cisco-NXOS": ("Cisco", "N9K-C93180YC-FX", "switch"),
}
UPLINK_PEERS = [
    "CORE-SW-01", "CORE-SW-02", "AGG-SW-01", "AGG-SW-02",
    "SPINE-01", "SPINE-02",
]


def generate_for_devices(device_names: list[str]) -> dict:
    """
    為一批設備產生 Topology 回應。

    回傳格式與真實 GNMS Topology API 一致：
    {
        "device_name": {
            "device_name": str,
            "neighbors": {
                "local_interface": {
                    "to_device_name": str,
                    "to_interface_name": str,
                    "is_up_link": bool,
                    ...
                }
            }
        }
    }
    """
    mid = db.get_active_maintenance_id()
    device_info = _get_device_info(mid, device_names) if mid else {}
    all_hostnames = set(device_names)

    result: dict[str, dict] = {}

    for name in device_names:
        rng = random.Random(name)
        info = device_info.get(name, {})
        vendor = info.get("vendor", "Cisco-IOS")
        ip = info.get("ip", f"10.0.0.{hash(name) % 254 + 1}")
        mfr, model, model_type = MODELS.get(vendor, MODELS["Cisco-IOS"])

        # 決定 neighbor 數量：2-5 個
        neighbor_count = rng.randint(2, 5)
        neighbors: dict[str, dict] = {}

        # 至少 1-2 個 uplink
        uplink_count = rng.randint(1, min(2, neighbor_count))

        for i in range(neighbor_count):
            is_uplink = i < uplink_count
            port_num = rng.randint(1, 48)

            if "HPE" in vendor:
                local_if = rng.choice(INTERFACES_HPE).format(p=port_num)
            else:
                local_if = rng.choice(INTERFACES_CISCO).format(p=port_num)

            if is_uplink:
                # Uplink: 連接到 CORE / AGG / SPINE
                # 優先選設備清單中存在的設備
                candidates = [h for h in all_hostnames if h != name and (
                    "CORE" in h or "AGG" in h or "SPINE" in h
                )]
                if not candidates:
                    candidates = [p for p in UPLINK_PEERS]
                to_device = rng.choice(candidates)
                to_port = rng.randint(1, 48)
                to_if = f"Ethernet1/{to_port}"
                to_level = rng.choice([1, 2])
            else:
                # Downlink: 連接到其他 access switch 或隨機設備
                to_device = f"ACCESS-SW-{rng.randint(1, 20):02d}"
                to_port = rng.randint(1, 48)
                to_if = f"GigabitEthernet1/0/{to_port}"
                to_level = rng.choice([3, 4])

            to_mfr, to_model, to_model_type = MODELS.get(
                rng.choice(list(MODELS.keys())),
                MODELS["Cisco-IOS"],
            )

            neighbors[local_if] = {
                "to_device_name": to_device,
                "to_interface_name": to_if,
                "to_device_manufacturer": to_mfr,
                "to_device_model": to_model,
                "to_device_model_type": to_model_type,
                "to_device_level": to_level,
                "is_up_link": is_uplink,
            }

        result[name] = {
            "device_name": name,
            "management_ip": ip,
            "level": rng.choice([2, 3]),
            "manufacturer": mfr,
            "model": model,
            "model_type": model_type,
            "platform": vendor,
            "role": "access" if "RT-FAB" in name else "distribution",
            "service": "network",
            "neighbors": neighbors,
        }

    return result


def _get_device_info(
    maintenance_id: str, device_names: list[str],
) -> dict[str, dict]:
    """從 DB 查詢設備的 IP/vendor/tenant_group。"""
    engine = db.get_engine()
    with engine.connect() as conn:
        from sqlalchemy import text

        placeholders = ", ".join(f":n{i}" for i in range(len(device_names)))
        params = {"mid": maintenance_id}
        params.update({f"n{i}": n for i, n in enumerate(device_names)})

        rows = conn.execute(
            text(
                "SELECT new_hostname, new_ip_address, new_vendor, tenant_group "
                "FROM maintenance_device_list "
                f"WHERE maintenance_id = :mid AND new_hostname IN ({placeholders})"
            ),
            params,
        ).fetchall()

    result = {}
    for row in rows:
        result[row[0]] = {
            "ip": row[1] or "",
            "vendor": row[2] or "Cisco-IOS",
            "tenant_group": row[3] or "F18",
        }
    return result
