-- Uplink 期望表
CREATE TABLE IF NOT EXISTS uplink_expectations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    maintenance_id VARCHAR(100) NOT NULL,
    hostname VARCHAR(100) NOT NULL,
    local_interface VARCHAR(50) NOT NULL,
    expected_neighbor VARCHAR(100) NOT NULL,
    expected_interface VARCHAR(50),
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (maintenance_id) REFERENCES maintenance(id) ON DELETE CASCADE
);

-- Uplink 期望索引
CREATE INDEX IF NOT EXISTS idx_uplink_exp_maintenance ON uplink_expectations(maintenance_id);
CREATE INDEX IF NOT EXISTS idx_uplink_exp_hostname ON uplink_expectations(hostname);

-- 版本期望表
CREATE TABLE IF NOT EXISTS version_expectations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    maintenance_id VARCHAR(100) NOT NULL,
    hostname VARCHAR(100) NOT NULL,
    expected_versions TEXT NOT NULL,  -- 用分號分隔多個版本，例如 "16.10.1;16.10.2;16.11.1"
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (maintenance_id) REFERENCES maintenance(id) ON DELETE CASCADE
);

-- 版本期望索引
CREATE INDEX IF NOT EXISTS idx_version_exp_maintenance ON version_expectations(maintenance_id);
CREATE INDEX IF NOT EXISTS idx_version_exp_hostname ON version_expectations(hostname);
