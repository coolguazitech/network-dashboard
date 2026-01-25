-- Migration: 允許同一 MAC 屬於多個分類
-- 日期: 2026-01-22
-- 說明: 移除 mac_address 的 unique 約束，允許多對多關係

-- 移除 mac_address 欄位的 unique 約束
-- MySQL 需要先刪除索引才能移除約束
ALTER TABLE client_category_members DROP INDEX mac_address;

-- 重新創建普通索引（非唯一）
CREATE INDEX idx_client_category_members_mac ON client_category_members(mac_address);

-- 添加組合唯一約束：同一分類中不能重複添加同一 MAC
ALTER TABLE client_category_members 
ADD CONSTRAINT uq_category_mac UNIQUE (category_id, mac_address);
