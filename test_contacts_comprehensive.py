#!/usr/bin/env python3
"""
通訊錄功能綜合測試腳本
測試項目：
1. 聯絡人 CRUD
2. 分類 CRUD
3. 刪除分類後聯絡人變未分類
4. 批量刪除
5. 批量修改分類
6. null category_id 情境
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000/api/v1"
MAINTENANCE_ID = "M001"  # 測試用的歲修 ID

# 顏色輸出
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    END = '\033[0m'

def log_pass(msg):
    print(f"{Colors.GREEN}✓ PASS{Colors.END}: {msg}")

def log_fail(msg):
    print(f"{Colors.RED}✗ FAIL{Colors.END}: {msg}")

def log_info(msg):
    print(f"{Colors.CYAN}ℹ INFO{Colors.END}: {msg}")

def log_section(msg):
    print(f"\n{Colors.YELLOW}{'='*50}{Colors.END}")
    print(f"{Colors.YELLOW}  {msg}{Colors.END}")
    print(f"{Colors.YELLOW}{'='*50}{Colors.END}")


# ============================================================
# 測試 1: 分類 CRUD
# ============================================================
def test_category_crud():
    log_section("測試 1: 分類 CRUD")

    # 1.1 新增分類
    log_info("1.1 新增分類 '測試分類A'")
    resp = requests.post(f"{BASE_URL}/contacts/categories", json={
        "maintenance_id": MAINTENANCE_ID,
        "name": "測試分類A",
        "color": "#22d3ee"
    })
    if resp.status_code == 200:
        cat_a = resp.json()
        log_pass(f"分類建立成功, id={cat_a['id']}")
    else:
        log_fail(f"分類建立失敗: {resp.status_code} - {resp.text}")
        return None

    # 1.2 新增第二個分類
    log_info("1.2 新增分類 '測試分類B'")
    resp = requests.post(f"{BASE_URL}/contacts/categories", json={
        "maintenance_id": MAINTENANCE_ID,
        "name": "測試分類B",
        "color": "#ef4444"
    })
    if resp.status_code == 200:
        cat_b = resp.json()
        log_pass(f"分類建立成功, id={cat_b['id']}")
    else:
        log_fail(f"分類建立失敗: {resp.status_code} - {resp.text}")
        return None

    # 1.3 讀取分類列表
    log_info("1.3 讀取分類列表")
    resp = requests.get(f"{BASE_URL}/contacts/categories/{MAINTENANCE_ID}")
    if resp.status_code == 200:
        categories = resp.json()
        test_cats = [c for c in categories if c['name'] in ['測試分類A', '測試分類B']]
        if len(test_cats) >= 2:
            log_pass(f"分類列表讀取成功，找到 {len(test_cats)} 個測試分類")
        else:
            log_fail(f"分類列表不完整")
    else:
        log_fail(f"分類列表讀取失敗: {resp.status_code}")

    # 1.4 編輯分類
    log_info("1.4 編輯分類名稱")
    resp = requests.put(f"{BASE_URL}/contacts/categories/{cat_a['id']}", json={
        "name": "測試分類A-已修改",
        "color": "#10b981"
    })
    if resp.status_code == 200:
        updated = resp.json()
        if updated['name'] == "測試分類A-已修改":
            log_pass("分類編輯成功")
        else:
            log_fail("分類名稱未更新")
    else:
        log_fail(f"分類編輯失敗: {resp.status_code}")

    return {"cat_a": cat_a, "cat_b": cat_b}


# ============================================================
# 測試 2: 聯絡人 CRUD
# ============================================================
def test_contact_crud(categories):
    log_section("測試 2: 聯絡人 CRUD")

    cat_a_id = categories['cat_a']['id']

    # 2.1 新增有分類的聯絡人
    log_info("2.1 新增聯絡人（有分類）")
    resp = requests.post(f"{BASE_URL}/contacts/{MAINTENANCE_ID}", json={
        "name": "測試人員A",
        "title": "工程師",
        "company": "測試公司",
        "phone": "02-12345678",
        "mobile": "0912345678",
        "email": "test_a@example.com",
        "category_id": cat_a_id
    })
    if resp.status_code == 200:
        contact_a = resp.json()
        log_pass(f"聯絡人建立成功, id={contact_a['id']}")
        if contact_a.get('category_id') == cat_a_id:
            log_pass("category_id 正確")
        else:
            log_fail(f"category_id 錯誤: expected {cat_a_id}, got {contact_a.get('category_id')}")
    else:
        log_fail(f"聯絡人建立失敗: {resp.status_code} - {resp.text}")
        return None

    # 2.2 新增無分類的聯絡人（測試 null category_id）
    log_info("2.2 新增聯絡人（無分類 - null category_id）")
    resp = requests.post(f"{BASE_URL}/contacts/{MAINTENANCE_ID}", json={
        "name": "測試人員B",
        "title": "PM",
        "company": "測試公司",
        "phone": "02-87654321",
        "mobile": "0987654321",
        "email": "test_b@example.com",
        "category_id": None
    })
    if resp.status_code == 200:
        contact_b = resp.json()
        log_pass(f"無分類聯絡人建立成功, id={contact_b['id']}")
        if contact_b.get('category_id') is None:
            log_pass("category_id 正確為 null")
        else:
            log_fail(f"category_id 應為 null，實際為 {contact_b.get('category_id')}")
    else:
        log_fail(f"無分類聯絡人建立失敗: {resp.status_code} - {resp.text}")
        return None

    # 2.3 新增第三個聯絡人（用於批量測試）
    log_info("2.3 新增第三個聯絡人")
    resp = requests.post(f"{BASE_URL}/contacts/{MAINTENANCE_ID}", json={
        "name": "測試人員C",
        "title": "設計師",
        "company": "測試公司C",
        "email": "test_c@example.com",
        "category_id": cat_a_id
    })
    if resp.status_code == 200:
        contact_c = resp.json()
        log_pass(f"聯絡人建立成功, id={contact_c['id']}")
    else:
        log_fail(f"聯絡人建立失敗: {resp.status_code} - {resp.text}")
        return None

    # 2.4 讀取聯絡人列表
    log_info("2.4 讀取聯絡人列表")
    resp = requests.get(f"{BASE_URL}/contacts/{MAINTENANCE_ID}")
    if resp.status_code == 200:
        contacts = resp.json()
        test_contacts = [c for c in contacts if c['name'].startswith('測試人員')]
        log_pass(f"聯絡人列表讀取成功，找到 {len(test_contacts)} 個測試聯絡人")
    else:
        log_fail(f"聯絡人列表讀取失敗: {resp.status_code}")

    # 2.5 編輯聯絡人
    log_info("2.5 編輯聯絡人")
    resp = requests.put(f"{BASE_URL}/contacts/{MAINTENANCE_ID}/{contact_a['id']}", json={
        "name": "測試人員A-已修改",
        "title": "資深工程師"
    })
    if resp.status_code == 200:
        updated = resp.json()
        if updated['name'] == "測試人員A-已修改" and updated['title'] == "資深工程師":
            log_pass("聯絡人編輯成功")
        else:
            log_fail("聯絡人資料未正確更新")
    else:
        log_fail(f"聯絡人編輯失敗: {resp.status_code}")

    return {"contact_a": contact_a, "contact_b": contact_b, "contact_c": contact_c}


# ============================================================
# 測試 3: 刪除分類後聯絡人變未分類
# ============================================================
def test_category_delete_cascade(categories, contacts):
    log_section("測試 3: 刪除分類後聯絡人變未分類")

    cat_a_id = categories['cat_a']['id']
    contact_a_id = contacts['contact_a']['id']

    # 3.1 確認聯絡人目前有分類
    log_info("3.1 確認聯絡人目前有分類")
    resp = requests.get(f"{BASE_URL}/contacts/{MAINTENANCE_ID}")
    contact = next((c for c in resp.json() if c['id'] == contact_a_id), None)
    if contact and contact.get('category_id') == cat_a_id:
        log_pass(f"聯絡人目前屬於分類 {cat_a_id}")
    else:
        log_info(f"聯絡人分類狀態: {contact.get('category_id') if contact else 'not found'}")

    # 3.2 刪除分類
    log_info(f"3.2 刪除分類 (id={cat_a_id})")
    resp = requests.delete(f"{BASE_URL}/contacts/categories/{cat_a_id}")
    if resp.status_code == 200:
        log_pass("分類刪除成功")
    else:
        log_fail(f"分類刪除失敗: {resp.status_code} - {resp.text}")
        return

    # 3.3 確認聯絡人變成未分類
    log_info("3.3 確認聯絡人變成未分類")
    resp = requests.get(f"{BASE_URL}/contacts/{MAINTENANCE_ID}")
    contact = next((c for c in resp.json() if c['id'] == contact_a_id), None)
    if contact and contact.get('category_id') is None:
        log_pass("聯絡人已變成未分類 (category_id = null)")
    else:
        log_fail(f"聯絡人分類未正確更新: {contact.get('category_id') if contact else 'not found'}")


# ============================================================
# 測試 4: 批量修改分類
# ============================================================
def test_bulk_change_category(categories, contacts):
    log_section("測試 4: 批量修改分類")

    cat_b_id = categories['cat_b']['id']
    contact_a_id = contacts['contact_a']['id']
    contact_b_id = contacts['contact_b']['id']

    # 4.1 將兩個聯絡人移到分類B
    log_info(f"4.1 批量修改分類 (移到分類B, id={cat_b_id})")

    success_count = 0
    for cid in [contact_a_id, contact_b_id]:
        resp = requests.put(f"{BASE_URL}/contacts/{MAINTENANCE_ID}/{cid}", json={
            "category_id": cat_b_id
        })
        if resp.status_code == 200:
            success_count += 1

    if success_count == 2:
        log_pass(f"批量修改成功，{success_count} 筆聯絡人已更新")
    else:
        log_fail(f"批量修改部分失敗，只有 {success_count} 筆成功")

    # 4.2 驗證結果
    log_info("4.2 驗證批量修改結果")
    resp = requests.get(f"{BASE_URL}/contacts/{MAINTENANCE_ID}")
    contacts_list = resp.json()
    updated = [c for c in contacts_list if c['id'] in [contact_a_id, contact_b_id] and c.get('category_id') == cat_b_id]
    if len(updated) == 2:
        log_pass("所有聯絡人分類已正確更新")
    else:
        log_fail(f"只有 {len(updated)} 筆分類正確更新")

    # 4.3 批量移到未分類
    log_info("4.3 批量移到未分類")
    for cid in [contact_a_id, contact_b_id]:
        requests.put(f"{BASE_URL}/contacts/{MAINTENANCE_ID}/{cid}", json={
            "category_id": None
        })

    resp = requests.get(f"{BASE_URL}/contacts/{MAINTENANCE_ID}")
    contacts_list = resp.json()
    uncategorized = [c for c in contacts_list if c['id'] in [contact_a_id, contact_b_id] and c.get('category_id') is None]
    if len(uncategorized) == 2:
        log_pass("批量移到未分類成功")
    else:
        log_fail(f"只有 {len(uncategorized)} 筆移到未分類")


# ============================================================
# 測試 5: 批量刪除
# ============================================================
def test_bulk_delete(contacts):
    log_section("測試 5: 批量刪除")

    contact_b_id = contacts['contact_b']['id']
    contact_c_id = contacts['contact_c']['id']

    # 5.1 批量刪除兩個聯絡人
    log_info(f"5.1 批量刪除聯絡人 (ids: {contact_b_id}, {contact_c_id})")

    success_count = 0
    for cid in [contact_b_id, contact_c_id]:
        resp = requests.delete(f"{BASE_URL}/contacts/{MAINTENANCE_ID}/{cid}")
        if resp.status_code == 200:
            success_count += 1

    if success_count == 2:
        log_pass(f"批量刪除成功，{success_count} 筆聯絡人已刪除")
    else:
        log_fail(f"批量刪除部分失敗，只有 {success_count} 筆成功")

    # 5.2 驗證刪除結果
    log_info("5.2 驗證刪除結果")
    resp = requests.get(f"{BASE_URL}/contacts/{MAINTENANCE_ID}")
    contacts_list = resp.json()
    remaining = [c for c in contacts_list if c['id'] in [contact_b_id, contact_c_id]]
    if len(remaining) == 0:
        log_pass("聯絡人已成功刪除")
    else:
        log_fail(f"仍有 {len(remaining)} 筆聯絡人未刪除")


# ============================================================
# 清理測試資料
# ============================================================
def cleanup(categories, contacts):
    log_section("清理測試資料")

    # 刪除剩餘聯絡人
    if contacts and contacts.get('contact_a'):
        resp = requests.delete(f"{BASE_URL}/contacts/{MAINTENANCE_ID}/{contacts['contact_a']['id']}")
        if resp.status_code == 200:
            log_info(f"已刪除聯絡人 {contacts['contact_a']['id']}")

    # 刪除剩餘分類
    if categories and categories.get('cat_b'):
        resp = requests.delete(f"{BASE_URL}/contacts/categories/{categories['cat_b']['id']}")
        if resp.status_code == 200:
            log_info(f"已刪除分類 {categories['cat_b']['id']}")

    log_pass("測試資料清理完成")


# ============================================================
# 主程式
# ============================================================
def main():
    print(f"\n{Colors.CYAN}{'='*60}{Colors.END}")
    print(f"{Colors.CYAN}  通訊錄功能綜合測試{Colors.END}")
    print(f"{Colors.CYAN}  API Base URL: {BASE_URL}{Colors.END}")
    print(f"{Colors.CYAN}  Maintenance ID: {MAINTENANCE_ID}{Colors.END}")
    print(f"{Colors.CYAN}{'='*60}{Colors.END}")

    categories = None
    contacts = None

    try:
        # 測試 1: 分類 CRUD
        categories = test_category_crud()
        if not categories:
            log_fail("分類測試失敗，終止測試")
            return

        # 測試 2: 聯絡人 CRUD
        contacts = test_contact_crud(categories)
        if not contacts:
            log_fail("聯絡人測試失敗，終止測試")
            return

        # 測試 3: 刪除分類後聯絡人變未分類
        test_category_delete_cascade(categories, contacts)

        # 測試 4: 批量修改分類
        test_bulk_change_category(categories, contacts)

        # 測試 5: 批量刪除
        test_bulk_delete(contacts)

    finally:
        # 清理測試資料
        cleanup(categories, contacts)

    print(f"\n{Colors.GREEN}{'='*60}{Colors.END}")
    print(f"{Colors.GREEN}  測試完成！{Colors.END}")
    print(f"{Colors.GREEN}{'='*60}{Colors.END}\n")


if __name__ == "__main__":
    main()
