-- =============================================================================
-- 新增 Checkpoint 和 Reference Client 功能
-- =============================================================================

-- Checkpoints 表：記錄歲修過程中的重要時間點
CREATE TABLE IF NOT EXISTS checkpoints (
    id INT AUTO_INCREMENT PRIMARY KEY,
    maintenance_id VARCHAR(100) NOT NULL,
    name VARCHAR(200) NOT NULL,
    checkpoint_time DATETIME(6) NOT NULL,
    description TEXT,
    summary_data JSON,
    created_by VARCHAR(100),
    created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    
    INDEX idx_maintenance_id (maintenance_id),
    INDEX idx_checkpoint_time (checkpoint_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Reference Clients 表：不斷電機台定義
CREATE TABLE IF NOT EXISTS reference_clients (
    id INT AUTO_INCREMENT PRIMARY KEY,
    mac_address VARCHAR(17) NOT NULL UNIQUE,
    description VARCHAR(200),
    location VARCHAR(200),
    reason TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    
    INDEX idx_mac_address (mac_address),
    INDEX idx_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Maintenance 配置表：存儲 anchor_time 等配置
CREATE TABLE IF NOT EXISTS maintenance_configs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    maintenance_id VARCHAR(100) NOT NULL UNIQUE,
    name VARCHAR(200),
    start_date DATE,
    end_date DATE,
    anchor_time DATETIME(6),
    config_data JSON,
    created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    
    INDEX idx_maintenance_id (maintenance_id),
    INDEX idx_anchor_time (anchor_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
