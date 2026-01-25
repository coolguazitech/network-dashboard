-- 新增歲修設備清單表
-- 用於管理歲修涉及的所有設備及其對應關係

CREATE TABLE IF NOT EXISTS maintenance_device_list (
    id INT AUTO_INCREMENT PRIMARY KEY,
    maintenance_id VARCHAR(100) NOT NULL,
    hostname VARCHAR(255) NOT NULL,
    ip_address VARCHAR(45) NULL,
    vendor VARCHAR(50) NULL,
    platform VARCHAR(50) NULL,
    role ENUM('old', 'new', 'unchanged') NOT NULL DEFAULT 'old',
    mapped_to VARCHAR(255) NULL COMMENT '對應的設備 hostname（old→new 或 new→old）',
    use_same_port BOOLEAN DEFAULT TRUE COMMENT '是否同埠對應',
    is_reachable BOOLEAN NULL COMMENT '可達性狀態（NULL=未檢查）',
    last_check_at DATETIME NULL COMMENT '最後檢查時間',
    description VARCHAR(500) NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    
    -- 索引
    INDEX idx_maintenance_id (maintenance_id),
    INDEX idx_hostname (hostname),
    INDEX idx_role (role),
    
    -- 唯一約束：同一歲修中設備名稱不可重複
    UNIQUE KEY uk_maintenance_hostname (maintenance_id, hostname)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
