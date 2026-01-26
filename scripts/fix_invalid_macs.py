#!/usr/bin/env python3
"""
修復數據庫中不合法的 MAC 地址格式。

將所有不符合 XX:XX:XX:XX:XX:XX 格式的 MAC 地址替換為有效的 MAC 地址。
"""
import sys
import re
from pathlib import Path

# 添加項目根目錄到 Python 路徑
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
from sqlalchemy import select, update
from app.db.base import get_session_context
from app.db.models import MaintenanceMacList


def is_valid_mac(mac: str) -> bool:
    """檢查 MAC 地址格式是否有效。"""
    mac_pattern = re.compile(r'^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$')
    return bool(mac_pattern.match(mac))


def generate_valid_mac(invalid_mac: str) -> str:
    """
    根據不合法的 MAC 生成一個有效的 MAC 地址。

    嘗試修復常見錯誤：
    - 將非十六進制字符替換為有效字符
    - 保持原始 MAC 的部分結構（如果可能）
    """
    # 移除所有分隔符
    mac_parts = invalid_mac.replace(':', '').replace('-', '')

    # 替換非十六進制字符
    valid_chars = []
    for char in mac_parts:
        if char in '0123456789ABCDEFabcdef':
            valid_chars.append(char.upper())
        else:
            # 將非法字符映射到十六進制
            # A-Z, a-z 映射到 0-F
            if char.isalpha():
                # 使用字符的 ASCII 值模 16
                valid_chars.append(format(ord(char.upper()) % 16, 'X'))
            else:
                valid_chars.append('0')

    # 確保有 12 個字符
    if len(valid_chars) < 12:
        valid_chars.extend(['0'] * (12 - len(valid_chars)))
    elif len(valid_chars) > 12:
        valid_chars = valid_chars[:12]

    # 組裝成標準格式
    mac_str = ''.join(valid_chars)
    return ':'.join([mac_str[i:i+2] for i in range(0, 12, 2)])


async def fix_invalid_macs():
    """修復數據庫中所有不合法的 MAC 地址。"""
    print("=" * 60)
    print("修復數據庫中不合法的 MAC 地址")
    print("=" * 60)

    async with get_session_context() as session:
        # 查詢所有 MAC 地址
        stmt = select(MaintenanceMacList)
        result = await session.execute(stmt)
        all_macs = result.scalars().all()

        print(f"\n找到 {len(all_macs)} 筆 MAC 地址記錄")

        # 找出不合法的 MAC
        invalid_macs = []
        for mac_record in all_macs:
            if not is_valid_mac(mac_record.mac_address):
                invalid_macs.append(mac_record)

        if not invalid_macs:
            print("\n✅ 所有 MAC 地址格式都正確！")
            return

        print(f"\n⚠️  發現 {len(invalid_macs)} 筆不合法的 MAC 地址：")
        print("-" * 60)

        # 顯示並修復每個不合法的 MAC
        fixed_count = 0
        for mac_record in invalid_macs:
            old_mac = mac_record.mac_address
            new_mac = generate_valid_mac(old_mac)

            print(f"ID {mac_record.id}:")
            print(f"  舊 MAC: {old_mac}")
            print(f"  新 MAC: {new_mac}")
            print(f"  描述: {mac_record.description or '(無)'}")

            # 檢查新 MAC 是否已存在
            check_stmt = select(MaintenanceMacList).where(
                MaintenanceMacList.maintenance_id == mac_record.maintenance_id,
                MaintenanceMacList.mac_address == new_mac,
                MaintenanceMacList.id != mac_record.id
            )
            check_result = await session.execute(check_stmt)
            existing = check_result.scalar_one_or_none()

            if existing:
                # 如果新 MAC 已存在，生成一個唯一的
                base_mac = new_mac.replace(':', '')
                for i in range(1, 256):
                    # 修改最後一個字節
                    test_mac_str = base_mac[:10] + format(i, '02X')
                    test_mac = ':'.join([test_mac_str[j:j+2] for j in range(0, 12, 2)])

                    check_stmt2 = select(MaintenanceMacList).where(
                        MaintenanceMacList.maintenance_id == mac_record.maintenance_id,
                        MaintenanceMacList.mac_address == test_mac
                    )
                    check_result2 = await session.execute(check_stmt2)
                    if not check_result2.scalar_one_or_none():
                        new_mac = test_mac
                        print(f"  (調整) 新 MAC: {new_mac} (避免重複)")
                        break

            # 更新 MAC 地址
            mac_record.mac_address = new_mac
            fixed_count += 1
            print()

        # 提交更改
        await session.commit()

        print("=" * 60)
        print(f"✅ 成功修復 {fixed_count} 筆 MAC 地址！")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(fix_invalid_macs())
