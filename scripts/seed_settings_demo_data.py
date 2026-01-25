#!/usr/bin/env python3
"""
Seed demo data for Settings page (MAC list, Device mappings, Categories).

This script creates demo data for TEST-500 maintenance ID to demonstrate
the Settings page functionality including:
- Categories (機台分類)
- MAC List (MAC 清單)
- Device Mappings (設備對應)
"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import httpx


async def main():
    maintenance_id = "TEST-500"
    base_url = "http://localhost:8000/api/v1"

    async with httpx.AsyncClient() as client:
        print(f"🎯 Creating demo data for {maintenance_id}")
        print("=" * 60)

        # 1. Create Categories (機台分類)
        print("\n1️⃣  Creating Categories...")
        categories = [
            {"name": "伺服器", "color": "#3B82F6", "description": "Server machines"},
            {"name": "網路設備", "color": "#10B981", "description": "Network equipment"},
            {"name": "儲存設備", "color": "#F59E0B", "description": "Storage devices"},
            {"name": "測試機台", "color": "#8B5CF6", "description": "Test machines"},
            {"name": "辦公電腦", "color": "#EC4899", "description": "Office computers"},
        ]

        created_categories = []
        for cat in categories:
            try:
                response = await client.post(
                    f"{base_url}/categories",
                    json={
                        **cat,
                        "maintenance_id": maintenance_id,
                    }
                )
                if response.status_code == 200:
                    created = response.json()
                    created_categories.append(created)
                    print(f"   ✅ Created category: {cat['name']} (ID: {created['id']})")
                else:
                    print(f"   ⚠️  Failed to create {cat['name']}: {response.text}")
            except Exception as e:
                print(f"   ❌ Error creating {cat['name']}: {e}")

        # 2. Create MAC List (MAC 清單)
        print("\n2️⃣  Creating MAC List...")
        mac_addresses = [
            # 伺服器 (category 1)
            {"mac": "00:50:56:AA:11:01", "desc": "Web Server 1", "category_id": created_categories[0]["id"] if created_categories else None},
            {"mac": "00:50:56:AA:11:02", "desc": "Web Server 2", "category_id": created_categories[0]["id"] if created_categories else None},
            {"mac": "00:50:56:AA:11:03", "desc": "Database Server", "category_id": created_categories[0]["id"] if created_categories else None},

            # 網路設備 (category 2)
            {"mac": "00:1A:A0:BB:22:01", "desc": "Core Router", "category_id": created_categories[1]["id"] if len(created_categories) > 1 else None},
            {"mac": "00:1A:A0:BB:22:02", "desc": "Distribution Switch", "category_id": created_categories[1]["id"] if len(created_categories) > 1 else None},

            # 儲存設備 (category 3)
            {"mac": "00:25:90:CC:33:01", "desc": "NAS Primary", "category_id": created_categories[2]["id"] if len(created_categories) > 2 else None},
            {"mac": "00:25:90:CC:33:02", "desc": "NAS Backup", "category_id": created_categories[2]["id"] if len(created_categories) > 2 else None},

            # 測試機台 (category 4)
            {"mac": "00:0C:29:DD:44:01", "desc": "Test VM 1", "category_id": created_categories[3]["id"] if len(created_categories) > 3 else None},
            {"mac": "00:0C:29:DD:44:02", "desc": "Test VM 2", "category_id": created_categories[3]["id"] if len(created_categories) > 3 else None},
            {"mac": "00:0C:29:DD:44:03", "desc": "Test VM 3", "category_id": created_categories[3]["id"] if len(created_categories) > 3 else None},

            # 辦公電腦 (category 5)
            {"mac": "A8:5E:45:EE:55:01", "desc": "Workstation 01", "category_id": created_categories[4]["id"] if len(created_categories) > 4 else None},
            {"mac": "A8:5E:45:EE:55:02", "desc": "Workstation 02", "category_id": created_categories[4]["id"] if len(created_categories) > 4 else None},
            {"mac": "A8:5E:45:EE:55:03", "desc": "Workstation 03", "category_id": created_categories[4]["id"] if len(created_categories) > 4 else None},

            # 未分類
            {"mac": "AA:BB:CC:DD:EE:01", "desc": "Unknown Device 1", "category_id": None},
            {"mac": "AA:BB:CC:DD:EE:02", "desc": "Unknown Device 2", "category_id": None},
        ]

        for mac_data in mac_addresses:
            try:
                response = await client.post(
                    f"{base_url}/mac-list/{maintenance_id}",
                    json={
                        "mac_address": mac_data["mac"],
                        "description": mac_data["desc"],
                    }
                )
                if response.status_code == 200:
                    created_mac = response.json()
                    print(f"   ✅ Added MAC: {mac_data['mac']} ({mac_data['desc']})")

                    # 如果有分類，將 MAC 加入分類
                    if mac_data["category_id"]:
                        try:
                            await client.post(
                                f"{base_url}/categories/{mac_data['category_id']}/members",
                                json={"mac_address": mac_data["mac"]}
                            )
                        except Exception as e:
                            print(f"      ⚠️  Failed to assign category: {e}")
                else:
                    print(f"   ⚠️  Failed to add {mac_data['mac']}: {response.text}")
            except Exception as e:
                print(f"   ❌ Error adding {mac_data['mac']}: {e}")

        # 3. Create Device Mappings (設備對應)
        print("\n3️⃣  Creating Device Mappings...")
        device_mappings = [
            {
                "old_hostname": "old-sw-01",
                "new_hostname": "switch-new-01",
                "vendor": "Cisco-NXOS",
                "use_same_port": True,
            },
            {
                "old_hostname": "old-sw-02",
                "new_hostname": "switch-new-02",
                "vendor": "HPE",
                "use_same_port": True,
            },
            {
                "old_hostname": "old-router-01",
                "new_hostname": "new-router-01",
                "vendor": "Cisco-IOS",
                "use_same_port": False,
            },
        ]

        for mapping in device_mappings:
            try:
                payload = {
                    "maintenance_id": maintenance_id,
                    **mapping,
                }
                response = await client.post(
                    f"{base_url}/device-mappings/{maintenance_id}",
                    json=payload
                )
                if response.status_code == 200:
                    print(f"   ✅ Added mapping: {mapping['old_hostname']} → {mapping['new_hostname']}")
                else:
                    print(f"   ⚠️  Failed to add mapping: {response.text}")
            except Exception as e:
                print(f"   ❌ Error adding mapping: {e}")

        # 4. Summary
        print("\n" + "=" * 60)
        print("✅ Demo data creation complete!")
        print("\n📊 Summary:")
        print(f"   - Categories: {len(created_categories)}")
        print(f"   - MAC Addresses: {len(mac_addresses)}")
        print(f"   - Device Mappings: {len(device_mappings)}")
        print("\n🌐 Visit Settings page at: http://localhost:3000/settings")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
