-- Migration: Add vendor column to device_mappings table
-- Description: 新增 vendor 欄位到設備對應表，用於記錄設備廠商（HPE, Cisco-IOS, Cisco-NXOS）
-- Date: 2026-01-24

-- Add vendor column with default value 'HPE'
ALTER TABLE device_mappings 
ADD COLUMN IF NOT EXISTS vendor VARCHAR(50) NOT NULL DEFAULT 'HPE';

-- Add comment for vendor column
COMMENT ON COLUMN device_mappings.vendor IS '設備廠商（HPE, Cisco-IOS, Cisco-NXOS）';

-- Verify the column was added
SELECT column_name, data_type, column_default, is_nullable
FROM information_schema.columns
WHERE table_name = 'device_mappings' AND column_name = 'vendor';
