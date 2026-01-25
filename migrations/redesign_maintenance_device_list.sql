-- Migration: 重新設計 maintenance_device_list 表結構
-- 將每筆資料改為包含新舊設備對應
-- 執行前請備份現有資料

-- 備份現有資料
DROP TABLE IF EXISTS maintenance_device_list_backup;
CREATE TABLE maintenance_device_list_backup AS SELECT * FROM maintenance_device_list;

-- 刪除舊表
DROP TABLE IF EXISTS maintenance_device_list;

-- 建立新表
CREATE TABLE maintenance_device_list (
    id INT AUTO_INCREMENT PRIMARY KEY,
    maintenance_id VARCHAR(100) NOT NULL,
    old_hostname VARCHAR(255) NOT NULL,
    old_ip_address VARCHAR(45) NOT NULL,
    old_vendor VARCHAR(50) NOT NULL,
    new_hostname VARCHAR(255) NOT NULL,
    new_ip_address VARCHAR(45) NOT NULL,
    new_vendor VARCHAR(50) NOT NULL,
    use_same_port BOOLEAN DEFAULT TRUE,
    is_reachable BOOLEAN,
    last_check_at DATETIME,
    description VARCHAR(500),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT uk_maintenance_old_hostname UNIQUE (maintenance_id, old_hostname)
);

-- 建立索引
CREATE INDEX ix_maint_dev_list_maintenance ON maintenance_device_list(maintenance_id);
CREATE INDEX ix_maint_dev_list_old_host ON maintenance_device_list(old_hostname);
CREATE INDEX ix_maint_dev_list_new_host ON maintenance_device_list(new_hostname);
