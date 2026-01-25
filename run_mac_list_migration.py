#!/usr/bin/env python3
"""執行 MAC 清單表格遷移。"""
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

sql = """
CREATE TABLE IF NOT EXISTS maintenance_mac_list (
    id INT AUTO_INCREMENT PRIMARY KEY,
    maintenance_id VARCHAR(50) NOT NULL COMMENT '歲修 ID',
    mac_address VARCHAR(17) NOT NULL COMMENT 'MAC 地址',
    description VARCHAR(255) DEFAULT NULL COMMENT '備註',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_maintenance_mac (maintenance_id, mac_address),
    INDEX idx_maintenance (maintenance_id),
    INDEX idx_mac (mac_address)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

try:
    cursor.execute(sql)
    conn.commit()
    print('✅ 表格 maintenance_mac_list 已創建')
except Exception as e:
    print(f'❌ 錯誤: {e}')

cursor.close()
conn.close()
