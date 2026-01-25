#!/usr/bin/env python3
"""將 snapshot_clients 中的 MAC 同步到 maintenance_mac_list 表。"""
import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

conn = pymysql.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=int(os.getenv('DB_PORT', 3306)),
    user=os.getenv('DB_USER', 'root'),
    password=os.getenv('DB_PASSWORD', ''),
    database=os.getenv('DB_NAME', 'network_dashboard'),
    charset='utf8mb4'
)

cursor = conn.cursor()

# 查詢 client_comparisons 中所有歲修和 MAC
query = """
SELECT DISTINCT maintenance_id, mac_address
FROM client_comparisons
WHERE mac_address IS NOT NULL AND mac_address != ''
ORDER BY maintenance_id, mac_address
"""

cursor.execute(query)
rows = cursor.fetchall()

print(f'找到 {len(rows)} 筆記錄')

# 插入到 maintenance_mac_list（忽略重複）
insert_sql = """
INSERT IGNORE INTO maintenance_mac_list (maintenance_id, mac_address, description)
VALUES (%s, %s, NULL)
"""

inserted = 0
for maintenance_id, mac_address in rows:
    # 標準化 MAC 格式
    mac = mac_address.strip().upper().replace('-', ':')
    cursor.execute(insert_sql, (maintenance_id, mac))
    if cursor.rowcount > 0:
        inserted += 1

conn.commit()
print(f'✅ 已同步 {inserted} 筆 MAC 到 maintenance_mac_list')

# 顯示統計
cursor.execute("""
SELECT maintenance_id, COUNT(*) 
FROM maintenance_mac_list 
GROUP BY maintenance_id
""")
stats = cursor.fetchall()
for m_id, count in stats:
    print(f'  - {m_id}: {count} 筆')

cursor.close()
conn.close()
