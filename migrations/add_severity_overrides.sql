-- 手動覆蓋嚴重程度表
-- 允許用戶手動覆蓋某個 MAC 的嚴重程度判定

CREATE TABLE IF NOT EXISTS client_severity_overrides (
    id SERIAL PRIMARY KEY,
    maintenance_id VARCHAR(50) NOT NULL,
    mac_address VARCHAR(20) NOT NULL,
    override_severity VARCHAR(20) NOT NULL,  -- 'critical', 'warning', 'info', 'undetected'
    original_severity VARCHAR(20),           -- 保存原本的自動判斷值
    note TEXT,                               -- 用戶備註
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(maintenance_id, mac_address)
);

-- 索引加速查詢
CREATE INDEX IF NOT EXISTS idx_severity_overrides_maintenance 
ON client_severity_overrides(maintenance_id);

CREATE INDEX IF NOT EXISTS idx_severity_overrides_mac 
ON client_severity_overrides(mac_address);
