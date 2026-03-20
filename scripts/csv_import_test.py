#!/usr/bin/env python3
"""
CSV Import Integration Test
===========================
模擬真實使用者透過 CSV 匯入 400 台設備（含拓樸）、5000 個 client、100 名聯絡人（含子分類），
然後對系統做全面功能測試。

Usage:
    python scripts/csv_import_test.py [--base-url http://localhost:8000]
"""
import argparse
import csv
import io
import json
import random
import sys
import time
import requests

# ── Config ──────────────────────────────────────────────────────────────────
BASE_URL = "http://localhost:8000"
API = f"{BASE_URL}/api/v1"
MAINTENANCE_ID = "CSV-TEST"
MAINTENANCE_NAME = "CSV匯入驗證 (400設備/5000客戶/100聯絡人)"
CREDS = {"username": "root", "password": "admin123"}

NUM_CORE = 4
NUM_AGG = 16          # 4 per core
NUM_ACCESS = 80       # 5 per agg
NUM_EDGE = 300        # spread across access
NUM_DEVICES = NUM_CORE + NUM_AGG + NUM_ACCESS + NUM_EDGE  # = 400
NUM_CLIENTS = 5000
NUM_CONTACTS = 100

VENDORS = ["Cisco-IOS", "Cisco-NXOS", "HPE"]
TENANT_GROUPS = ["F18", "F6", "AP", "F14", "F12"]
# ────────────────────────────────────────────────────────────────────────────

passed = 0
failed = 0
errors = []


