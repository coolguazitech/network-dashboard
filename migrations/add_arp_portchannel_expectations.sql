-- ARP 來源資料表
CREATE TABLE IF NOT EXISTS arp_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    maintenance_id TEXT NOT NULL,
    hostname TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    priority INTEGER DEFAULT 100,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(maintenance_id, hostname),
    FOREIGN KEY (maintenance_id) REFERENCES maintenances(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_arp_sources_maintenance ON arp_sources(maintenance_id);

-- Port-Channel 期望資料表
CREATE TABLE IF NOT EXISTS port_channel_expectations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    maintenance_id TEXT NOT NULL,
    hostname TEXT NOT NULL,
    port_channel TEXT NOT NULL,
    member_interfaces TEXT NOT NULL,  -- 分號分隔的實體介面清單
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(maintenance_id, hostname, port_channel),
    FOREIGN KEY (maintenance_id) REFERENCES maintenances(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_port_channel_exp_maintenance ON port_channel_expectations(maintenance_id);
CREATE INDEX IF NOT EXISTS idx_port_channel_exp_hostname ON port_channel_expectations(maintenance_id, hostname);
