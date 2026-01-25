-- 移除 ping_latency_ms 和 hostname 欄位
-- 執行此遷移前請先備份資料庫

-- 移除 client_records 表的 ping_latency_ms 和 hostname 欄位
ALTER TABLE client_records DROP COLUMN IF EXISTS ping_latency_ms;
ALTER TABLE client_records DROP COLUMN IF EXISTS hostname;

-- 移除 client_comparisons 表的 ping_latency_ms 和 hostname 欄位
ALTER TABLE client_comparisons DROP COLUMN IF EXISTS pre_ping_latency_ms;
ALTER TABLE client_comparisons DROP COLUMN IF EXISTS pre_hostname;
ALTER TABLE client_comparisons DROP COLUMN IF EXISTS post_ping_latency_ms;
ALTER TABLE client_comparisons DROP COLUMN IF EXISTS post_hostname;
