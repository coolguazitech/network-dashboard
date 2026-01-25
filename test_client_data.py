"""
創建客戶端追蹤測試數據。
"""
import asyncio
from datetime import datetime

from app.core.enums import MaintenancePhase
from app.db.base import get_session_context
from app.db.models import ClientRecord
from app.parsers.registry import auto_discover_parsers


async def create_client_test_data():
    """創建客戶端測試數據。"""
    
    print("=" * 70)
    print("🌐 創建客戶端追蹤測試數據")
    print("=" * 70)
    
    auto_discover_parsers()
    
    async with get_session_context() as session:
        clients = [
            {
                "mac_address": "AA:BB:CC:DD:EE:01",
                "ip_address": "192.168.1.10",
                "hostname": "client-01",
                "switch_hostname": "switch-new-01",
                "interface_name": "Ethernet1/1",
                "vlan_id": 10,
                "speed": "1G",
                "duplex": "full",
                "link_status": "up",
                "ping_reachable": True,
                "ping_latency_ms": 5.2,
                "acl_rules_applied": ["rule1", "rule2"],
                "acl_passes": True,
            },
            {
                "mac_address": "AA:BB:CC:DD:EE:02",
                "ip_address": "192.168.1.20",
                "hostname": "client-02",
                "switch_hostname": "switch-new-01",
                "interface_name": "Ethernet1/2",
                "vlan_id": 10,
                "speed": "1G",
                "duplex": "full",
                "link_status": "up",
                "ping_reachable": True,
                "ping_latency_ms": 150.5,  # ❌ 延遲太高
                "acl_rules_applied": ["rule1"],
                "acl_passes": True,
            },
            {
                "mac_address": "AA:BB:CC:DD:EE:03",
                "ip_address": "192.168.1.30",
                "hostname": "client-03",
                "switch_hostname": "switch-new-02",
                "interface_name": "Ethernet1/1",
                "vlan_id": 20,
                "speed": "1G",
                "duplex": "half",  # ❌ 應該是 full
                "link_status": "up",
                "ping_reachable": True,
                "ping_latency_ms": 8.3,
                "acl_rules_applied": ["rule1"],
                "acl_passes": True,
            },
            {
                "mac_address": "AA:BB:CC:DD:EE:04",
                "ip_address": "192.168.1.40",
                "hostname": "client-04",
                "switch_hostname": "switch-new-02",
                "interface_name": "Ethernet1/2",
                "vlan_id": 20,
                "speed": "1G",
                "duplex": "full",
                "link_status": "down",  # ❌ Link 斷開
                "ping_reachable": False,
                "ping_latency_ms": None,
                "acl_rules_applied": None,
                "acl_passes": False,
            },
            {
                "mac_address": "AA:BB:CC:DD:EE:05",
                "ip_address": "192.168.1.50",
                "hostname": "client-05",
                "switch_hostname": "switch-new-02",
                "interface_name": "Ethernet1/3",
                "vlan_id": 20,
                "speed": "1G",
                "duplex": "full",
                "link_status": "up",
                "ping_reachable": True,
                "ping_latency_ms": 6.1,
                "acl_rules_applied": ["rule1", "rule2"],
                "acl_passes": True,
            },
        ]
        
        for client_data in clients:
            record = ClientRecord(
                maintenance_id="2026Q1-ANNUAL",
                phase=MaintenancePhase.NEW,
                collected_at=datetime.now(),
                mac_address=client_data["mac_address"],
                ip_address=client_data["ip_address"],
                hostname=client_data["hostname"],
                switch_hostname=client_data["switch_hostname"],
                interface_name=client_data["interface_name"],
                vlan_id=client_data["vlan_id"],
                speed=client_data["speed"],
                duplex=client_data["duplex"],
                link_status=client_data["link_status"],
                ping_reachable=client_data["ping_reachable"],
                ping_latency_ms=client_data["ping_latency_ms"],
                acl_rules_applied=client_data["acl_rules_applied"],
                acl_passes=client_data["acl_passes"],
                parsed_data=client_data,
            )
            session.add(record)
        
        await session.commit()
        
        print("\n✅ 客戶端測試數據創建完成！")
        print("\n客戶端統計:")
        print("  • client-01 ✅ - 全部正常")
        print("  • client-02 ❌ - Ping 延遲過高 (150.5ms > 100ms)")
        print("  • client-03 ❌ - Duplex 異常 (half 應為 full)")
        print("  • client-04 ❌ - Link 斷開")
        print("  • client-05 ✅ - 全部正常")
        print("\n預期通過率: 2/5 = 40%")
        print("=" * 70)


if __name__ == "__main__":
    asyncio.run(create_client_test_data())
