#!/usr/bin/env python3
"""
乾淨重置測試環境

此腳本會：
1. 刪除舊的測試歲修及相關資料
2. 建立新的歲修
3. 匯入測試資料（MAC 清單、設備清單、ARP 來源）

正確的資料流架構：
┌─────────────┐     ┌────────────────────┐     ┌──────────────┐
│  Scheduler  │ ──▶ │ ClientCollection   │ ──▶ │ Mock Fetcher │
│  (每 15 秒)  │     │ Service            │     │ (基於時間收斂) │
└─────────────┘     └────────────────────┘     └──────────────┘
                              │
                              ▼
                    ┌────────────────────┐
                    │  DB (ClientRecord) │
                    └────────────────────┘

Mock Fetcher 收斂邏輯：
- OLD-* 設備：t=0 可達 → t=T/2 不可達
- NEW-* 設備：t=0 不可達 → t=T/2 可達
- T = MOCK_PING_CONVERGE_TIME（預設 5 分鐘）

使用方式：
    1. 停止後端服務
    2. 執行此腳本
    3. 重新啟動後端服務
"""
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
MAINTENANCE_ID = "CONVERGE-TEST"

AUTH_USERNAME = "root"
AUTH_PASSWORD = "root123"


def print_header(title: str):
    """打印標題"""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def print_json(data, indent: int = 2):
    """格式化打印 JSON"""
    print(json.dumps(data, indent=indent, ensure_ascii=False, default=str))


