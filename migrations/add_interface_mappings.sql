-- 創建連接埠對應表
CREATE TABLE IF NOT EXISTS interface_mappings (
    id INT AUTO_INCREMENT PRIMARY KEY,
    maintenance_id VARCHAR(100) NOT NULL,
    old_hostname VARCHAR(255) NOT NULL,
    old_interface VARCHAR(100) NOT NULL,
    new_hostname VARCHAR(255) NOT NULL,
    new_interface VARCHAR(100) NOT NULL,
    description VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_maintenance_id (maintenance_id),
    INDEX idx_old_hostname (old_hostname),
    INDEX idx_new_hostname (new_hostname)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