def check(name: str, condition: bool, detail: str = ""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  ✓ {name}")
    else:
        failed += 1
        errors.append(f"{name}: {detail}")
        print(f"  ✗ {name} — {detail}")


def login() -> str:
    r = requests.post(f"{API}/auth/login", json=CREDS)
    assert r.status_code == 200, f"Login failed: {r.text}"
    return r.json()["token"]


def headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── Device topology builders ────────────────────────────────────────────────

def build_devices():
    """Build 400 devices with a realistic 4-tier topology."""
    devices = []
    uplinks = []  # (hostname, local_intf, neighbor, neighbor_intf)

    # --- Core switches ---
    for i in range(1, NUM_CORE + 1):
        devices.append({
            "hostname": f"CORE-SW-{i:02d}",
            "ip": f"10.0.0.{i}",
            "vendor": "Cisco-NXOS",
            "group": "F18",
            "desc": f"Core Switch #{i}",
        })

    # --- Aggregation switches ---
    for i in range(1, NUM_AGG + 1):
        core_id = ((i - 1) % NUM_CORE) + 1
        devices.append({
            "hostname": f"AGG-SW-{i:02d}",
            "ip": f"10.1.{i}.1",
            "vendor": "Cisco-NXOS",
            "group": "F18",
            "desc": f"Aggregation Switch #{i}",
        })
        uplinks.append((
            f"AGG-SW-{i:02d}", f"Ethernet1/{core_id}",
            f"CORE-SW-{core_id:02d}", f"Ethernet1/{i}",
        ))

    # --- Access switches ---
    for i in range(1, NUM_ACCESS + 1):
        agg_id = ((i - 1) % NUM_AGG) + 1
        devices.append({
            "hostname": f"ACC-SW-{i:03d}",
            "ip": f"10.2.{(i-1)//256}.{(i-1)%256 + 1}",
            "vendor": "Cisco-IOS",
            "group": random.choice(TENANT_GROUPS),
            "desc": f"Access Switch #{i}",
        })
        uplinks.append((
            f"ACC-SW-{i:03d}", f"GigabitEthernet0/1",
            f"AGG-SW-{agg_id:02d}", f"Ethernet1/{((i-1)//NUM_AGG)+10}",
        ))

    # --- Edge switches ---
    for i in range(1, NUM_EDGE + 1):
        acc_id = ((i - 1) % NUM_ACCESS) + 1
        # Use 10.3.x.y format — x = (i-1)//250, y = (i-1)%250 + 1 (avoid .0 and .255)
        octet3 = (i - 1) // 250
        octet4 = (i - 1) % 250 + 1
        devices.append({
            "hostname": f"EDGE-SW-{i:03d}",
            "ip": f"10.3.{octet3}.{octet4}",
            "vendor": random.choice(["Cisco-IOS", "HPE"]),
            "group": random.choice(TENANT_GROUPS),
            "desc": f"Edge Switch #{i}",
        })
        uplinks.append((
            f"EDGE-SW-{i:03d}", f"GigabitEthernet0/48",
            f"ACC-SW-{acc_id:03d}", f"GigabitEthernet0/{(i-1)//NUM_ACCESS + 2}",
        ))

    return devices, uplinks


def build_clients(devices):
    """Build 5000 clients spread across devices."""
    clients = []
    access_and_edge = [d for d in devices if d["hostname"].startswith(("ACC-", "EDGE-"))]
    for i in range(1, NUM_CLIENTS + 1):
        dev = access_and_edge[i % len(access_and_edge)]
        mac = f"{i//65536:02X}:{(i//256)%256:02X}:{i%256:02X}:AA:BB:{random.randint(0,255):02X}"
        # Ensure unique MACs
        mac = f"{(i >> 16) & 0xFF:02X}:{(i >> 8) & 0xFF:02X}:{i & 0xFF:02X}:{random.randint(0,255):02X}:{random.randint(0,255):02X}:{random.randint(0,255):02X}"
        clients.append({
            "mac_address": mac,
            "ip_address": f"192.168.{(i-1)//254}.{(i-1)%254 + 1}",
            "tenant_group": dev["group"],
            "description": f"Client-{i} on {dev['hostname']}",
        })
    return clients


def build_contacts():
    """Build 100 contacts across categories with subcategories."""
    categories = [
        ("網路維運組", ["L2維運", "L3維運", "無線維運"]),
        ("系統管理組", ["Windows", "Linux", "虛擬化"]),
        ("資安組", ["SOC", "滲透測試"]),
        ("專案管理", ["內部專案", "外部專案"]),
        ("廠商聯絡人", ["思科", "HPE", "Aruba", "Fortinet"]),
        ("管理層", []),  # 無子分類
    ]

    contacts = []
    surnames = ["陳", "林", "黃", "張", "李", "王", "吳", "劉", "蔡", "楊",
                "許", "鄭", "謝", "洪", "郭", "邱", "曾", "廖", "賴", "徐"]
    given_names = ["志明", "俊傑", "建宏", "家豪", "淑芬", "美玲", "雅婷", "怡君",
                   "宗翰", "柏翰", "冠宇", "承恩", "品妤", "宜臻", "佳蓉", "思穎",
                   "浩然", "子軒", "宥辰", "芷涵"]
    titles = ["工程師", "資深工程師", "主任工程師", "技術經理", "副理", "經理",
              "協理", "處長", "技術顧問", "專案經理"]
    companies = ["本公司", "本公司", "本公司", "思科台灣", "HPE Taiwan",
                 "Aruba Networks", "Fortinet", "中華電信", "遠傳電信"]
    departments = ["IT部", "網路組", "系統組", "資安處", "維運中心",
                   "技術服務部", "專案部", "客服中心"]

    idx = 0
    for cat_name, subcats in categories:
        if subcats:
            for sub in subcats:
                # 每個子分類放 3-5 人
                n = random.randint(3, 5)
                for _ in range(n):
                    if idx >= NUM_CONTACTS:
                        break
                    name = random.choice(surnames) + random.choice(given_names)
                    contacts.append({
                        "category_name": cat_name,
                        "sub_category_name": sub,
                        "name": name,
                        "title": random.choice(titles),
                        "department": random.choice(departments),
                        "company": random.choice(companies),
                        "phone": f"02-{random.randint(2000,2999)}-{random.randint(1000,9999)}",
                        "mobile": f"09{random.randint(10,99)}-{random.randint(100,999)}-{random.randint(100,999)}",
                        "extension": str(random.randint(1000, 9999)),
                        "notes": f"負責{sub}相關事務",
                    })
                    idx += 1
        else:
            # 無子分類，直接放父分類
            n = random.randint(3, 6)
            for _ in range(n):
                if idx >= NUM_CONTACTS:
                    break
                name = random.choice(surnames) + random.choice(given_names)
                contacts.append({
                    "category_name": cat_name,
                    "sub_category_name": "",
                    "name": name,
                    "title": random.choice(titles),
                    "department": random.choice(departments),
                    "company": random.choice(companies),
                    "phone": f"02-{random.randint(2000,2999)}-{random.randint(1000,9999)}",
                    "mobile": f"09{random.randint(10,99)}-{random.randint(100,999)}-{random.randint(100,999)}",
                    "extension": str(random.randint(1000, 9999)),
                    "notes": "",
                })
                idx += 1

    # Fill remaining contacts into random categories
    while idx < NUM_CONTACTS:
        cat_name, subcats = random.choice(categories)
        sub = random.choice(subcats) if subcats else ""
        name = random.choice(surnames) + random.choice(given_names)
        contacts.append({
            "category_name": cat_name,
            "sub_category_name": sub,
            "name": name,
            "title": random.choice(titles),
            "department": random.choice(departments),
            "company": random.choice(companies),
            "phone": f"02-{random.randint(2000,2999)}-{random.randint(1000,9999)}",
            "mobile": f"09{random.randint(10,99)}-{random.randint(100,999)}-{random.randint(100,999)}",
            "extension": str(random.randint(1000, 9999)),
            "notes": "",
        })
        idx += 1

    return contacts


# ── CSV generators ──────────────────────────────────────────────────────────

def devices_to_csv(devices) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["old_hostname", "old_ip_address", "old_vendor",
                "new_hostname", "new_ip_address", "new_vendor",
                "tenant_group", "description"])
    for d in devices:
        w.writerow(["", "", "",
                     d["hostname"], d["ip"], d["vendor"],
                     d["group"], d["desc"]])
    return buf.getvalue()


