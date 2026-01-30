# 測試腳本說明

## 腳本清單

| 腳本 | 用途 |
|------|------|
| `reset_database.py` | 清空資料庫，回到初始狀態 |
| `step_by_step_test.py` | 互動式分步測試，逐步觀察系統行為 |
| `e2e_simulation.py` | 自動化端到端測試 |
| `test_data_flow.py` | 資料流驗證測試 |
| `test_performance.py` | 效能測試 |

---

## 快速開始

### 1. 啟動後端服務

```bash
cd network_dashboard
source venv/bin/activate
python -m app.main
```

### 2. 查看資料庫狀態

```bash
python scripts/reset_database.py --status
```

### 3. 清空資料庫（可選）

```bash
# 互動式確認
python scripts/reset_database.py

# 強制執行（不需確認）
python scripts/reset_database.py --force
```

### 4. 執行互動式測試

```bash
python scripts/step_by_step_test.py
```

每個步驟會等待你按 Enter 確認後再繼續。

### 5. 執行自動化測試

```bash
python scripts/e2e_simulation.py
```

---

## 測試流程

### 互動式測試 (step_by_step_test.py)

```
Step 0: 清空測試資料（可選）
    ↓
Step 1: 建立歲修 ID
    ↓
Step 2: 匯入 Client MAC 清單
    ↓
Step 3: 匯入設備對應清單
    ↓
Step 4: 設定期望值（版本、ARP 來源）
    ↓
Step 5: 生成 Mock 資料（模擬 Scheduler）
    ↓
Step 6: 執行客戶端偵測
    ↓
Step 7: 查看時間點和統計資料
    ↓
Step 8: 啟動 Scheduler（持續運行）
```

---

## 搭配前端使用

1. 啟動後端: `python -m app.main`
2. 啟動前端: `cd frontend && npm run dev`
3. 執行測試腳本
4. 在前端頁面觀察資料變化

前端 URL: http://localhost:5173

---

## 測試資料

測試腳本會建立以下資料：

### MAC 清單
- 5-10 個測試 MAC 地址
- 分布在 F18, F6, AP, F14, F12 等 Tenant Group

### 設備對應
- 2-3 個設備對應
- 包含 HPE, Cisco-IOS, Cisco-NXOS

### 期望值
- 版本期望
- ARP 來源設備

---

## 注意事項

1. **Mock 模式**: 測試使用 Mock Fetcher，不會真的連接外部 API
2. **資料隔離**: 測試使用獨立的歲修 ID，不影響正式資料
3. **Scheduler**: 應用程式啟動時會自動運行 Scheduler
