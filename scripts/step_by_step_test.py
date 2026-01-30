#!/usr/bin/env python3
"""
分步驟互動式測試腳本

每個步驟會等待用戶確認後再繼續，方便觀察系統狀態。
"""
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))

# =============================================================================
# 配置
# =============================================================================
BASE_URL = "http://localhost:8000/api/v1"
MAINTENANCE_ID = "STEP-TEST-001"


def wait_for_user(prompt: str = "按 Enter 繼續，輸入 'q' 退出..."):
    """等待用戶輸入"""
    user_input = input(f"\n{prompt} ")
    if user_input.lower() == 'q':
        print("用戶取消測試")
        sys.exit(0)
    return user_input


def print_header(step: int, title: str):
    """打印步驟標題"""
    print(f"\n{'=' * 70}")
    print(f"【Step {step}】{title}")
    print(f"{'=' * 70}")


def print_json(data, indent: int = 2):
    """格式化打印 JSON"""
    import json
    print(json.dumps(data, indent=indent, ensure_ascii=False, default=str))


class StepByStepTest:
    def __init__(self):
        self.client = httpx.Client(timeout=30.0)
        self.maintenance_id = MAINTENANCE_ID

    def close(self):
        self.client.close()

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
        print("\n請先啟動後端服務:")
        print("  cd network_dashboard")
        print("  source venv/bin/activate")
        print("  python -m app.main")
        return False

    # =========================================================================
    # Step 0: 清空測試資料
    # =========================================================================
    def step0_cleanup(self):
        """清空測試資料"""
        print_header(0, "清空測試資料（可選）")

        print(f"\n將刪除歲修 ID: {self.maintenance_id}")
        print("這會移除所有相關資料（MAC清單、設備、期望值等）")

        choice = wait_for_user("輸入 'y' 確認刪除，或按 Enter 跳過: ")

        if choice.lower() == 'y':
            resp = self.client.delete(f"{BASE_URL}/maintenance/{self.maintenance_id}")
            if resp.status_code == 200:
                print(f"✓ 已刪除歲修 ID: {self.maintenance_id}")
            elif resp.status_code == 404:
                print("✓ 歲修 ID 不存在，無需刪除")
            else:
                print(f"✗ 刪除失敗: {resp.text}")
        else:
            print("跳過清空步驟")

    # =========================================================================
    # Step 1: 建立歲修 ID
    # =========================================================================
    def step1_create_maintenance(self):
        """建立歲修 ID"""
        print_header(1, "建立歲修 ID")

        print(f"\n將建立歲修 ID: {self.maintenance_id}")
        print("\nAPI 請求:")
        print(f"  POST {BASE_URL}/maintenance")
        print(f"  Body: {{'maintenance_id': '{self.maintenance_id}'}}")

        wait_for_user()

        resp = self.client.post(
            f"{BASE_URL}/maintenance",
            json={"maintenance_id": self.maintenance_id}
        )

        print(f"\n回應狀態: {resp.status_code}")
        if resp.status_code == 200:
            print("✓ 歲修 ID 建立成功")
            print("\n回應內容:")
            print_json(resp.json())
        else:
            print(f"✗ 建立失敗: {resp.text}")
            if "already exists" in resp.text:
                print("\n提示: 歲修 ID 已存在，可回到 Step 0 清空資料")

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

        print("\n將匯入以下 MAC 清單:")
        for mac in test_macs:
            print(f"  - {mac['mac_address']} / {mac['ip_address']} ({mac['tenant_group']})")

        print(f"\nAPI 請求:")
        print(f"  POST {BASE_URL}/mac-list/{self.maintenance_id}")

        wait_for_user()

        success_count = 0
        for mac in test_macs:
            resp = self.client.post(
                f"{BASE_URL}/mac-list/{self.maintenance_id}",
                json=mac
            )
            if resp.status_code == 200:
                success_count += 1
                print(f"  ✓ {mac['mac_address']} 匯入成功")
            else:
                print(f"  ✗ {mac['mac_address']} 匯入失敗: {resp.text}")

        print(f"\n結果: {success_count}/{len(test_macs)} 筆成功")

        # 查看統計
        print("\n查看 MAC 統計:")
        resp = self.client.get(f"{BASE_URL}/mac-list/{self.maintenance_id}/stats")
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

        print("\n將匯入以下設備對應:")
        for dev in test_devices:
            print(f"  - {dev['old_hostname']} → {dev['new_hostname']}")

        print(f"\nAPI 請求:")
        print(f"  POST {BASE_URL}/maintenance-devices/{self.maintenance_id}")

        wait_for_user()

        for dev in test_devices:
            resp = self.client.post(
                f"{BASE_URL}/maintenance-devices/{self.maintenance_id}",
                json=dev
            )
            if resp.status_code == 200:
                print(f"  ✓ {dev['old_hostname']} → {dev['new_hostname']} 匯入成功")
            else:
                print(f"  ✗ 匯入失敗: {resp.text}")

        # 查看統計
        print("\n查看設備統計:")
        resp = self.client.get(f"{BASE_URL}/maintenance-devices/{self.maintenance_id}/stats")
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

        print("\n將設定以下版本期望:")
        for exp in version_expectations:
            print(f"  - {exp['hostname']}: {exp['expected_version']}")

        print(f"\nAPI 請求:")
        print(f"  POST {BASE_URL}/expectations/version/{self.maintenance_id}")

        wait_for_user()

        for exp in version_expectations:
            resp = self.client.post(
                f"{BASE_URL}/expectations/version/{self.maintenance_id}",
                json=exp
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

        print("\n將設定以下 ARP 來源:")
        for src in arp_sources:
            print(f"  - {src['hostname']} ({src['ip_address']}) 優先級: {src['priority']}")

        wait_for_user()

        for src in arp_sources:
            resp = self.client.post(
                f"{BASE_URL}/expectations/arp/{self.maintenance_id}",
                json=src
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

        print("\n此步驟會透過服務層直接生成 Mock ClientRecord 資料")
        print("模擬 Scheduler 定期收集資料的行為")
        print("\n將生成 3 批次資料，每批次間隔 1 秒")

        wait_for_user()

        # 必須用 asyncio 來執行
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

        print("\n此步驟會觸發客戶端偵測，比對 ARP 資料和 Ping 結果")
        print("\nAPI 請求:")
        print(f"  POST {BASE_URL}/mac-list/{self.maintenance_id}/detect")

        wait_for_user()

        print("\n執行偵測中...")
        resp = self.client.post(
            f"{BASE_URL}/mac-list/{self.maintenance_id}/detect",
            timeout=60.0
        )

        if resp.status_code == 200:
            result = resp.json()
            print("\n✓ 偵測完成")
            print("\n偵測結果:")
            print_json(result)

            print("\n說明:")
            print(f"  - detected: 已偵測到的 Client 數量")
            print(f"  - mismatch: IP/MAC 不匹配的數量")
            print(f"  - not_detected: 未偵測到的數量")
        else:
            print(f"\n✗ 偵測失敗: {resp.text}")

        # 查看更新後的統計
        print("\n查看更新後的 MAC 統計:")
        resp = self.client.get(f"{BASE_URL}/mac-list/{self.maintenance_id}/stats")
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
        print(f"\nAPI 請求:")
        print(f"  GET {BASE_URL}/comparisons/timepoints/{self.maintenance_id}")

        wait_for_user()

        resp = self.client.get(f"{BASE_URL}/comparisons/timepoints/{self.maintenance_id}")
        if resp.status_code == 200:
            data = resp.json()
            timepoints = data.get("timepoints", [])
            print(f"\n可用時間點數量: {len(timepoints)}")
            if timepoints:
                print("\n時間點列表:")
                for tp in timepoints[-5:]:  # 只顯示最後 5 個
                    print(f"  - {tp.get('label', 'N/A')}")
        else:
            print(f"✗ 取得失敗: {resp.text}")

        # 7.2 統計資料
        print("\n7.2 查看統計資料（圖表用）")
        print(f"\nAPI 請求:")
        print(f"  GET {BASE_URL}/comparisons/statistics/{self.maintenance_id}")

        wait_for_user()

        resp = self.client.get(f"{BASE_URL}/comparisons/statistics/{self.maintenance_id}")
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
    # Step 8: 啟動 Scheduler（背景持續運行）
    # =========================================================================
    def step8_start_scheduler(self):
        """啟動 Scheduler"""
        print_header(8, "啟動 Scheduler（持續運行）")

        print("\n此步驟會啟動 Scheduler 服務，持續執行排程任務")
        print("\n排程任務包含:")
        print("  - mock-client-generation: 每 60 秒生成 Mock 資料")
        print("  - cleanup-old-records: 每小時清理超過 7 天的資料")

        print("\n注意: Scheduler 會在背景持續運行")
        print("您可以同時打開前端頁面觀察資料變化")
        print("\n前端 URL: http://localhost:5173")

        wait_for_user("輸入 'y' 啟動 Scheduler，或按 Enter 跳過: ")

        # 這裡不會真的啟動，因為 Scheduler 需要在應用程式啟動時初始化
        print("\n提示: Scheduler 已在應用程式啟動時自動運行")
        print("請確認 scheduler.yaml 中的 mock-client-generation 已啟用")
        print("\n可查看後端日誌確認 Scheduler 狀態")

    # =========================================================================
    # 主流程
    # =========================================================================
    def run(self):
        """執行分步測試"""
        print("\n" + "=" * 70)
        print("分步驟互動式測試")
        print(f"歲修 ID: {self.maintenance_id}")
        print(f"時間: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("=" * 70)

        if not self.check_server():
            return 1

        steps = [
            ("清空測試資料", self.step0_cleanup),
            ("建立歲修 ID", self.step1_create_maintenance),
            ("匯入 MAC 清單", self.step2_import_mac_list),
            ("匯入設備對應", self.step3_import_devices),
            ("設定期望值", self.step4_setup_expectations),
            ("生成 Mock 資料", self.step5_generate_mock_data),
            ("執行客戶端偵測", self.step6_detect_clients),
            ("查看統計資料", self.step7_view_statistics),
            ("啟動 Scheduler", self.step8_start_scheduler),
        ]

        for name, step_func in steps:
            try:
                step_func()
            except KeyboardInterrupt:
                print("\n\n用戶中斷測試")
                break
            except Exception as e:
                print(f"\n[ERROR] {name} 執行失敗: {e}")
                import traceback
                traceback.print_exc()

                choice = wait_for_user("輸入 'c' 繼續下一步，或按 Enter 退出: ")
                if choice.lower() != 'c':
                    break

        print("\n" + "=" * 70)
        print("測試結束")
        print("=" * 70)
        return 0


if __name__ == "__main__":
    test = StepByStepTest()
    try:
        exit_code = test.run()
    finally:
        test.close()
    sys.exit(exit_code)
