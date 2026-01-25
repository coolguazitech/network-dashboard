#!/usr/bin/env python3
"""
執行 Uplink/Version 期望相關的 migration。
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "network_dashboard.db")

def run_migration():
    """執行 migration。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 讀取並執行 uplink/version expectations migration
    migration_file = os.path.join(
        os.path.dirname(__file__),
        "migrations",
        "add_uplink_version_expectations.sql"
    )
    
    with open(migration_file, 'r', encoding='utf-8') as f:
        sql = f.read()
    
    # 分開執行每個語句
    for statement in sql.split(';'):
        statement = statement.strip()
        if statement:
            try:
                cursor.execute(statement)
                print(f"✓ 執行: {statement[:60]}...")
            except sqlite3.Error as e:
                print(f"⚠ 跳過或錯誤: {e}")
    
    # 讀取並執行 arp/portchannel migration
    arp_migration_file = os.path.join(
        os.path.dirname(__file__),
        "migrations",
        "add_arp_portchannel_expectations.sql"
    )
    
    if os.path.exists(arp_migration_file):
        with open(arp_migration_file, 'r', encoding='utf-8') as f:
            sql = f.read()
        
        for statement in sql.split(';'):
            statement = statement.strip()
            if statement:
                try:
                    cursor.execute(statement)
                    print(f"✓ 執行: {statement[:60]}...")
                except sqlite3.Error as e:
                    print(f"⚠ 跳過或錯誤: {e}")
    
    conn.commit()
    conn.close()
    print("\n✅ Migration 完成！")


if __name__ == "__main__":
    run_migration()
