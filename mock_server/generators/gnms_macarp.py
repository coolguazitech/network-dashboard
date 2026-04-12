"""Mock: GNMS MacARP batch API (/api/v1/macarp/batch).

根據 DB 中的設備清單和 client 清單，產生模擬的 MacARP 回應。
每台設備回傳 3-15 個 client 記錄。
"""
from __future__ import annotations

import hashlib
import random
from datetime import datetime, timezone

from mock_server import db

AREAS = ["FAB-A", "FAB-B", "FAB-C", "OFC-1", "OFC-2"]
PLATFORMS = ["Cisco IOS", "Cisco NX-OS", "HPE Comware"]
MODELS = [
    "C9300-48T", "C9300-24P", "N9K-C93180YC-FX",
    "5130-48G-PoE+", "WS-C3850-48T",
]


def generate_for_devices(device_names: list[str]) -> dict:
    """
    為一批設備產生 MacARP 回應。

    MacARP 是外部 API，不讀本系統 DB 的 client 清單。
    每台設備根據 hostname 產生獨立的模擬 client 資料。

    Args:
        device_names: 要查詢的設備 hostname 清單

    Returns:
        GNMS MacARP API 格式的 dict
    """
    # 從 DB 取得活躍歲修（只用於查設備 IP/vendor）
    mid = db.get_active_maintenance_id()
    device_info = _get_device_info(mid, device_names) if mid else {}

    data: dict[str, list[dict]] = {}

    for name in device_names:
        info = device_info.get(name, {})
        device_ip = info.get("ip", f"10.0.0.{hash(name) % 254 + 1}")
        vendor = info.get("vendor", "Cisco-IOS")
        tenant = info.get("tenant_group", "F18")

        # 每台設備獨立產生 mock client（不讀 DB，避免跟匯入資料循環）
        assigned_clients = _generate_random_clients(name, device_ip, tenant)

        records = []
        for client in assigned_clients:
            records.append({
                "device_name": name,
                "device_model": random.choice(MODELS),
                "platform": _vendor_to_platform(vendor),
                "device_ip": device_ip,
                "interface_name": f"GigabitEthernet1/0/{random.randint(1, 48)}",
                "user_ip": client.get("ip", ""),
                "user_mac": client.get("mac", ""),
                "user_devicename": f"PC-{client.get('mac', '')[-5:].replace(':', '')}",
                "owner": client.get("owner", ""),
                "tenant_group": client.get("tenant_group", tenant),
                "area": random.choice(AREAS),
                "effective_acl_number": random.randint(100, 199),
                "effective_acl_name": f"ACL-{random.choice(['PERMIT', 'DENY', 'AUTH'])}",
                "cms_ip": "",
                "gk_device_name": "",
                "gk_device_ip": "",
                "gk_slot": "",
                "gk_port": "",
                "last_seen": datetime.now(timezone.utc).isoformat(),
            })

        data[name] = records

    return {
        "bucket": "macarp",
        "data": data,
    }


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


def _assign_clients(
    device_name: str, mac_list: list[dict],
) -> list[dict]:
    """用 hash 把 client 分配到設備，模擬真實分佈。"""
    assigned = []
    for mac_entry in mac_list:
        mac = mac_entry.get("mac_address", "")
        h = hashlib.md5(f"{mac}:{device_name}".encode()).hexdigest()
        # ~3% 的 client 分配到每台設備
        if int(h[:2], 16) < 8:
            assigned.append({
                "mac": mac,
                "ip": mac_entry.get("ip_address", ""),
                "tenant_group": mac_entry.get("tenant_group", "F18"),
                "owner": "",
            })
    # 限制每台最多 20 個
    return assigned[:20]


def _generate_random_clients(
    device_name: str, device_ip: str, tenant: str,
) -> list[dict]:
    """若無 DB client，產生 3-8 個隨機 client。"""
    rng = random.Random(device_name)
    count = rng.randint(3, 8)
    clients = []
    for i in range(count):
        mac_bytes = rng.randbytes(3)
        mac = f"00:CC:DD:{mac_bytes[0]:02X}:{mac_bytes[1]:02X}:{mac_bytes[2]:02X}"
        ip = f"172.16.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
        clients.append({
            "mac": mac,
            "ip": ip,
            "tenant_group": tenant,
            "owner": rng.choice(["user_a", "user_b", "user_c", ""]),
        })
    return clients


def _vendor_to_platform(vendor: str) -> str:
    if "NXOS" in vendor.upper():
        return "Cisco NX-OS"
    elif "IOS" in vendor.upper():
        return "Cisco IOS"
    return "HPE Comware"
