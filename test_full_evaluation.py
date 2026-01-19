"""
完整評估流程測試。

1. 準備 POST phase 測試數據
2. 運行所有指標評估器
3. 驗證結果
"""
import asyncio
from datetime import datetime

from sqlalchemy import select

from app.core.enums import MaintenancePhase, PlatformType, VendorType
from app.db.base import get_session_context
from app.db.models import CollectionRecord
from app.services.indicator_service import IndicatorService
from app.parsers.registry import auto_discover_parsers


async def prepare_test_data(session) -> None:
    """準備 POST phase 測試數據。"""
    
    print("\n[準備數據] 創建 POST phase 測試數據...")
    
    # 測試光模塊數據 - 部分失敗
    transceiver_data = [
        {
            "interface_name": "Ethernet1/1",
            "tx_power": -15.3,  # ❌ 低於閾值 (-12)
            "rx_power": -2.45,
            "temperature": 30.0,
            "voltage": 3.28,
            "serial_number": "FNS001",
            "part_number": "FTLX8571D3BCL",
        },
        {
            "interface_name": "Ethernet1/2",
            "tx_power": -1.0,   # ✅ 正常
            "rx_power": -2.0,
            "temperature": 28.0,
            "voltage": 3.30,
            "serial_number": "FNS002",
            "part_number": "FTLX8571D3BCL",
        },
        {
            "interface_name": "Ethernet1/3",
            "tx_power": -0.5,   # ✅ 正常
            "rx_power": -20.5,  # ❌ 低於閾值 (-18)
            "temperature": 29.0,
            "voltage": 3.29,
            "serial_number": "FNS003",
            "part_number": "FTLX8571D3BCL",
        },
    ]
    
    record1 = CollectionRecord(
        indicator_type="transceiver",
        switch_hostname="switch-new-01",
        phase=MaintenancePhase.POST,
        maintenance_id="2026Q1-ANNUAL",
        raw_data="[mock raw data]",
        parsed_data=transceiver_data,
        collected_at=datetime.now(),
    )
    session.add(record1)
    
    # 測試版本數據 - 全部通過
    version_data = {
        "version": "9.3(10)",
        "model": "N9K-C9336C-FX2",
    }
    
    record2 = CollectionRecord(
        indicator_type="version",
        switch_hostname="switch-new-01",
        phase=MaintenancePhase.POST,
        maintenance_id="2026Q1-ANNUAL",
        raw_data="[mock raw data]",
        parsed_data=version_data,
        collected_at=datetime.now(),
    )
    session.add(record2)
    
    # 測試 uplink 數據 - 部分異常
    uplink_data = [
        {
            "local_interface": "Ethernet1/49",
            "remote_hostname": "spine-01",
            "remote_interface": "Ethernet1/1",
        },
        {
            "local_interface": "Ethernet1/50",
            "remote_hostname": "spine-02",  # ❌ 期望是 spine-02，但實際是 spine-03
            "remote_interface": "Ethernet1/2",
        },
    ]
    
    record3 = CollectionRecord(
        indicator_type="uplink",
        switch_hostname="switch-new-01",
        phase=MaintenancePhase.POST,
        maintenance_id="2026Q1-ANNUAL",
        raw_data="[mock raw data]",
        parsed_data=uplink_data,
        collected_at=datetime.now(),
    )
    session.add(record3)
    
    await session.commit()
    print("✅ 測試數據創建完成")


async def test_evaluation():
    """運行完整的評估測試。"""
    
    print("=" * 70)
    print("🧪 完整評估測試")
    print("=" * 70)
    
    # 初始化 parsers
    auto_discover_parsers()
    
    async with get_session_context() as session:
        # 準備測試數據
        await prepare_test_data(session)
        
        # 運行評估
        print("\n[評估中] 運行所有指標評估器...")
        service = IndicatorService()
        
        # 獲取摘要
        summary = await service.get_dashboard_summary(
            "2026Q1-ANNUAL",
            session
        )
        
        print("\n" + "=" * 70)
        print("📊 評估結果摘要")
        print("=" * 70)
        print(f"維護作業 ID: {summary['maintenance_id']}")
        print(f"\n整體統計:")
        print(f"  總項目數: {summary['overall']['total_count']}")
        print(f"  通過: {summary['overall']['pass_count']}")
        print(f"  失敗: {summary['overall']['fail_count']}")
        print(f"  通過率: {summary['overall']['pass_rate']:.1f}%")
        
        print(f"\n各指標詳情:")
        for indicator_type, stats in summary["indicators"].items():
            status = "✅" if stats["fail_count"] == 0 else "❌"
            print(f"\n  {status} {indicator_type.upper()}")
            print(f"    通過率: {stats['pass_rate']:.1f}% "
                  f"({stats['pass_count']}/{stats['total_count']})")
            print(f"    摘要: {stats['summary']}")
        
        # 獲取詳細結果
        print("\n" + "=" * 70)
        print("📋 詳細失敗清單")
        print("=" * 70)
        
        results = await service.evaluate_all("2026Q1-ANNUAL", session)
        
        for indicator_type, result in results.items():
            if result.failures:
                print(f"\n{indicator_type.upper()} - 失敗項目:")
                for failure in result.failures:
                    print(f"  • {failure['device']}")
                    if "interface" in failure:
                        print(f"    接口: {failure['interface']}")
                    print(f"    原因: {failure['reason']}")


if __name__ == "__main__":
    asyncio.run(test_evaluation())
