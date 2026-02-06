#!/usr/bin/env python3
"""
收斂測試設定腳本

此腳本設定測試環境，讓 Scheduler 自動執行真實資料流。
Mock Fetcher 會根據時間產生收斂的資料（NEW 設備逐漸上線，OLD 設備逐漸離線）。

使用方式：
    1. 確保後端服務正在運行
    2. 執行此腳本設定測試資料
    3. 觀察前端 Dashboard 的變化

收斂時間設定（.env）：
    MOCK_PING_CONVERGE_TIME=1800  # 30 分鐘

測試案例：
    - 正常客戶端：MAC/IP 符合，可 ping
    - MISMATCH 案例：MAC 存在但 IP 不符
    - NOT_DETECTED 案例：MAC 不在模擬網路中
    - Ping 失敗案例：MAC/IP 符合但 ping 失敗

預期行為：
    t=0:      NEW 設備 ~0% 可達，OLD 設備 ~100% 可達
    t=T/2:    收斂中，新舊設備各約 50% 可達
    t=T:      NEW 設備 ~98% 可達，OLD 設備 ~2% 可達
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

# 認證配置
AUTH_USERNAME = "root"
AUTH_PASSWORD = "admin123"


def print_header(title: str):
    """打印標題"""
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def print_json(data, indent: int = 2):
    """格式化打印 JSON"""
    print(json.dumps(data, indent=indent, ensure_ascii=False, default=str))


class ConvergenceTestSetup:
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
                print("✓ 登入成功")
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
                data = resp.json()
                print(f"✓ 伺服器運行正常")
                print(f"  Scheduler 狀態: {'運行中' if data.get('scheduler_running') else '已停止'}")
                print(f"  排程任務數量: {data.get('scheduled_jobs', 0)}")
                return True
        except httpx.ConnectError:
            pass
        print("✗ 無法連接到伺服器")
        return False

    def create_maintenance(self) -> bool:
        """建立歲修"""
        print_header(f"建立歲修: {self.maintenance_id}")

        # 先檢查是否存在
        resp = self.client.get(
            f"{BASE_URL}/maintenance",
            headers=self.get_auth_headers()
        )

        if resp.status_code == 200:
            maintenances = resp.json()
            found = any(m.get("maintenance_id") == self.maintenance_id for m in maintenances)
            if found:
                print(f"⚠ 歲修 '{self.maintenance_id}' 已存在")
                choice = input("是否刪除並重新建立？(y/N): ")
                if choice.lower() == 'y':
                    del_resp = self.client.delete(
                        f"{BASE_URL}/maintenance/{self.maintenance_id}",
                        headers=self.get_auth_headers()
                    )
                    if del_resp.status_code == 200:
                        print("✓ 已刪除舊歲修")
                    else:
                        print(f"✗ 刪除失敗: {del_resp.text}")
                        return False
                else:
                    print("使用現有歲修")
                    return True

        # 建立歲修
        resp = self.client.post(
            f"{BASE_URL}/maintenance",
            json={"id": self.maintenance_id, "name": f"收斂測試 {self.maintenance_id}"},
            headers=self.get_auth_headers()
        )

        if resp.status_code == 200:
            print(f"✓ 歲修建立成功")
            print_json(resp.json())
            return True
        else:
            print(f"✗ 建立失敗: {resp.text}")
            return False

    def import_devices(self) -> bool:
        """匯入設備清單（對應 mock_network_state.csv 的 switch 命名）"""
        print_header("匯入設備清單")

        # 設備清單對應 mock_network_state.csv 中的 switch
        # tenant_group 只能是: F18, F6, AP, F14, F12
        # 對應: EQP→F18, AMHS→F6, 基礎設施→F14
        test_devices = [
            # Router（ARP 來源）
            {
                "old_hostname": "OLD-ROUTER-01", "old_ip_address": "10.1.0.1", "old_vendor": "HPE",
                "new_hostname": "NEW-ROUTER-01", "new_ip_address": "10.1.0.11", "new_vendor": "HPE",
                "use_same_port": True, "tenant_group": "F14", "description": "核心路由器（ARP 來源）",
            },
            # EQP Switches (tenant_group: F18)
            {
                "old_hostname": "SW-OLD-011-EQP", "old_ip_address": "192.168.10.1", "old_vendor": "HPE",
                "new_hostname": "SW-NEW-011-EQP", "new_ip_address": "192.168.10.11", "new_vendor": "HPE",
                "use_same_port": True, "tenant_group": "F18", "description": "EQP 交換機 011",
            },
            {
                "old_hostname": "SW-OLD-012-EQP", "old_ip_address": "192.168.10.2", "old_vendor": "HPE",
                "new_hostname": "SW-NEW-012-EQP", "new_ip_address": "192.168.10.12", "new_vendor": "HPE",
                "use_same_port": True, "tenant_group": "F18", "description": "EQP 交換機 012",
            },
            # AMHS Switches (tenant_group: F6)
            {
                "old_hostname": "SW-OLD-021-AMHS", "old_ip_address": "192.168.20.1", "old_vendor": "HPE",
                "new_hostname": "SW-NEW-021-AMHS", "new_ip_address": "192.168.20.11", "new_vendor": "HPE",
                "use_same_port": True, "tenant_group": "F6", "description": "AMHS 交換機 021",
            },
            {
                "old_hostname": "SW-OLD-022-AMHS", "old_ip_address": "192.168.20.2", "old_vendor": "HPE",
                "new_hostname": "SW-NEW-022-AMHS", "new_ip_address": "192.168.20.12", "new_vendor": "HPE",
                "use_same_port": True, "tenant_group": "F6", "description": "AMHS 交換機 022",
            },
            # AP Switches (tenant_group: AP)
            {
                "old_hostname": "SW-OLD-031-AP", "old_ip_address": "192.168.30.1", "old_vendor": "HPE",
                "new_hostname": "SW-NEW-031-AP", "new_ip_address": "192.168.30.11", "new_vendor": "HPE",
                "use_same_port": True, "tenant_group": "AP", "description": "AP 交換機 031",
            },
        ]

        print(f"\n匯入 {len(test_devices)} 筆設備對應...")
        success_count = 0
        for dev in test_devices:
            resp = self.client.post(
                f"{BASE_URL}/maintenance-devices/{self.maintenance_id}",
                json=dev,
                headers=self.get_auth_headers()
            )
            if resp.status_code == 200:
                print(f"  ✓ {dev['old_hostname']} → {dev['new_hostname']}")
                success_count += 1
            else:
                print(f"  ✗ {dev['old_hostname']} 失敗: {resp.text}")

        print(f"✓ 成功匯入 {success_count}/{len(test_devices)} 筆設備")
        return success_count > 0

    def import_mac_list(self) -> bool:
        """匯入 MAC 清單（包含正常和異常測試案例）"""
        print_header("匯入 MAC 清單")

        # MAC 清單對應 mock_network_state.csv
        # tenant_group 只能是: F18, F6, AP, F14, F12
        # 對應: EQP→F18, AMHS→F6
        test_macs = [
            # ===== 正常案例（DETECTED）=====
            # EQP 客戶端 - 對應 mock_network_state.csv (tenant_group: F18)
            {"mac_address": "00:11:22:E0:01:01", "ip_address": "192.168.10.101", "tenant_group": "F18", "description": "EQP 設備 001 (正常)"},
            {"mac_address": "00:11:22:E0:01:02", "ip_address": "192.168.10.102", "tenant_group": "F18", "description": "EQP 設備 002 (正常)"},
            {"mac_address": "00:11:22:E0:01:03", "ip_address": "192.168.10.103", "tenant_group": "F18", "description": "EQP 設備 003 (正常)"},
            {"mac_address": "00:11:22:E0:01:04", "ip_address": "192.168.10.104", "tenant_group": "F18", "description": "EQP 設備 004 (正常)"},

            # AMHS 客戶端 (tenant_group: F6)
            {"mac_address": "00:11:22:A0:01:01", "ip_address": "192.168.20.101", "tenant_group": "F6", "description": "AMHS 設備 001 (正常)"},
            {"mac_address": "00:11:22:A0:01:02", "ip_address": "192.168.20.102", "tenant_group": "F6", "description": "AMHS 設備 002 (正常)"},
            {"mac_address": "00:11:22:A0:01:03", "ip_address": "192.168.20.103", "tenant_group": "F6", "description": "AMHS 設備 003 (正常)"},
            {"mac_address": "00:11:22:A0:01:04", "ip_address": "192.168.20.104", "tenant_group": "F6", "description": "AMHS 設備 004 (正常)"},

            # AP 客戶端 (tenant_group: AP)
            {"mac_address": "00:11:22:33:01:01", "ip_address": "192.168.30.101", "tenant_group": "AP", "description": "AP 設備 001 (正常)"},
            {"mac_address": "00:11:22:33:01:02", "ip_address": "192.168.30.102", "tenant_group": "AP", "description": "AP 設備 002 (正常)"},

            # ===== MISMATCH 案例 =====
            # MAC 存在於 mock_network_state.csv 但 IP 不符
            {"mac_address": "00:11:22:FF:02:02", "ip_address": "192.168.99.200", "tenant_group": "F18", "description": "IP 不符測試 (MISMATCH)"},

            # ===== NOT_DETECTED 案例 =====
            # MAC 不存在於 mock_network_state.csv
            {"mac_address": "AA:BB:CC:DD:EE:01", "ip_address": "10.99.99.1", "tenant_group": "F18", "description": "不存在的設備 001 (NOT_DETECTED)"},
            {"mac_address": "AA:BB:CC:DD:EE:02", "ip_address": "10.99.99.2", "tenant_group": "F6", "description": "不存在的設備 002 (NOT_DETECTED)"},

            # ===== Ping 失敗案例 =====
            # MAC/IP 對應存在，但 mock_network_state.csv 中 ping_reachable=false
            {"mac_address": "00:11:22:FF:01:01", "ip_address": "192.168.99.101", "tenant_group": "F18", "description": "Ping 失敗測試 (NOT_DETECTED)"},
        ]

        print(f"\n匯入 {len(test_macs)} 筆 MAC 清單...")
        print("  測試案例分布：")
        print("    - 正常案例 (DETECTED): 10 筆")
        print("    - MISMATCH 案例: 1 筆")
        print("    - NOT_DETECTED 案例: 3 筆")
        print("    - Ping 失敗案例: 1 筆")

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

    def setup_arp_sources(self) -> bool:
        """設定 ARP 來源設備（新舊 Router 都設定，避免換機時丟失 MAC）"""
        print_header("設定 ARP 來源設備")

        # 同時設定新舊 Router 作為 ARP 來源
        # 這樣無論在收斂前後都能取得 ARP 資料
        arp_sources = [
            {"hostname": "OLD-ROUTER-01", "ip_address": "10.1.0.1", "priority": 1},
            {"hostname": "NEW-ROUTER-01", "ip_address": "10.1.0.11", "priority": 2},
        ]

        print("\n設定新舊 Router 作為 ARP 來源（避免換機時丟失 MAC）")
        success_count = 0
        for src in arp_sources:
            resp = self.client.post(
                f"{BASE_URL}/expectations/arp/{self.maintenance_id}",
                json=src,
                headers=self.get_auth_headers()
            )
            if resp.status_code == 200:
                print(f"  ✓ ARP 來源: {src['hostname']} ({src['ip_address']}) priority={src['priority']}")
                success_count += 1
            else:
                print(f"  ✗ {src['hostname']} 設定失敗: {resp.text}")

        print(f"✓ 成功設定 {success_count}/{len(arp_sources)} 個 ARP 來源")
        return success_count > 0

    def setup_expectations(self) -> bool:
        """設定期望值（Uplink, Version, Port-Channel）"""
        print_header("設定期望值")

        # ===== Uplink 期望 =====
        print("\n設定 Uplink 期望...")
        uplink_expectations = [
            # SW-NEW-011-EQP 的上行連接
            {
                "hostname": "SW-NEW-011-EQP",
                "local_interface": "GE1/0/49",
                "expected_neighbor": "NEW-ROUTER-01",
                "expected_interface": "GE1/0/1",
                "description": "EQP-011 上行到 Router",
            },
            # SW-NEW-012-EQP 的上行連接
            {
                "hostname": "SW-NEW-012-EQP",
                "local_interface": "GE1/0/49",
                "expected_neighbor": "NEW-ROUTER-01",
                "expected_interface": "GE1/0/2",
                "description": "EQP-012 上行到 Router",
            },
            # SW-NEW-021-AMHS 的上行連接
            {
                "hostname": "SW-NEW-021-AMHS",
                "local_interface": "1/1/49",
                "expected_neighbor": "NEW-ROUTER-01",
                "expected_interface": "GE1/0/3",
                "description": "AMHS-021 上行到 Router",
            },
        ]

        uplink_success = 0
        for exp in uplink_expectations:
            resp = self.client.post(
                f"{BASE_URL}/expectations/uplink/{self.maintenance_id}",
                json=exp,
                headers=self.get_auth_headers()
            )
            if resp.status_code == 200:
                print(f"  ✓ Uplink: {exp['hostname']}:{exp['local_interface']} → {exp['expected_neighbor']}")
                uplink_success += 1
            else:
                print(f"  ✗ {exp['hostname']} 失敗: {resp.text}")

        # ===== Version 期望 =====
        print("\n設定 Version 期望...")
        version_expectations = [
            {"hostname": "SW-NEW-011-EQP", "expected_versions": "6635P07;6635P08", "description": "EQP-011 期望版本"},
            {"hostname": "SW-NEW-012-EQP", "expected_versions": "6635P07;6635P08", "description": "EQP-012 期望版本"},
            {"hostname": "SW-NEW-021-AMHS", "expected_versions": "6635P07;6635P08", "description": "AMHS-021 期望版本"},
            {"hostname": "SW-NEW-022-AMHS", "expected_versions": "6635P07;6635P08", "description": "AMHS-022 期望版本"},
            {"hostname": "SW-NEW-031-AP", "expected_versions": "6635P07;6635P08", "description": "AP-031 期望版本"},
            {"hostname": "NEW-ROUTER-01", "expected_versions": "6635P07;6635P08", "description": "Router 期望版本"},
        ]

        version_success = 0
        for exp in version_expectations:
            resp = self.client.post(
                f"{BASE_URL}/expectations/version/{self.maintenance_id}",
                json=exp,
                headers=self.get_auth_headers()
            )
            if resp.status_code == 200:
                print(f"  ✓ Version: {exp['hostname']} → {exp['expected_versions']}")
                version_success += 1
            else:
                print(f"  ✗ {exp['hostname']} 失敗: {resp.text}")

        # ===== Port-Channel 期望 =====
        print("\n設定 Port-Channel 期望...")
        port_channel_expectations = [
            {
                "hostname": "SW-NEW-011-EQP",
                "port_channel": "BAGG1",
                "member_interfaces": "XGE1/0/51;XGE1/0/52",
                "description": "EQP-011 LAG",
            },
            {
                "hostname": "SW-NEW-012-EQP",
                "port_channel": "BAGG1",
                "member_interfaces": "XGE1/0/51;XGE1/0/52",
                "description": "EQP-012 LAG",
            },
            {
                "hostname": "SW-NEW-021-AMHS",
                "port_channel": "BAGG1",
                "member_interfaces": "HGE1/0/25;HGE1/0/26",
                "description": "AMHS-021 LAG",
            },
        ]

        pc_success = 0
        for exp in port_channel_expectations:
            resp = self.client.post(
                f"{BASE_URL}/expectations/port-channel/{self.maintenance_id}",
                json=exp,
                headers=self.get_auth_headers()
            )
            if resp.status_code == 200:
                print(f"  ✓ Port-Channel: {exp['hostname']}:{exp['port_channel']} → {exp['member_interfaces']}")
                pc_success += 1
            else:
                print(f"  ✗ {exp['hostname']} 失敗: {resp.text}")

        total = len(uplink_expectations) + len(version_expectations) + len(port_channel_expectations)
        success = uplink_success + version_success + pc_success
        print(f"\n✓ 期望值設定完成: {success}/{total}")
        return success > 0

    def show_status(self):
        """顯示目前狀態"""
        print_header("目前狀態")

        # MAC 統計
        resp = self.client.get(
            f"{BASE_URL}/mac-list/{self.maintenance_id}/stats",
            headers=self.get_auth_headers()
        )
        if resp.status_code == 200:
            print("\nMAC 清單統計:")
            print_json(resp.json())

        # 設備統計
        resp = self.client.get(
            f"{BASE_URL}/maintenance-devices/{self.maintenance_id}/stats",
            headers=self.get_auth_headers()
        )
        if resp.status_code == 200:
            print("\n設備統計:")
            print_json(resp.json())

        # Dashboard
        resp = self.client.get(
            f"{BASE_URL}/dashboard/maintenance/{self.maintenance_id}/summary",
            headers=self.get_auth_headers()
        )
        if resp.status_code == 200:
            data = resp.json()
            print("\nDashboard 摘要:")
            print(f"  整體通過率: {data['overall']['pass_rate']:.1f}%")
            for name, indicator in data.get('indicators', {}).items():
                print(f"  - {name}: {indicator['pass_count']}/{indicator['total_count']}")

    def run(self):
        """執行設定"""
        print("\n" + "=" * 60)
        print("  收斂測試環境設定（完整版）")
        print(f"  歲修 ID: {self.maintenance_id}")
        print(f"  時間: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print("=" * 60)

        if not self.check_server():
            return 1

        if not self.login():
            return 1

        if not self.create_maintenance():
            return 1

        # 必須先匯入設備，因為期望值會驗證設備是否存在
        self.import_devices()
        self.import_mac_list()
        self.setup_arp_sources()
        self.setup_expectations()

        self.show_status()

        print_header("設定完成！")
        print("""
測試案例說明：

1. 正常案例 (DETECTED)：
   - 10 筆 MAC 對應 mock_network_state.csv
   - 收斂後會顯示為 DETECTED

2. MISMATCH 案例：
   - 00:11:22:FF:02:02 IP 不符
   - 會顯示為 MISMATCH

3. NOT_DETECTED 案例：
   - AA:BB:CC:DD:EE:01/02 不在模擬網路中
   - 00:11:22:FF:01:01 在模擬網路但 ping 失敗
   - 會顯示為 NOT_DETECTED

收斂時程（T=30分鐘）：
   - t=0:      OLD 設備 ~100% 可達，NEW 設備 ~0% 可達
   - t=15min:  收斂中，各約 50%
   - t=30min:  NEW 設備 ~98% 可達，OLD 設備 ~2% 可達

前端觀察：
   http://localhost:3001
   選擇歲修: CONVERGE-TEST
""")
        return 0


if __name__ == "__main__":
    setup = ConvergenceTestSetup()
    try:
        exit_code = setup.run()
    finally:
        setup.close()
    sys.exit(exit_code)