def uplinks_to_csv(uplinks) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["hostname", "local_interface", "expected_neighbor",
                "expected_interface", "description"])
    for hostname, local_intf, neighbor, neighbor_intf in uplinks:
        w.writerow([hostname, local_intf, neighbor, neighbor_intf, ""])
    return buf.getvalue()


def clients_to_csv(clients) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["mac_address", "ip_address", "tenant_group",
                "description", "default_assignee"])
    for c in clients:
        w.writerow([c["mac_address"], c["ip_address"],
                     c["tenant_group"], c["description"], ""])
    return buf.getvalue()


def contacts_to_csv(contacts) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["category_name", "sub_category_name", "name", "title",
                "department", "company", "phone", "mobile", "extension", "notes"])
    for c in contacts:
        w.writerow([c["category_name"], c["sub_category_name"], c["name"],
                     c["title"], c["department"], c["company"],
                     c["phone"], c["mobile"], c["extension"], c["notes"]])
    return buf.getvalue()


# ── Import helpers ──────────────────────────────────────────────────────────

def upload_csv(token: str, url: str, csv_data: str, filename: str = "import.csv") -> dict:
    """Upload CSV file to the given endpoint."""
    files = {"file": (filename, csv_data.encode("utf-8-sig"), "text/csv")}
    r = requests.post(url, headers=headers(token), files=files)
    return {"status": r.status_code, "body": r.json() if r.status_code < 500 else r.text}


# ── Main test flow ──────────────────────────────────────────────────────────

