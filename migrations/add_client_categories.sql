-- ============================================
-- 新增機台種類表
-- ============================================
-- 用於客戶端比較頁面的機台分類功能
-- ============================================

-- 機台種類定義表
CREATE TABLE IF NOT EXISTS client_categories (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description VARCHAR(500),
    color VARCHAR(20) DEFAULT '#3B82F6',
    sort_order INT DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_is_active (is_active),
    INDEX idx_sort_order (sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 機台種類成員關聯表
CREATE TABLE IF NOT EXISTS client_category_members (
    id INT AUTO_INCREMENT PRIMARY KEY,
    category_id INT NOT NULL,
    mac_address VARCHAR(17) NOT NULL UNIQUE,
    description VARCHAR(200),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_category_id (category_id),
    INDEX idx_mac_address (mac_address),
    CONSTRAINT fk_category_member_category
        FOREIGN KEY (category_id) 
        REFERENCES client_categories(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- 插入預設種類（可選）
-- INSERT INTO client_categories (name, description, color, sort_order) VALUES
-- ('生產機台', '生產線上的機台設備', '#22C55E', 0),
-- ('測試機台', '測試環境的機台設備', '#3B82F6', 1),
-- ('不斷電機台', '歲修期間不關機的參考設備', '#A855F7', 2);