class CleanResetTest:
    def __init__(self):
        self.client = httpx.Client(timeout=30.0)
        self.maintenance_id = MAINTENANCE_ID
        self.token = None

    def close(self):
        self.client.close()

    def get_auth_headers(self):
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
                print("✓ 登入成功")
                return True
            else:
                print(f"✗ 登入失敗: {resp.text}")
                return False
        except Exception as e:
            print(f"✗ 登入錯誤: {e}")
            return False

    def check_server(self) -> bool:
        """檢查伺服器狀態"""
        print("\n檢查伺服器狀態...")
        try:
            resp = self.client.get(BASE_URL.replace('/api/v1', '') + '/health')
            if resp.status_code == 200:
                data = resp.json()
                print(f"✓ 伺服器運行正常")
                print(f"  Scheduler 狀態: {'運行中' if data.get('scheduler_running') else '已停止'}")
                print(f"  排程任務數量: {data.get('scheduled_jobs', 0)}")
                return True
        except httpx.ConnectError:
            pass
        print("✗ 無法連接到伺服器")
        return False

    def delete_maintenance(self) -> bool:
        """刪除舊的歲修及所有相關資料"""
        print_header(f"刪除舊歲修: {self.maintenance_id}")

        resp = self.client.delete(
            f"{BASE_URL}/maintenance/{self.maintenance_id}",
            headers=self.get_auth_headers()
        )

        if resp.status_code == 200:
            print("✓ 已刪除舊歲修及所有相關資料")
            return True
        elif resp.status_code == 404:
            print("⚠ 歲修不存在，跳過刪除")
            return True
        else:
            print(f"✗ 刪除失敗: {resp.text}")
            return False

    def create_maintenance(self) -> bool:
        """建立新歲修"""
        print_header(f"建立新歲修: {self.maintenance_id}")

        resp = self.client.post(
            f"{BASE_URL}/maintenance",
            json={"id": self.maintenance_id, "name": f"收斂測試 {self.maintenance_id}"},
            headers=self.get_auth_headers()
        )

        if resp.status_code == 200:
            print(f"✓ 歲修建立成功")
            data = resp.json()
            print(f"  建立時間: {data.get('created_at', 'N/A')}")
            print(f"  （收斂時間從此刻開始計算）")
            return True
        else:
            print(f"✗ 建立失敗: {resp.text}")
            return False

    def import_mac_list(self) -> bool:
        """匯入 MAC 清單"""
        print_header("匯入 MAC 清單")

        # 對應 test_data/mock_network_state.csv
        test_macs = [
            {"mac_address": "AA:BB:CC:DD:EE:01", "ip_address": "10.1.1.101", "tenant_group": "F18", "description": "EQP-001"},
            {"mac_address": "AA:BB:CC:DD:EE:02", "ip_address": "10.1.1.102", "tenant_group": "F18", "description": "EQP-002"},
            {"mac_address": "AA:BB:CC:DD:EE:03", "ip_address": "10.1.1.103", "tenant_group": "F18", "description": "EQP-003"},
            {"mac_address": "AA:BB:CC:DD:EE:04", "ip_address": "10.1.1.104", "tenant_group": "F6", "description": "AMHS-001"},
            {"mac_address": "AA:BB:CC:DD:EE:05", "ip_address": "10.1.1.105", "tenant_group": "F6", "description": "AMHS-002"},
            {"mac_address": "AA:BB:CC:DD:EE:06", "ip_address": "10.1.1.106", "tenant_group": "F6", "description": "AMHS-003"},
            {"mac_address": "AA:BB:CC:DD:EE:07", "ip_address": "10.1.1.107", "tenant_group": "AP", "description": "AP-001"},
            {"mac_address": "AA:BB:CC:DD:EE:08", "ip_address": "10.1.1.108", "tenant_group": "AP", "description": "AP-002"},
        ]

        print(f"匯入 {len(test_macs)} 筆 MAC...")
        success_count = 0
        for mac in test_macs:
            resp = self.client.post(
                f"{BASE_URL}/mac-list/{self.maintenance_id}",
                json=mac,
                headers=self.get_auth_headers()
            )
            if resp.status_code == 200:
                success_count += 1
            else:
                print(f"  ✗ {mac['mac_address']} 失敗: {resp.text}")

        print(f"✓ 成功匯入 {success_count}/{len(test_macs)} 筆")
        return success_count == len(test_macs)

    def import_devices(self) -> bool:
        """匯入設備清單（使用 OLD/NEW 命名讓收斂機制生效）"""
        print_header("匯入設備清單")

        # OLD-* 設備會逐漸離線，NEW-* 設備會逐漸上線
        test_devices = [
            {
                "old_hostname": "OLD-SW-001", "old_ip_address": "10.1.1.1", "old_vendor": "HPE",
                "new_hostname": "NEW-SW-001", "new_ip_address": "10.1.1.11", "new_vendor": "HPE",
                "use_same_port": True, "tenant_group": "F18", "description": "EQP 核心交換機",
            },
            {
                "old_hostname": "OLD-SW-002", "old_ip_address": "10.1.1.2", "old_vendor": "HPE",
                "new_hostname": "NEW-SW-002", "new_ip_address": "10.1.1.12", "new_vendor": "HPE",
                "use_same_port": True, "tenant_group": "F6", "description": "AMHS 核心交換機",
            },
            {
                "old_hostname": "OLD-SW-003", "old_ip_address": "10.1.1.3", "old_vendor": "HPE",
                "new_hostname": "NEW-SW-003", "new_ip_address": "10.1.1.13", "new_vendor": "HPE",
                "use_same_port": True, "tenant_group": "AP", "description": "AP 核心交換機",
            },
        ]

        print(f"匯入 {len(test_devices)} 筆設備對應...")
        for dev in test_devices:
            resp = self.client.post(
                f"{BASE_URL}/maintenance-devices/{self.maintenance_id}",
                json=dev,
                headers=self.get_auth_headers()
            )
            if resp.status_code == 200:
                print(f"  ✓ {dev['old_hostname']} → {dev['new_hostname']}")
            else:
                print(f"  ✗ {dev['old_hostname']} 失敗: {resp.text}")

        return True

    def setup_arp_sources(self) -> bool:
        """設定 ARP 來源設備"""
        print_header("設定 ARP 來源設備")

        # 使用 NEW 設備作為 ARP 來源
        # ARP 來源必須可達才會撈取 ARP 資料
        # 所以在收斂之前（NEW 設備不可達），detect_clients 會返回 no_arp
        arp_sources = [
            {"hostname": "NEW-SW-001", "ip_address": "10.1.1.11", "priority": 1},
        ]

        print("設定 ARP 來源...")
        for src in arp_sources:
            resp = self.client.post(
                f"{BASE_URL}/expectations/arp/{self.maintenance_id}",
                json=src,
                headers=self.get_auth_headers()
            )
            if resp.status_code == 200:
                print(f"  ✓ ARP 來源: {src['hostname']}")
            else:
                print(f"  ✗ 設定失敗: {resp.text}")

        return True

    def run(self):
        """執行重置"""
        print("\n" + "=" * 60)
        print("  乾淨重置測試環境")
        print(f"  歲修 ID: {self.maintenance_id}")
        print(f"  時間: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("=" * 60)

        if not self.check_server():
            return 1

        if not self.login():
            return 1

        # 刪除舊資料
        self.delete_maintenance()

        # 建立新歲修
        if not self.create_maintenance():
            return 1

        # 匯入測試資料
        self.import_mac_list()
        self.import_devices()
        self.setup_arp_sources()

        print_header("設定完成！")
        print("""
正確的資料流架構：

1. Scheduler 每 15 秒觸發 client-collection job
2. ClientCollectionService 呼叫 fetchers 取得資料
3. Mock Fetchers 根據「經過時間」回傳收斂中的資料：
   - t=0:      NEW 設備不可達，OLD 設備可達
   - t=T/2:    切換點（T = MOCK_PING_CONVERGE_TIME）
   - t≥T/2:    NEW 設備可達，OLD 設備不可達
4. 資料寫入 DB，Dashboard 即時查詢

收斂時間設定：
   MOCK_PING_CONVERGE_TIME=300  (5 分鐘)
   收斂切換點 = T/2 = 2.5 分鐘

接下來：
1. 確認 scheduler.yaml 中 mock-client-generation 已停用
2. 重新啟動後端服務
3. 觀察 Dashboard 變化（約 2.5 分鐘後開始收斂）
""")
        return 0


if __name__ == "__main__":
    setup = CleanResetTest()
    try:
        exit_code = setup.run()
    finally:
        setup.close()
    sys.exit(exit_code)