def main():
    global passed, failed, BASE_URL, API

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=BASE_URL)
    args = parser.parse_args()
    BASE_URL = args.base_url
    API = f"{BASE_URL}/api/v1"

    print("=" * 70)
    print("  CSV Import Integration Test")
    print("=" * 70)

    # ── 0. Login ────────────────────────────────────────────────────────
    print("\n[0] Login")
    token = login()
    check("Login successful", bool(token))

    # ── 1. Create maintenance ───────────────────────────────────────────
    print("\n[1] Create maintenance")
    r = requests.post(f"{API}/maintenance", headers=headers(token),
                      json={"id": MAINTENANCE_ID, "name": MAINTENANCE_NAME})
    check("Create maintenance", r.status_code in (200, 201),
          f"status={r.status_code} body={r.text[:200]}")

    # ── 2. Generate data ────────────────────────────────────────────────
    print("\n[2] Generate test data")
    devices, uplinks = build_devices()
    check(f"Generated {len(devices)} devices", len(devices) == NUM_DEVICES)
    check(f"Generated {len(uplinks)} uplink relationships", len(uplinks) > 0)

    clients = build_clients(devices)
    check(f"Generated {len(clients)} clients", len(clients) == NUM_CLIENTS)

    contacts = build_contacts()
    check(f"Generated {len(contacts)} contacts", len(contacts) == NUM_CONTACTS)

    # ── 3. Download & verify CSV templates ──────────────────────────────
    print("\n[3] Verify CSV templates")

    # Device template (export empty)
    r = requests.get(f"{API}/maintenance-devices/{MAINTENANCE_ID}/export-csv",
                     headers=headers(token))
    check("Device export CSV endpoint works", r.status_code == 200)

    # Client template
    r = requests.get(f"{API}/mac-list/{MAINTENANCE_ID}/template-csv",
                     headers=headers(token))
    if r.status_code == 200:
        template_text = r.text
        check("Client template has correct columns",
              "mac_address" in template_text and "ip_address" in template_text
              and "tenant_group" in template_text and "description" in template_text)
    else:
        check("Client template download", False, f"status={r.status_code}")

    # ── 4. Import devices via CSV ───────────────────────────────────────
    print("\n[4] Import devices via CSV")
    device_csv = devices_to_csv(devices)
    result = upload_csv(token,
                        f"{API}/maintenance-devices/{MAINTENANCE_ID}/import-csv",
                        device_csv, "devices.csv")
    body = result["body"]
    if isinstance(body, dict):
        imported = body.get("imported", body.get("success_count", 0))
        total_errors = body.get("total_errors", len(body.get("errors", [])))
        check(f"Device import: {imported} imported",
              imported == NUM_DEVICES and total_errors == 0,
              f"imported={imported}, errors={total_errors}, body={str(body)[:300]}")
    else:
        check("Device import", False, f"status={result['status']} body={str(body)[:300]}")

    # ── 5. Import uplink expectations (topology) ────────────────────────
    print("\n[5] Import uplink expectations (topology)")
    uplink_csv = uplinks_to_csv(uplinks)
    result = upload_csv(token,
                        f"{API}/expectations/uplink/{MAINTENANCE_ID}/import-csv",
                        uplink_csv, "uplinks.csv")
    body = result["body"]
    if isinstance(body, dict):
        imported = body.get("imported", 0) + body.get("updated", 0)
        total_errors = body.get("total_errors", 0)
        check(f"Uplink import: {imported} imported",
              imported == len(uplinks) and total_errors == 0,
              f"imported={imported}, errors={total_errors}, body={str(body)[:300]}")
    else:
        check("Uplink import", False, f"status={result['status']} body={str(body)[:300]}")

    # ── 6. Import clients via CSV ───────────────────────────────────────
    print("\n[6] Import clients via CSV")
    client_csv = clients_to_csv(clients)
    result = upload_csv(token,
                        f"{API}/mac-list/{MAINTENANCE_ID}/import-csv",
                        client_csv, "clients.csv")
    body = result["body"]
    if isinstance(body, dict):
        imported = body.get("imported", 0)
        total_errors = body.get("total_errors", 0)
        check(f"Client import: {imported} imported",
              imported == NUM_CLIENTS and total_errors == 0,
              f"imported={imported}, errors={total_errors}, body={str(body)[:300]}")
    else:
        check("Client import", False, f"status={result['status']} body={str(body)[:300]}")

    # ── 7. Import contacts via CSV ──────────────────────────────────────
    print("\n[7] Import contacts via CSV")
    contact_csv = contacts_to_csv(contacts)
    result = upload_csv(token,
                        f"{API}/contacts/{MAINTENANCE_ID}/import-csv",
                        contact_csv, "contacts.csv")
    body = result["body"]
    if isinstance(body, dict):
        imported = body.get("contacts_imported", 0)
        cats_created = body.get("categories_created", 0)
        total_errors = body.get("total_errors", 0)
        check(f"Contact import: {imported} contacts, {cats_created} categories",
              imported == NUM_CONTACTS and total_errors == 0,
              f"imported={imported}, cats={cats_created}, errors={total_errors}, body={str(body)[:300]}")
    else:
        check("Contact import", False, f"status={result['status']} body={str(body)[:300]}")

    # ── 8. Verify imported data via API ─────────────────────────────────
    print("\n[8] Verify imported data")

    # Devices
    r = requests.get(f"{API}/maintenance-devices/{MAINTENANCE_ID}",
                     headers=headers(token))
    if r.status_code == 200:
        dev_data = r.json()
        dev_list = dev_data if isinstance(dev_data, list) else dev_data.get("devices", dev_data.get("items", []))
        check(f"Devices in DB: {len(dev_list)}",
              len(dev_list) == NUM_DEVICES,
              f"expected {NUM_DEVICES}, got {len(dev_list)}")
    else:
        check("Devices query", False, f"status={r.status_code}")

    # Uplink expectations
    r = requests.get(f"{API}/expectations/uplink/{MAINTENANCE_ID}",
                     headers=headers(token))
    if r.status_code == 200:
        uplink_data = r.json()
        uplink_list = uplink_data if isinstance(uplink_data, list) else uplink_data.get("items", [])
        check(f"Uplink expectations in DB: {len(uplink_list)}",
              len(uplink_list) == len(uplinks),
              f"expected {len(uplinks)}, got {len(uplink_list)}")
    else:
        check("Uplink expectations query", False, f"status={r.status_code}")

    # Clients (paginated — use stats endpoint for total count)
    r = requests.get(f"{API}/mac-list/{MAINTENANCE_ID}/stats",
                     headers=headers(token))
    if r.status_code == 200:
        stats = r.json()
        total = stats.get("total", 0)
        check(f"Clients in DB: {total}",
              total == NUM_CLIENTS,
              f"expected {NUM_CLIENTS}, got {total}")
    else:
        # Fallback: query with high limit
        r = requests.get(f"{API}/mac-list/{MAINTENANCE_ID}?limit=10000",
                         headers=headers(token))
        if r.status_code == 200:
            client_list = r.json()
            check(f"Clients in DB: {len(client_list)}",
                  len(client_list) == NUM_CLIENTS,
                  f"expected {NUM_CLIENTS}, got {len(client_list)}")
        else:
            check("Clients query", False, f"status={r.status_code}")

    # Contacts
    r = requests.get(f"{API}/contacts/{MAINTENANCE_ID}",
                     headers=headers(token))
    if r.status_code == 200:
        contact_data = r.json()
        contact_list = contact_data if isinstance(contact_data, list) else contact_data.get("items", contact_data.get("contacts", []))
        check(f"Contacts in DB: {len(contact_list)}",
              len(contact_list) == NUM_CONTACTS,
              f"expected {NUM_CONTACTS}, got {len(contact_list)}")
    else:
        check("Contacts query", False, f"status={r.status_code}")

    # Contact categories (with hierarchy)
    r = requests.get(f"{API}/contacts/categories/{MAINTENANCE_ID}",
                     headers=headers(token))
    if r.status_code == 200:
        cat_data = r.json()
        cat_list = cat_data if isinstance(cat_data, list) else cat_data.get("items", [])
        # Count parent and child categories
        parent_count = len(cat_list)
        child_count = sum(len(c.get("children", [])) for c in cat_list)
        check(f"Contact categories: {parent_count} parents, {child_count} subcategories",
              parent_count >= 5 and child_count >= 10,
              f"parents={parent_count}, children={child_count}")

        # Verify hierarchy - at least some categories should have children
        cats_with_children = [c for c in cat_list if len(c.get("children", [])) > 0]
        check(f"Categories with subcategories: {len(cats_with_children)}",
              len(cats_with_children) >= 4,
              f"expected >=4, got {len(cats_with_children)}")
    else:
        check("Contact categories query", False, f"status={r.status_code}")

    # ── 9. System functionality tests ───────────────────────────────────
    print("\n[9] System functionality tests")

    # Health check
    r = requests.get(f"{BASE_URL}/health")
    check("Health endpoint", r.status_code == 200)

    # Dashboard
    r = requests.get(f"{API}/dashboard/maintenance/{MAINTENANCE_ID}/summary",
                     headers=headers(token))
    check("Dashboard summary", r.status_code == 200,
          f"status={r.status_code}")

    # Topology
    r = requests.get(f"{API}/topology/{MAINTENANCE_ID}",
                     headers=headers(token))
    if r.status_code == 200:
        topo = r.json()
        nodes = topo.get("nodes", [])
        edges = topo.get("edges", topo.get("links", []))
        check(f"Topology: {len(nodes)} nodes, {len(edges)} edges",
              len(nodes) > 0,
              f"nodes={len(nodes)}, edges={len(edges)}")
    else:
        check("Topology endpoint", r.status_code == 200,
              f"status={r.status_code}")

    # Device export CSV round-trip
    r = requests.get(f"{API}/maintenance-devices/{MAINTENANCE_ID}/export-csv",
                     headers=headers(token))
    if r.status_code == 200:
        exported_lines = r.text.strip().split("\n")
        # First line is header
        check(f"Device CSV export: {len(exported_lines)-1} rows",
              len(exported_lines) - 1 == NUM_DEVICES,
              f"expected {NUM_DEVICES}, got {len(exported_lines)-1}")
    else:
        check("Device CSV export", False, f"status={r.status_code}")

    # Client export CSV round-trip
    r = requests.get(f"{API}/mac-list/{MAINTENANCE_ID}/export-csv",
                     headers=headers(token))
    if r.status_code == 200:
        exported_lines = r.text.strip().split("\n")
        check(f"Client CSV export: {len(exported_lines)-1} rows",
              len(exported_lines) - 1 == NUM_CLIENTS,
              f"expected {NUM_CLIENTS}, got {len(exported_lines)-1}")
    else:
        check("Client CSV export", False, f"status={r.status_code}")

    # Contact individual CRUD
    print("\n[10] Contact CRUD tests")

    # Create a contact via API
    r = requests.post(f"{API}/contacts/{MAINTENANCE_ID}",
                      headers=headers(token),
                      json={"name": "測試用聯絡人", "title": "測試工程師",
                            "department": "QA", "company": "Test Co",
                            "phone": "02-1234-5678", "mobile": "0912-345-678",
                            "extension": "9999", "notes": "API建立測試"})
    if r.status_code in (200, 201):
        contact_id = r.json().get("id")
        check("Create contact via API", contact_id is not None)

        # Update
        r2 = requests.put(f"{API}/contacts/{MAINTENANCE_ID}/{contact_id}",
                          headers=headers(token),
                          json={"title": "資深測試工程師"})
        check("Update contact", r2.status_code == 200)

        # Delete
        r3 = requests.delete(f"{API}/contacts/{MAINTENANCE_ID}/{contact_id}",
                             headers=headers(token))
        check("Delete contact", r3.status_code == 200)
    else:
        check("Create contact via API", False, f"status={r.status_code} body={r.text[:200]}")

    # ── 10. Cases auto-creation test ────────────────────────────────────
    print("\n[11] Cases & indicators")
    r = requests.get(f"{API}/cases/{MAINTENANCE_ID}",
                     headers=headers(token))
    check("Cases endpoint accessible", r.status_code == 200)

    r = requests.get(f"{API}/indicators",
                     headers=headers(token))
    check("Indicators endpoint accessible", r.status_code == 200,
          f"status={r.status_code}")

    # ── 11. Maintenance list ────────────────────────────────────────────
    print("\n[12] Maintenance operations")
    r = requests.get(f"{API}/maintenance", headers=headers(token))
    if r.status_code == 200:
        maint_list = r.json()
        found = any(m["id"] == MAINTENANCE_ID for m in maint_list)
        check(f"Maintenance {MAINTENANCE_ID} in list", found)
    else:
        check("Maintenance list", False, f"status={r.status_code}")

    # ── 12. Delete maintenance (cleanup) ────────────────────────────────
    print("\n[13] Cleanup - delete test maintenance")
    r = requests.delete(f"{API}/maintenance/{MAINTENANCE_ID}",
                        headers=headers(token))
    if r.status_code == 200:
        body = r.json()
        counts = body.get("deleted_counts", {})
        total = sum(counts.values())
        check(f"Maintenance deleted ({total} records cleaned)",
              "已刪除" in body.get("message", "") or "deleted" in body.get("message", "").lower(),
              f"body={str(body)[:300]}")
    else:
        check("Maintenance delete", False,
              f"status={r.status_code} body={r.text[:300]}")

    # Verify deletion
    r = requests.get(f"{API}/maintenance", headers=headers(token))
    if r.status_code == 200:
        remaining = [m for m in r.json() if m["id"] == MAINTENANCE_ID]
        check("Maintenance fully removed", len(remaining) == 0,
              f"still found {len(remaining)} entries")

    # ── Summary ─────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"  Results: {passed} passed, {failed} failed")
    print("=" * 70)
    if errors:
        print("\nFailures:")
        for e in errors:
            print(f"  ✗ {e}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
