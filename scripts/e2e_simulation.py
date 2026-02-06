#!/usr/bin/env python3
"""
端到端模擬測試腳本

模擬真實用戶從空資料庫開始的完整使用流程：
1. 建立歲修 ID
2. 匯入 Client MAC 清單
3. 匯入設備對應清單
4. 設定期望值（Uplink、版本、ARP 來源）
5. 建立分類
6. 啟動 Scheduler（使用 Mock Fetcher）
7. 執行客戶端偵測
8. 驗證資料收集結果
"""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# =============================================================================
# 配置
# =============================================================================
BASE_URL = "http://localhost:8000/api/v1"
MAINTENANCE_ID = "E2E-TEST-001"

# 測試資料
TEST_MAC_LIST = [
    {"mac_address": "AA:BB:CC:DD:EE:01", "ip_address": "10.1.1.101", "tenant_group": "F18", "description": "設備A"},
    {"mac_address": "AA:BB:CC:DD:EE:02", "ip_address": "10.1.1.102", "tenant_group": "F18", "description": "設備B"},
    {"mac_address": "AA:BB:CC:DD:EE:03", "ip_address": "10.1.1.103", "tenant_group": "F6", "description": "設備C"},
    {"mac_address": "AA:BB:CC:DD:EE:04", "ip_address": "10.1.1.104", "tenant_group": "F6", "description": "設備D"},
    {"mac_address": "AA:BB:CC:DD:EE:05", "ip_address": "10.1.1.105", "tenant_group": "AP", "description": "設備E"},
    {"mac_address": "AA:BB:CC:DD:EE:06", "ip_address": "10.1.1.106", "tenant_group": "AP", "description": "設備F"},
    {"mac_address": "AA:BB:CC:DD:EE:07", "ip_address": "10.1.1.107", "tenant_group": "F14", "description": "設備G"},
    {"mac_address": "AA:BB:CC:DD:EE:08", "ip_address": "10.1.1.108", "tenant_group": "F14", "description": "設備H"},
    {"mac_address": "AA:BB:CC:DD:EE:09", "ip_address": "10.1.1.109", "tenant_group": "F12", "description": "設備I"},
    {"mac_address": "AA:BB:CC:DD:EE:10", "ip_address": "10.1.1.110", "tenant_group": "F12", "description": "設備J"},
]

TEST_DEVICES = [
    {
        "old_hostname": "OLD-SW-001",
        "old_ip_address": "10.1.1.1",
        "old_vendor": "HPE",
        "new_hostname": "NEW-SW-001",
        "new_ip_address": "10.1.1.11",
        "new_vendor": "HPE",
        "use_same_port": True,
        "tenant_group": "F18",
        "description": "核心交換機 1",
    },
    {
        "old_hostname": "OLD-SW-002",
        "old_ip_address": "10.1.1.2",
        "old_vendor": "Cisco-IOS",
        "new_hostname": "NEW-SW-002",
        "new_ip_address": "10.1.1.12",
        "new_vendor": "Cisco-IOS",
        "use_same_port": True,
        "tenant_group": "F6",
        "description": "接入交換機 1",
    },
    {
        "old_hostname": "OLD-SW-003",
        "old_ip_address": "10.1.1.3",
        "old_vendor": "Cisco-NXOS",
        "new_hostname": "NEW-SW-003",
        "new_ip_address": "10.1.1.13",
        "new_vendor": "Cisco-NXOS",
        "use_same_port": False,
        "tenant_group": "AP",
        "description": "資料中心交換機",
    },
]

TEST_UPLINK_EXPECTATIONS = [
    {
        "hostname": "NEW-SW-001",
        "local_interface": "GE1/0/1",
        "expected_neighbor": "NEW-SW-002",
        "expected_interface": "GE1/0/48",
    },
    {
        "hostname": "NEW-SW-002",
        "local_interface": "GE1/0/48",
        "expected_neighbor": "NEW-SW-001",
        "expected_interface": "GE1/0/1",
    },
]

TEST_VERSION_EXPECTATIONS = [
    {"hostname": "NEW-SW-001", "expected_versions": "16.12.4"},
    {"hostname": "NEW-SW-002", "expected_versions": "17.3.2"},
    {"hostname": "NEW-SW-003", "expected_versions": "9.3(8)"},
]

