-- 為 ClientCategory 和 ClientCategoryMember 添加 maintenance_id 欄位
-- 讓分類變成歲修專屬

-- 1. 為 client_categories 表添加 maintenance_id 欄位
ALTER TABLE client_categories 
ADD COLUMN IF NOT EXISTS maintenance_id VARCHAR(100);

-- 2. 為 client_category_members 表添加 maintenance_id 欄位（冗餘但方便查詢）
ALTER TABLE client_category_members 
ADD COLUMN IF NOT EXISTS maintenance_id VARCHAR(100);

-- 3. 創建索引以優化查詢
CREATE INDEX IF NOT EXISTS idx_client_categories_maintenance 
ON client_categories(maintenance_id);

CREATE INDEX IF NOT EXISTS idx_client_category_members_maintenance 
ON client_category_members(maintenance_id);

-- 4. 更新現有數據（如果有的話，可以設為某個預設歲修 ID）
-- UPDATE client_categories SET maintenance_id = 'DEFAULT' WHERE maintenance_id IS NULL;
-- UPDATE client_category_members SET maintenance_id = 'DEFAULT' WHERE maintenance_id IS NULL;
