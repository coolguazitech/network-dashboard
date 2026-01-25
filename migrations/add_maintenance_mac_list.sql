-- 歲修 MAC 清單表
-- 存放該歲修的全部待追蹤 MAC 地址（獨立於分類）
-- 用戶先匯入全部 MAC，之後可選擇性地將部分 MAC 分到特定分類

CREATE TABLE IF NOT EXISTS maintenance_mac_list (
    id INT AUTO_INCREMENT PRIMARY KEY,
    maintenance_id VARCHAR(50) NOT NULL COMMENT '歲修 ID',
    mac_address VARCHAR(17) NOT NULL COMMENT 'MAC 地址（標準化格式 XX:XX:XX:XX:XX:XX）',
    description VARCHAR(255) DEFAULT NULL COMMENT '備註/機台名稱',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- 同一歲修下 MAC 不能重複
    UNIQUE KEY uk_maintenance_mac (maintenance_id, mac_address),
    -- 索引
    INDEX idx_maintenance (maintenance_id),
    INDEX idx_mac (mac_address)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
COMMENT='歲修 MAC 清單 - 該歲修涉及的全部設備 MAC';
