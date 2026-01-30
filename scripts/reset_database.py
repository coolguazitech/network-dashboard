#!/usr/bin/env python3
"""
資料庫重置腳本

清空所有資料，讓系統回到初始狀態。
用於測試前的環境準備。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def reset_database(confirm: bool = False):
    """重置資料庫"""
    print("\n" + "=" * 60)
    print("資料庫重置工具")
    print("=" * 60)

    if not confirm:
        print("\n⚠️  警告: 此操作會刪除所有資料！")
        print("\n將清空以下資料表:")
        print("  - Maintenance (歲修 ID)")
        print("  - MaintenanceMacList (MAC 清單)")
        print("  - MaintenanceDevice (設備對應)")
        print("  - ClientRecord (客戶端記錄)")
        print("  - Category / CategoryMember (分類)")
        print("  - UplinkExpectation / VersionExpectation / ArpSourceDevice")
        print("  - PortChannelExpectation")
        print("  - Checkpoint")
        print("  - ClientComparison / SeverityOverride")
        print("  - IndicatorResult")
        print("  - ReferenceClient")

        user_input = input("\n輸入 'yes' 確認刪除所有資料: ")
        if user_input.lower() != 'yes':
            print("取消操作")
            return

    print("\n開始清空資料庫...")

    from sqlalchemy import text
    from app.db.base import get_session_context

    # 要清空的資料表（按順序，處理外鍵關係）
    tables_to_clear = [
        # 先刪除有外鍵依賴的表
        "category_member",
        "severity_override",
        "client_comparison",
        "indicator_result",
        "checkpoint",
        "client_record",
        "uplink_expectation",
        "version_expectation",
        "arp_source_device",
        "port_channel_expectation",
        "reference_client",
        "category",
        "maintenance_mac_list",
        "maintenance_device",
        # 最後刪除主表
        "maintenance",
    ]

    async with get_session_context() as session:
        for table in tables_to_clear:
            try:
                # 使用 DELETE 而不是 TRUNCATE，更安全
                result = await session.execute(text(f"DELETE FROM {table}"))
                count = result.rowcount
                await session.commit()
                if count > 0:
                    print(f"  ✓ {table}: 刪除 {count} 筆")
                else:
                    print(f"  - {table}: 無資料")
            except Exception as e:
                print(f"  ✗ {table}: 錯誤 - {e}")
                await session.rollback()

    print("\n✓ 資料庫清空完成")
    print("=" * 60)


async def show_database_status():
    """顯示資料庫狀態"""
    print("\n" + "=" * 60)
    print("資料庫狀態")
    print("=" * 60)

    from sqlalchemy import text, func, select
    from app.db.base import get_session_context

    tables_to_check = [
        ("maintenance", "歲修 ID"),
        ("maintenance_mac_list", "MAC 清單"),
        ("maintenance_device", "設備對應"),
        ("client_record", "客戶端記錄"),
        ("category", "分類"),
        ("uplink_expectation", "Uplink 期望"),
        ("version_expectation", "版本期望"),
        ("arp_source_device", "ARP 來源"),
        ("checkpoint", "檢查點"),
        ("client_comparison", "比較結果"),
    ]

    async with get_session_context() as session:
        print("\n資料表記錄數:")
        for table, name in tables_to_check:
            try:
                result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
                count = result.scalar()
                print(f"  {name:15} ({table}): {count}")
            except Exception as e:
                print(f"  {name:15} ({table}): 錯誤 - {e}")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="資料庫重置工具")
    parser.add_argument(
        "--status",
        action="store_true",
        help="只顯示資料庫狀態，不刪除資料",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="強制執行，不需確認",
    )

    args = parser.parse_args()

    if args.status:
        asyncio.run(show_database_status())
    else:
        asyncio.run(reset_database(confirm=args.force))
