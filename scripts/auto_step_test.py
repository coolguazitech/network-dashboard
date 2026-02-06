#!/usr/bin/env python3
"""
自動化分步驟測試腳本（非互動式）

自動執行所有測試步驟，無需用戶輸入。
"""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
import json

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

# =============================================================================
# 配置
# =============================================================================
BASE_URL = "http://localhost:8000/api/v1"
MAINTENANCE_ID = "STEP-TEST-001"

# 認證配置
AUTH_USERNAME = "root"
AUTH_PASSWORD = "root123"


def print_header(step: int, title: str):
    """打印步驟標題"""
    print(f"\n{'=' * 70}")
    print(f"【Step {step}】{title}")
    print(f"{'=' * 70}")


def print_json(data, indent: int = 2):
    """格式化打印 JSON"""
    print(json.dumps(data, indent=indent, ensure_ascii=False, default=str))


class AutoStepTest:
    def __init__(self):
        self.client = httpx.Client(timeout=30.0)
        self.maintenance_id = MAINTENANCE_ID
        self.token = None

    def close(self):
        self.client.close()

    def get_auth_headers(self):
        """取得認證 headers"""
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

    def login(self) -> bool:
        """登入取得 token"""
        print("\n登入中...")
        try:
            resp = self.client.post(
                f"{BASE_URL}/auth/login",
                json={"username": AUTH_USERNAME, "password": AUTH_PASSWORD}
            )
            if resp.status_code == 200:
                data = resp.json()
                self.token = data.get("token")
                print("✓ 登入成功，取得 token")
                return True
            else:
                print(f"✗ 登入失敗: {resp.text}")
                return False
        except Exception as e:
            print(f"✗ 登入錯誤: {e}")
            return False

    def check_server(self) -> bool:
        """檢查伺服器是否運行"""
        print("\n檢查伺服器狀態...")
        try:
            resp = self.client.get(BASE_URL.replace('/api/v1', '') + '/health')
            if resp.status_code == 200:
                print("✓ 伺服器運行正常")
                return True
        except httpx.ConnectError:
            pass
        print("✗ 無法連接到伺服器")
        return False

    # =========================================================================
    # Step 1: 建立歲修
    # =========================================================================
    def step1_create_maintenance(self):
        """建立歲修"""
        print_header(1, f"建立歲修 ID: {self.maintenance_id}")

        # 先檢查是否存在
        resp = self.client.get(
            f"{BASE_URL}/maintenance",
            headers=self.get_auth_headers()
        )

        if resp.status_code == 200:
            maintenances = resp.json()
            found = any(m.get("maintenance_id") == self.maintenance_id for m in maintenances)
            if found:
                print(f"✓ 歲修 ID '{self.maintenance_id}' 已存在，跳過建立")
                return True

        # 建立歲修
        print(f"\n建立新歲修: {self.maintenance_id}")
        resp = self.client.post(
            f"{BASE_URL}/maintenance",
            json={"id": self.maintenance_id, "name": self.maintenance_id},
            headers=self.get_auth_headers()
        )

        if resp.status_code == 200:
            print(f"✓ 歲修 ID '{self.maintenance_id}' 建立成功")
            print_json(resp.json())
            return True
        else:
            print(f"✗ 建立失敗: {resp.text}")
            return False

    # =========================================================================
    # Step 2: 匯入 MAC 清單
    # =========================================================================
    def step2_import_mac_list(self):
        """匯入 MAC 清單"""
        print_header(2, "匯入 Client MAC 清單")

        test_macs = [
            {"mac_address": "AA:BB:CC:DD:EE:01", "ip_address": "10.1.1.101", "tenant_group": "F18", "description": "EQP 設備 1"},
            {"mac_address": "AA:BB:CC:DD:EE:02", "ip_address": "10.1.1.102", "tenant_group": "F18", "description": "EQP 設備 2"},
            {"mac_address": "AA:BB:CC:DD:EE:03", "ip_address": "10.1.1.103", "tenant_group": "F6", "description": "AMHS 設備 1"},
            {"mac_address": "AA:BB:CC:DD:EE:04", "ip_address": "10.1.1.104", "tenant_group": "F6", "description": "AMHS 設備 2"},
            {"mac_address": "AA:BB:CC:DD:EE:05", "ip_address": "10.1.1.105", "tenant_group": "AP", "description": "SNR 設備 1"},
        ]

        print("\n匯入以下 MAC 清單:")
        for mac in test_macs:
            print(f"  - {mac['mac_address']} / {mac['ip_address']} ({mac['tenant_group']})")

        success_count = 0
        for mac in test_macs:
            resp = self.client.post(
                f"{BASE_URL}/mac-list/{self.maintenance_id}",
                json=mac,
                headers=self.get_auth_headers()
            )
            if resp.status_code == 200:
                success_count += 1
                print(f"  ✓ {mac['mac_address']} 匯入成功")
            else:
                print(f"  ✗ {mac['mac_address']} 匯入失敗: {resp.text}")

        print(f"\n結果: {success_count}/{len(test_macs)} 筆成功")

        # 查看統計
        print("\n查看 MAC 統計:")
        resp = self.client.get(
            f"{BASE_URL}/mac-list/{self.maintenance_id}/stats",
            headers=self.get_auth_headers()
        )
        if resp.status_code == 200:
            print_json(resp.json())

    # =========================================================================
    # Step 3: 匯入設備對應
    # =========================================================================
    def step3_import_devices(self):
        """匯入設備對應清單"""
        print_header(3, "匯入設備對應清單")

        test_devices = [
            {
                "old_hostname": "OLD-SW-001", "old_ip_address": "10.1.1.1", "old_vendor": "HPE",
                "new_hostname": "NEW-SW-001", "new_ip_address": "10.1.1.11", "new_vendor": "HPE",
                "use_same_port": True, "tenant_group": "F18", "description": "核心交換機",
            },
            {
                "old_hostname": "OLD-SW-002", "old_ip_address": "10.1.1.2", "old_vendor": "Cisco-IOS",
                "new_hostname": "NEW-SW-002", "new_ip_address": "10.1.1.12", "new_vendor": "Cisco-IOS",
                "use_same_port": True, "tenant_group": "F6", "description": "接入交換機",
            },
        ]

        print("\n匯入以下設備對應:")
        for dev in test_devices:
            print(f"  - {dev['old_hostname']} → {dev['new_hostname']}")

        for dev in test_devices:
            resp = self.client.post(
                f"{BASE_URL}/maintenance-devices/{self.maintenance_id}",
                json=dev,
                headers=self.get_auth_headers()
            )
            if resp.status_code == 200:
                print(f"  ✓ {dev['old_hostname']} → {dev['new_hostname']} 匯入成功")
            else:
                print(f"  ✗ 匯入失敗: {resp.text}")

        # 查看統計
        print("\n查看設備統計:")
        resp = self.client.get(
            f"{BASE_URL}/maintenance-devices/{self.maintenance_id}/stats",
            headers=self.get_auth_headers()
        )
        if resp.status_code == 200:
            print_json(resp.json())

    # =========================================================================
    # Step 4: 設定期望值
    # =========================================================================
    def step4_setup_expectations(self):
        """設定期望值"""
        print_header(4, "設定期望值")

        # 4.1 版本期望
        print("\n4.1 設定版本期望")
        version_expectations = [
            {"hostname": "NEW-SW-001", "expected_version": "16.12.4"},
            {"hostname": "NEW-SW-002", "expected_version": "17.3.2"},
        ]

        print("\n設定以下版本期望:")
        for exp in version_expectations:
            print(f"  - {exp['hostname']}: {exp['expected_version']}")

        for exp in version_expectations:
            resp = self.client.post(
                f"{BASE_URL}/expectations/version/{self.maintenance_id}",
                json=exp,
                headers=self.get_auth_headers()
            )
            if resp.status_code == 200:
                print(f"  ✓ {exp['hostname']} 版本期望設定成功")
            else:
                print(f"  ✗ 設定失敗: {resp.text}")

        # 4.2 ARP 來源設備
        print("\n4.2 設定 ARP 來源設備")
        arp_sources = [
            {"hostname": "NEW-SW-001", "ip_address": "10.1.1.11", "priority": 1},
        ]

        print("\n設定以下 ARP 來源:")
        for src in arp_sources:
            print(f"  - {src['hostname']} ({src['ip_address']}) 優先級: {src['priority']}")

        for src in arp_sources:
            resp = self.client.post(
                f"{BASE_URL}/expectations/arp/{self.maintenance_id}",
                json=src,
                headers=self.get_auth_headers()
            )
            if resp.status_code == 200:
                print(f"  ✓ ARP 來源設定成功")
            else:
                print(f"  ✗ 設定失敗: {resp.text}")

    # =========================================================================
    # Step 5: 生成 Mock 資料
    # =========================================================================
    def step5_generate_mock_data(self):
        """生成 Mock 資料"""
        print_header(5, "生成 Mock 資料（模擬 Scheduler）")

        print("\n生成 3 批次資料，每批次間隔 1 秒")

        async def generate():
            from app.db.base import get_session_context
            from app.services.mock_data_generator import get_mock_data_generator
            from app.core.enums import MaintenancePhase
            from sqlalchemy import select, func
            from app.db.models import ClientRecord

            generator = get_mock_data_generator()

            for batch in range(3):
                print(f"\n生成批次 {batch + 1}/3...")

                async with get_session_context() as session:
                    # 取得前一批次的記錄
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

                    print(f"  ✓ 批次 {batch + 1}: 生成 {len(new_records)} 筆記錄")

                    if new_records:
                        sample = new_records[0]
                        print(f"    範例: MAC={sample.mac_address}, IP={sample.ip_address}")
                        print(f"           Switch={sample.switch_hostname}, Port={sample.interface_name}")
                        print(f"           Link={sample.link_status}, Ping={sample.ping_reachable}")

                await asyncio.sleep(1)

        asyncio.run(generate())
        print("\n✓ Mock 資料生成完成")

    # =========================================================================
    # Step 6: 執行客戶端偵測
    # =========================================================================
    def step6_detect_clients(self):
        """執行客戶端偵測"""
        print_header(6, "執行客戶端偵測")

        print("\n執行偵測中...")
        resp = self.client.post(
            f"{BASE_URL}/mac-list/{self.maintenance_id}/detect",
            headers=self.get_auth_headers(),
            timeout=60.0
        )

        if resp.status_code == 200:
            result = resp.json()
            print("\n✓ 偵測完成")
            print("\n偵測結果:")
            print_json(result)
        else:
            print(f"\n✗ 偵測失敗: {resp.text}")

        # 查看更新後的統計
        print("\n查看更新後的 MAC 統計:")
        resp = self.client.get(
            f"{BASE_URL}/mac-list/{self.maintenance_id}/stats",
            headers=self.get_auth_headers()
        )
        if resp.status_code == 200:
            print_json(resp.json())

    # =========================================================================
    # Step 7: 查看時間點和統計
    # =========================================================================
    def step7_view_statistics(self):
        """查看時間點和統計資料"""
        print_header(7, "查看時間點和統計資料")

        # 7.1 時間點
        print("\n7.1 查看可用時間點")
        resp = self.client.get(
            f"{BASE_URL}/comparisons/timepoints/{self.maintenance_id}",
            headers=self.get_auth_headers()
        )
        if resp.status_code == 200:
            data = resp.json()
            timepoints = data.get("timepoints", [])
            print(f"\n可用時間點數量: {len(timepoints)}")
            if timepoints:
                print("\n時間點列表:")
                for tp in timepoints[-5:]:
                    print(f"  - {tp.get('label', 'N/A')}")
        else:
            print(f"✗ 取得失敗: {resp.text}")

        # 7.2 統計資料
        print("\n7.2 查看統計資料（圖表用）")
        resp = self.client.get(
            f"{BASE_URL}/comparisons/statistics/{self.maintenance_id}",
            headers=self.get_auth_headers()
        )
        if resp.status_code == 200:
            data = resp.json()
            stats = data.get("statistics", [])
            print(f"\n統計點數量: {len(stats)}")
            if stats:
                print("\n最新統計:")
                print_json(stats[-1])
        else:
            print(f"✗ 取得失敗: {resp.text}")

    # =========================================================================
    # Step 8: 查看 Dashboard
    # =========================================================================
    def step8_view_dashboard(self):
        """查看 Dashboard 摘要"""
        print_header(8, "查看 Dashboard 摘要")

        resp = self.client.get(
            f"{BASE_URL}/dashboard/maintenance/{self.maintenance_id}/summary",
            headers=self.get_auth_headers()
        )

        if resp.status_code == 200:
            print("\n✓ Dashboard 摘要:")
            print_json(resp.json())
        else:
            print(f"\n✗ 取得失敗: {resp.text}")

    # =========================================================================
    # 主流程
    # =========================================================================
    def run(self):
        """執行分步測試"""
        print("\n" + "=" * 70)
        print("自動化分步驟測試")
        print(f"歲修 ID: {self.maintenance_id}")
        print(f"時間: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("=" * 70)

        if not self.check_server():
            return 1

        if not self.login():
            return 1

        if not self.step1_create_maintenance():
            print("\n建立歲修失敗，無法繼續")
            return 1

        steps = [
            ("匯入 MAC 清單", self.step2_import_mac_list),
            ("匯入設備對應", self.step3_import_devices),
            ("設定期望值", self.step4_setup_expectations),
            ("生成 Mock 資料", self.step5_generate_mock_data),
            ("執行客戶端偵測", self.step6_detect_clients),
            ("查看統計資料", self.step7_view_statistics),
            ("查看 Dashboard", self.step8_view_dashboard),
        ]

        for name, step_func in steps:
            try:
                step_func()
            except Exception as e:
                print(f"\n[ERROR] {name} 執行失敗: {e}")
                import traceback
                traceback.print_exc()

        print("\n" + "=" * 70)
        print("測試完成！")
        print("請到前端查看結果: http://localhost:5173")
        print("=" * 70)
        return 0


if __name__ == "__main__":
    test = AutoStepTest()
    try:
        exit_code = test.run()
    finally:
        test.close()
    sys.exit(exit_code)
