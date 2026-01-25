import asyncio
import json
from app.db.base import get_session_context
from app.services.indicator_service import IndicatorService
from app.db.models import CollectionRecord, MaintenanceConfig, MaintenanceDeviceList, PortChannelExpectation
from app.core.enums import MaintenancePhase
from datetime import datetime

async def verify():
    async with get_session_context() as session:
        maintenance_id = "TEST-VERIFY"
        
        # 1. 建立測試維護作業
        # config = MaintenanceConfig(maintenance_id=maintenance_id, name="Verify New Indicators")
        # session.add(config)
        
        # 2. 建立 Port-Channel 期望
        exp = PortChannelExpectation(
            maintenance_id=maintenance_id,
            hostname="SW-TEST",
            port_channel="Po1",
            member_interfaces="Eth1/1;Eth1/2",
            description="Test PC"
        )
        session.add(exp)
        
        # 3. 模擬 Port-Channel 採集數據
        pc_data = [
            {
                "interface_name": "Po1",
                "status": "UP",
                "protocol": "LACP",
                "members": ["Eth1/1", "Eth1/2"],
                "member_status": {"Eth1/1": "UP", "Eth1/2": "UP"}
            }
        ]
        
        rec_pc = CollectionRecord(
            indicator_type="port_channel",
            switch_hostname="SW-TEST",
            phase=MaintenancePhase.NEW,
            maintenance_id=maintenance_id,
            parsed_data=pc_data,
            collected_at=datetime.now()
        )
        session.add(rec_pc)
        
        # 4. 模擬 Power 採集數據
        power_data = [
            {
                "ps_id": "1",
                "status": "Ok",
                "capacity_watts": 650.0,
                "actual_output_watts": 100.0
            },
            {
                "ps_id": "2",
                "status": "Fail",  # 模擬一個失敗
                "capacity_watts": 650.0,
                "actual_output_watts": 0.0
            }
        ]
        
        rec_power = CollectionRecord(
            indicator_type="power",
            switch_hostname="SW-TEST",
            phase=MaintenancePhase.NEW,
            maintenance_id=maintenance_id,
            parsed_data=power_data,
            collected_at=datetime.now()
        )
        session.add(rec_power)

        # 5. 模擬 Fan 採集數據
        fan_data = [
            {"fan_id": "Fan1", "status": "Ok"},
            {"fan_id": "Fan2", "status": "Fail"}
        ]
        rec_fan = CollectionRecord(
            indicator_type="fan",
            switch_hostname="SW-TEST",
            phase=MaintenancePhase.NEW,
            maintenance_id=maintenance_id,
            parsed_data=fan_data,
            collected_at=datetime.now()
        )
        session.add(rec_fan)

        # 6. 模擬 Error Count 採集數據
        error_data = [
            {"interface_name": "Eth1/1", "crc_errors": 0, "input_errors": 0, "output_errors": 0},
            {"interface_name": "Eth1/2", "crc_errors": 10, "input_errors": 5, "output_errors": 0}
        ]
        rec_error = CollectionRecord(
            indicator_type="error_count",
            switch_hostname="SW-TEST",
            phase=MaintenancePhase.NEW,
            maintenance_id=maintenance_id,
            parsed_data=error_data,
            collected_at=datetime.now()
        )
        session.add(rec_error)

        # 7. 模擬 Ping 採集數據
        ping_data = [
            {"target": "self", "is_reachable": True, "success_rate": 100.0, "avg_rtt_ms": 1.5}
        ]
        rec_ping = CollectionRecord(
            indicator_type="ping",
            switch_hostname="SW-TEST",
            phase=MaintenancePhase.NEW,
            maintenance_id=maintenance_id,
            parsed_data=ping_data,
            collected_at=datetime.now()
        )
        session.add(rec_ping)
        
        await session.commit()
        
        # 8. 執行評估
        service = IndicatorService()
        results = await service.evaluate_all(maintenance_id, session)
        
        print("\n=== Evaluation Results ===")
        for key in ["port_channel", "power", "fan", "error_count", "ping"]:
            res = results.get(key)
            if res:
                print(f"{key.title()}: {res.summary}")
                if res.failures:
                    print("  Failures:", json.dumps(res.failures, indent=2, default=str))
            else:
                print(f"{key.title()}: No result")

if __name__ == "__main__":
    asyncio.run(verify())
