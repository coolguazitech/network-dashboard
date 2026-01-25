-- 為設備對應表增加同名port對應欄位
-- use_same_port: 是否啟用同名port對應（預設 True）

ALTER TABLE device_mappings 
ADD COLUMN use_same_port BOOLEAN DEFAULT TRUE 
COMMENT '是否啟用同名port對應';

-- 更新現有記錄，設為 True
UPDATE device_mappings SET use_same_port = TRUE WHERE use_same_port IS NULL;