TEST_ARP_SOURCES = [
    {"hostname": "NEW-SW-001", "ip_address": "10.1.1.11", "priority": 1},
    {"hostname": "NEW-SW-002", "ip_address": "10.1.1.12", "priority": 2},
]


class E2ESimulation:
    """端到端模擬測試類別"""

    def __init__(self, base_url: str, maintenance_id: str):
        self.base_url = base_url
        self.maintenance_id = maintenance_id
        self.client = httpx.AsyncClient(timeout=30.0)
        self.results: dict[str, Any] = {}
        self.auth_token: str | None = None

    def _get_headers(self) -> dict[str, str]:
        """取得含認證的 HTTP headers"""
        if self.auth_token:
            return {"Authorization": f"Bearer {self.auth_token}"}
        return {}

    async def close(self):
        await self.client.aclose()

    def print_step(self, step_num: int, title: str):
        print(f"\n{'=' * 60}")
        print(f"Step {step_num}: {title}")
        print(f"{'=' * 60}")

    def print_result(self, success: bool, message: str):
        status = "✓" if success else "✗"
        print(f"   {status} {message}")

    async def check_server_health(self) -> bool:
        """檢查伺服器是否運行"""
        print("\n檢查伺服器狀態...")
        try:
            resp = await self.client.get(
                f"{self.base_url.replace('/api/v1', '')}/health"
            )
            if resp.status_code == 200:
                self.print_result(True, "伺服器運行正常")
                return True
        except httpx.ConnectError:
            pass
        self.print_result(False, "無法連接到伺服器，請先啟動後端服務")
        return False

    async def login(self) -> bool:
        """登入取得 token"""
        print("\n登入中...")
        try:
            resp = await self.client.post(
                f"{self.base_url}/auth/login",
                json={"username": "root", "password": "root123"}
            )
            if resp.status_code == 200:
                data = resp.json()
                self.auth_token = data.get("token")
                self.print_result(True, f"登入成功: {data.get('user', {}).get('username')}")
                return True
            else:
                self.print_result(False, f"登入失敗: {resp.text}")
                return False
        except Exception as e:
            self.print_result(False, f"登入錯誤: {e}")
            return False

    # =========================================================================
    # Step 1: 建立歲修 ID
    # =========================================================================
    async def step1_create_maintenance(self) -> bool:
        """建立歲修 ID"""
        self.print_step(1, "建立歲修 ID")

        headers = self._get_headers()

        # 先檢查是否已存在，如果存在則刪除
        resp = await self.client.get(f"{self.base_url}/maintenance", headers=headers)
        if resp.status_code == 200:
            existing = resp.json()
            for m in existing:
                if m.get("id") == self.maintenance_id:
                    print(f"   發現已存在的歲修 ID: {self.maintenance_id}，刪除中...")
                    del_resp = await self.client.delete(
                        f"{self.base_url}/maintenance/{self.maintenance_id}",
                        headers=headers
                    )
                    if del_resp.status_code == 200:
                        self.print_result(True, "已刪除舊的歲修資料")
                    else:
                        self.print_result(False, f"刪除失敗: {del_resp.text}")

        # 建立新的歲修 ID
        resp = await self.client.post(
            f"{self.base_url}/maintenance",
            json={"id": self.maintenance_id},
            headers=headers
        )

        if resp.status_code == 200:
            self.print_result(True, f"歲修 ID '{self.maintenance_id}' 建立成功")
            self.results["maintenance"] = resp.json()
            return True
        else:
            self.print_result(False, f"建立失敗: {resp.text}")
            return False

    # =========================================================================
    # Step 2: 匯入 Client MAC 清單
    # =========================================================================
    async def step2_import_mac_list(self) -> bool:
        """匯入 MAC 清單"""
        self.print_step(2, "匯入 Client MAC 清單")

        success_count = 0
        for mac_entry in TEST_MAC_LIST:
            resp = await self.client.post(
                f"{self.base_url}/mac-list/{self.maintenance_id}",
                json=mac_entry
            )
            if resp.status_code == 200:
                success_count += 1
            else:
                self.print_result(False, f"匯入 {mac_entry['mac_address']} 失敗: {resp.text}")

        self.print_result(
            success_count == len(TEST_MAC_LIST),
            f"成功匯入 {success_count}/{len(TEST_MAC_LIST)} 筆 MAC 清單"
        )

        # 驗證統計
        resp = await self.client.get(f"{self.base_url}/mac-list/{self.maintenance_id}/stats")
        if resp.status_code == 200:
            stats = resp.json()
            self.print_result(True, f"MAC 統計: 總數={stats.get('total', 0)}")
            self.results["mac_stats"] = stats

        return success_count > 0

    # =========================================================================
    # Step 3: 匯入設備對應清單
    # =========================================================================
    async def step3_import_devices(self) -> bool:
        """匯入設備對應清單"""
        self.print_step(3, "匯入設備對應清單")

        headers = self._get_headers()
        success_count = 0
        for device in TEST_DEVICES:
            resp = await self.client.post(
                f"{self.base_url}/maintenance-devices/{self.maintenance_id}",
                json=device,
                headers=headers
            )
            if resp.status_code == 200:
                success_count += 1
            else:
                self.print_result(False, f"匯入 {device['old_hostname']} 失敗: {resp.text}")

        self.print_result(
            success_count == len(TEST_DEVICES),
            f"成功匯入 {success_count}/{len(TEST_DEVICES)} 筆設備對應"
        )

        # 驗證統計
        resp = await self.client.get(
            f"{self.base_url}/maintenance-devices/{self.maintenance_id}/stats",
            headers=headers
        )
        if resp.status_code == 200:
            stats = resp.json()
            self.print_result(True, f"設備統計: 總數={stats.get('total', 0)}")
            self.results["device_stats"] = stats

        return success_count > 0

    # =========================================================================
    # Step 4: 設定期望值
    # =========================================================================
    async def step4_setup_expectations(self) -> bool:
        """設定期望值"""
        self.print_step(4, "設定期望值")

        headers = self._get_headers()

        # 4.1 Uplink 期望
        print("\n   4.1 Uplink 期望:")
        uplink_count = 0
        for exp in TEST_UPLINK_EXPECTATIONS:
            resp = await self.client.post(
                f"{self.base_url}/expectations/uplink/{self.maintenance_id}",
                json=exp,
                headers=headers
            )
            if resp.status_code == 200:
                uplink_count += 1
            else:
                self.print_result(False, f"Uplink 期望設定失敗: {resp.text}")
        self.print_result(uplink_count > 0, f"成功設定 {uplink_count} 筆 Uplink 期望")

        # 4.2 版本期望
        print("\n   4.2 版本期望:")
        version_count = 0
        for exp in TEST_VERSION_EXPECTATIONS:
            resp = await self.client.post(
                f"{self.base_url}/expectations/version/{self.maintenance_id}",
                json=exp,
                headers=headers
            )
            if resp.status_code == 200:
                version_count += 1
            else:
                self.print_result(False, f"版本期望設定失敗: {resp.text}")
        self.print_result(version_count > 0, f"成功設定 {version_count} 筆版本期望")

        # 4.3 ARP 來源設備
        print("\n   4.3 ARP 來源設備:")
        arp_count = 0
        for exp in TEST_ARP_SOURCES:
            resp = await self.client.post(
                f"{self.base_url}/expectations/arp/{self.maintenance_id}",
                json=exp,
                headers=headers
            )
            if resp.status_code == 200:
                arp_count += 1
            else:
                self.print_result(False, f"ARP 來源設定失敗: {resp.text}")
        self.print_result(arp_count > 0, f"成功設定 {arp_count} 筆 ARP 來源")

        self.results["expectations"] = {
            "uplink": uplink_count,
            "version": version_count,
            "arp": arp_count,
        }

        return uplink_count > 0 or version_count > 0 or arp_count > 0

    # =========================================================================
    # Step 5: 建立分類
    # =========================================================================
    async def step5_create_categories(self) -> bool:
        """建立分類"""
        self.print_step(5, "建立 Client 分類")

        categories_to_create = [
            {"name": "關鍵設備", "description": "重要生產設備", "color": "#FF0000", "maintenance_id": self.maintenance_id},
            {"name": "一般設備", "description": "一般用途設備", "color": "#00FF00", "maintenance_id": self.maintenance_id},
        ]

        created_categories = []
        for cat in categories_to_create:
            resp = await self.client.post(
                f"{self.base_url}/categories",
                json=cat
            )
            if resp.status_code == 200:
                created_categories.append(resp.json())
                self.print_result(True, f"建立分類: {cat['name']}")
            else:
                self.print_result(False, f"建立分類失敗: {resp.text}")

        # 將部分 MAC 加入分類
        if created_categories:
            cat_id = created_categories[0].get("id")
            if cat_id:
                # 加入前 3 個 MAC 到「關鍵設備」分類
                macs_to_add = [m["mac_address"] for m in TEST_MAC_LIST[:3]]
                resp = await self.client.post(
                    f"{self.base_url}/categories/{cat_id}/members",
                    json={"mac_addresses": macs_to_add}
                )
                if resp.status_code == 200:
                    self.print_result(True, f"已將 {len(macs_to_add)} 個 MAC 加入「關鍵設備」分類")

        self.results["categories"] = len(created_categories)
        return len(created_categories) > 0

    # =========================================================================
    # Step 6: 啟動 Mock 資料生成
    # =========================================================================
    async def step6_generate_mock_data(self) -> bool:
        """生成 Mock 資料（模擬 Scheduler 執行）"""
        self.print_step(6, "生成 Mock 資料")

        print("   直接透過服務層生成 Mock 資料...")

        # 使用 Python 直接呼叫服務層
        from app.db.base import get_session_context
        from app.services.mock_data_generator import get_mock_data_generator
        from app.core.enums import MaintenancePhase

        generator = get_mock_data_generator()
        records_generated = 0

        try:
            # 生成 3 批次資料，模擬時間序列
            for batch in range(3):
                async with get_session_context() as session:
                    # 取得前一批次的記錄作為基準
                    from sqlalchemy import select, func
                    from app.db.models import ClientRecord

                    subquery = (
                        select(func.max(ClientRecord.collected_at))
                        .where(
                            ClientRecord.maintenance_id == self.maintenance_id,
                            ClientRecord.phase == MaintenancePhase.NEW,
                        )
                        .scalar_subquery()
                    )

                    stmt = select(ClientRecord).where(
                        ClientRecord.maintenance_id == self.maintenance_id,
                        ClientRecord.phase == MaintenancePhase.NEW,
                        ClientRecord.collected_at == subquery,
                    )
                    result = await session.execute(stmt)
                    base_records = list(result.scalars().all())

                    # 生成新記錄
                    new_records = await generator.generate_client_records(
                        maintenance_id=self.maintenance_id,
                        phase=MaintenancePhase.NEW,
                        session=session,
                        base_records=base_records if base_records else None,
                    )

                    for record in new_records:
                        session.add(record)
                    await session.commit()

                    records_generated += len(new_records)
                    self.print_result(True, f"批次 {batch + 1}: 生成 {len(new_records)} 筆 ClientRecord")

                # 間隔一小段時間，讓時間戳不同
                await asyncio.sleep(0.5)

            self.results["mock_records"] = records_generated
            self.print_result(True, f"總共生成 {records_generated} 筆 Mock 資料")
            return True

        except Exception as e:
            self.print_result(False, f"Mock 資料生成失敗: {e}")
            import traceback
            traceback.print_exc()
            return False

    # =========================================================================
    # Step 7: 執行客戶端偵測
    # =========================================================================
    async def step7_detect_clients(self) -> bool:
        """執行客戶端偵測"""
        self.print_step(7, "執行客戶端偵測")

        # 等待資料庫同步
        await asyncio.sleep(1)

        print("   觸發客戶端偵測（POST /mac-list/{id}/detect）...")

        headers = self._get_headers()
        resp = await self.client.post(
            f"{self.base_url}/mac-list/{self.maintenance_id}/detect",
            headers=headers,
            timeout=120.0  # 偵測可能需要較長時間
        )

        if resp.status_code == 200:
            result = resp.json()
            self.print_result(True, f"偵測完成")
            self.print_result(True, f"  - 已偵測: {result.get('detected', 0)}")
            self.print_result(True, f"  - 不匹配: {result.get('mismatch', 0)}")
            self.print_result(True, f"  - 未偵測: {result.get('not_detected', 0)}")
            self.results["detection"] = result
            return True
        else:
            self.print_result(False, f"偵測失敗: {resp.text}")
            return False

    # =========================================================================
    # Step 8: 驗證統計與比較結果
    # =========================================================================
    async def step8_verify_results(self) -> bool:
        """驗證統計與比較結果"""
        self.print_step(8, "驗證統計與比較結果")

        all_checks_passed = True

        # 8.1 驗證 MAC 統計
        print("\n   8.1 MAC 清單統計:")
        resp = await self.client.get(f"{self.base_url}/mac-list/{self.maintenance_id}/stats")
        if resp.status_code == 200:
            stats = resp.json()
            self.print_result(True, f"總數: {stats.get('total', 0)}")
            self.print_result(True, f"已分類: {stats.get('categorized', 0)}")
            self.print_result(True, f"偵測狀態分佈: {stats.get('detection_status', {})}")
        else:
            self.print_result(False, f"取得統計失敗: {resp.text}")
            all_checks_passed = False

        # 8.2 驗證 Checkpoint
        print("\n   8.2 Checkpoint 查詢:")
        resp = await self.client.get(
            f"{self.base_url}/comparisons/checkpoints/{self.maintenance_id}"
        )
        if resp.status_code == 200:
            data = resp.json()
            checkpoints = data.get("checkpoints", [])
            self.print_result(True, f"可用 Checkpoint 數量: {len(checkpoints)}")
            if checkpoints:
                latest = checkpoints[-1]
                self.print_result(True, f"最新: {latest.get('label', 'N/A')}")
        else:
            self.print_result(False, f"取得 Checkpoint 失敗: {resp.text}")

        # 8.3 驗證比較摘要
        print("\n   8.3 比較摘要:")
        resp = await self.client.get(
            f"{self.base_url}/comparisons/summary/{self.maintenance_id}"
        )
        if resp.status_code == 200:
            data = resp.json()
            self.print_result(True, f"總數: {data.get('total', 0)}")
            self.print_result(True, f"有問題: {data.get('has_issues', 0)}")
        else:
            self.print_result(False, f"取得摘要失敗: {resp.text}")

        # 8.4 驗證分類統計
        print("\n   8.4 分類統計:")
        resp = await self.client.get(
            f"{self.base_url}/categories/stats/{self.maintenance_id}"
        )
        if resp.status_code == 200:
            stats = resp.json()
            self.print_result(True, f"分類統計: {stats}")
        else:
            self.print_result(False, f"取得分類統計失敗: {resp.text}")

        return all_checks_passed

    # =========================================================================
    # 主流程
    # =========================================================================
    async def run(self) -> int:
        """執行完整的端到端模擬"""
        print("\n" + "=" * 60)
        print("端到端模擬測試")
        print(f"歲修 ID: {self.maintenance_id}")
        print(f"時間: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("=" * 60)

        # 檢查伺服器
        if not await self.check_server_health():
            print("\n請先啟動後端服務: cd network_dashboard && python -m app.main")
            return 1

        # 登入
        if not await self.login():
            print("\n登入失敗，請確認使用者帳號密碼")
            return 1

        steps = [
            ("建立歲修 ID", self.step1_create_maintenance),
            ("匯入 MAC 清單", self.step2_import_mac_list),
            ("匯入設備對應", self.step3_import_devices),
            ("設定期望值", self.step4_setup_expectations),
            ("建立分類", self.step5_create_categories),
            ("生成 Mock 資料", self.step6_generate_mock_data),
            ("執行客戶端偵測", self.step7_detect_clients),
            ("驗證結果", self.step8_verify_results),
        ]

        passed = 0
        failed = 0

        for name, step_func in steps:
            try:
                result = await step_func()
                if result:
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                print(f"\n   [ERROR] {name} 執行失敗: {e}")
                import traceback
                traceback.print_exc()
                failed += 1

        # 最終報告
        print("\n" + "=" * 60)
        print("測試結果摘要")
        print("=" * 60)
        print(f"   通過: {passed}/{len(steps)}")
        print(f"   失敗: {failed}/{len(steps)}")

        if self.results:
            print("\n   詳細結果:")
            for key, value in self.results.items():
                print(f"   - {key}: {value}")

        print("=" * 60)

        return 0 if failed == 0 else 1


async def main():
    """主函式"""
    import argparse

    parser = argparse.ArgumentParser(description="端到端模擬測試")
    parser.add_argument(
        "--maintenance-id",
        default=MAINTENANCE_ID,
        help=f"歲修 ID (預設: {MAINTENANCE_ID})",
    )
    parser.add_argument(
        "--base-url",
        default=BASE_URL,
        help=f"API 基礎 URL (預設: {BASE_URL})",
    )

    args = parser.parse_args()

    simulation = E2ESimulation(
        base_url=args.base_url,
        maintenance_id=args.maintenance_id,
    )

    try:
        exit_code = await simulation.run()
    finally:
        await simulation.close()

    return exit_code


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
