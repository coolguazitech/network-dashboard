# Network Dashboard - 網路設備歲修監控系統

一個用於監控網路設備歲修過程的 Dashboard 系統，支援 8 種指標自動評估、前後對比、失敗原因追蹤，協助工程師快速定位問題。

---

## 從零開始建置（完整重現測試環境）

以下步驟會讓你 clone 後建出與開發環境一模一樣的前端畫面與測試資料。

### 前置需求

| 工具 | 版本 |
|------|------|
| Docker & Docker Compose | 任意近期版本 |
| Python | 3.11+ |
| Node.js | 18+ |
| npm | 9+ |

### Step 1: Clone 專案

```bash
git clone https://github.com/coolguazitech/network_dashboard.git
cd network_dashboard
```

### Step 2: 設定環境變數

```bash
cp .env.example .env
```

預設值即可直接使用，不需修改。關鍵設定：

```
APP_ENV=testing          # 使用 MockApiClient，不需連接真實外部 API
DB_HOST=localhost
DB_PORT=3306
DB_NAME=network_dashboard
DB_USER=admin
DB_PASSWORD=admin
```

### Step 3: 啟動資料庫

```bash
docker-compose up -d
```

啟動 MariaDB (`localhost:3306`) 和 phpMyAdmin (`http://localhost:8080`)。

等待 MariaDB 完全啟動（約 10 秒），可用以下命令確認：

```bash
docker-compose logs db | tail -5
# 看到 "ready for connections" 即可
```

### Step 4: 建立 Python 虛擬環境

```bash
python3 -m venv venv
source venv/bin/activate    # macOS / Linux
pip install -e ".[dev]"
```

### Step 5: 建置前端

```bash
cd frontend
npm install
npm run build
cd ..
```

前端 build 產出的靜態檔會放在 `frontend/dist/`，由 FastAPI 後端直接 serve。

### Step 6: 初始化基礎資料

```bash
python scripts/init_factory_data.py
```

這會建立：
- 歲修作業 `TEST-100`
- 65 台 switch（34 OLD + 31 NEW），其中 34 台 active
- 設備分類（CORE / AGG / EQP / AMHS / SNR / OTHERS）
- 新舊設備對應關係
- 100 個 MAC 地址清單
- Port-Channel / Uplink 期望值
- MaintenanceDeviceList（34 台新設備）

### Step 7: 啟動 Mock API Server 並 seed 指標資料

開兩個 terminal：

**Terminal 1 — Mock API Server：**

```bash
source venv/bin/activate
uvicorn tests.mock_api_server:app --port 8001
```

Mock Server 會根據 `tests/scenarios/` 下的 YAML 檔案回傳模擬的 CLI 原始文字。

**Terminal 2 — Seed 8 種指標的採集資料：**

```bash
source venv/bin/activate
python scripts/seed_test_data.py --scenario factory_baseline --maintenance-id TEST-100
```

等待 seed 完成後，可以關閉 Terminal 1 的 Mock API Server（`Ctrl+C`）。

### Step 8: Seed 客戶端比對資料

```bash
python scripts/seed_client_data.py
```

這會建立：
- 100 筆 OLD phase `client_records`
- 3 輪 NEW phase `client_records`（模擬逐步改善）
- `client_comparisons` 對比結果（info / warning / critical 分布）

### Step 9: 啟動後端

```bash
uvicorn app.main:app --port 8000
```

### Step 10: 開啟瀏覽器

打開 `http://localhost:8000`，即可看到完整的 Dashboard 畫面。

主要頁面：
- **Dashboard**：8 個指標通過率卡片 + 時間趨勢圖
- **指標詳情**：點擊任一指標卡片查看失敗設備清單
- **設備清單**：新舊設備對應、可達性狀態、MAC 偵測狀態
- **客戶端比較**：MAC 前後對比結果，含多時間點統計趨勢

---

## 一鍵重置

如果需要重新建立所有測試資料：

```bash
# 1. 重置資料庫（刪除所有資料，重建表結構）
python scripts/init_factory_data.py

# 2. 啟動 Mock Server（另一個 terminal）
uvicorn tests.mock_api_server:app --port 8001

# 3. Seed 指標資料
python scripts/seed_test_data.py --scenario factory_baseline --maintenance-id TEST-100

# 4. 關閉 Mock Server，然後 seed 客戶端資料
python scripts/seed_client_data.py

# 5. 重啟後端
uvicorn app.main:app --port 8000
```

---

## 資料流架構

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Scheduler Jobs │────▶│   Parser     │────▶│  DB             │
│  (APScheduler)  │     │  (解析 CLI)  │     │  typed_records  │
│  各自獨立排程   │     │              │     │  (per-type 表)  │
└────────┬────────┘     └──────────────┘     └────────┬────────┘
         │                                            │
         │ 呼叫外部 API                               │ Indicator 讀取
         ▼                                            ▼
┌─────────────────┐                         ┌─────────────────┐
│  External API   │                         │   Indicator     │
│  show/display   │                         │   .evaluate()   │
│  ping, etc.     │                         │   計算通過率    │
└─────────────────┘                         └────────┬────────┘
                                                     │
                                                     ▼
                                            ┌─────────────────┐
                                            │  Dashboard API  │
                                            │  /summary       │
                                            │  /details       │
                                            └─────────────────┘
```

### 關鍵設計

- **Scheduler 與 Indicator 獨立**：Scheduler 負責從外部 API 採集原始資料（show transceiver、display fan、ping 等），Indicator 從 DB 讀取已採集的資料進行評估
- **Typed Records**：每種指標有獨立的 typed record 表（`ping_records`、`transceiver_records` 等），取代舊的通用 `collection_records` 表
- **兩種分母來源**（所有指標的對象皆為新設備，若未換機則新設備 = 舊設備）：
  - **期望類**（ping、port_channel、uplink）：分母來自使用者定義的期望清單
  - **採集類**（power、fan、error_count、transceiver、version）：分母來自實際採集到的新設備資料筆數

---

## 指標總覽

系統支援 8 種指標，每種都會計算通過率並記錄失敗原因：

| 指標 | 說明 | 分母來源 | 通過條件 |
|------|------|----------|----------|
| `ping` | 新設備連通性檢查 | 新設備數 (MaintenanceDeviceList) | 可達且成功率 >= 80% |
| `power` | 電源供應器狀態 | 新設備數 | 所有 PSU 狀態正常 |
| `fan` | 風扇狀態 | 新設備數 | 所有風扇狀態正常 |
| `transceiver` | 光模塊 Tx/Rx/溫度 | 新設備光模塊數 | 功率與溫度在範圍內 |
| `error_count` | 介面錯誤計數 | 新設備介面數 | CRC/In/Out 錯誤為 0 |
| `port_channel` | Port-Channel 狀態 | Port-Channel 期望數 | 所有成員 UP |
| `uplink` | Uplink 拓撲驗證 | Uplink 期望數 | 鄰居符合期望 |
| `version` | 韌體版本驗證 | 新設備數 | 版本符合期望值 |

---

## 目錄結構

```
network_dashboard/
├── app/
│   ├── main.py                     # FastAPI 入口，lifespan 管理
│   ├── api/
│   │   ├── routes.py               # Router 彙整
│   │   └── endpoints/              # 各功能端點
│   ├── core/
│   │   ├── config.py               # pydantic-settings 設定
│   │   └── enums.py                # 列舉 (Phase, Vendor, Platform)
│   ├── db/
│   │   ├── base.py                 # SQLAlchemy async engine
│   │   └── models.py              # ORM 模型
│   ├── indicators/                 # 指標評估器（8 種）
│   │   ├── base.py                 # BaseIndicator ABC
│   │   └── *.py                    # ping, power, fan, transceiver, ...
│   ├── parsers/                    # Parser 系統 (Plugin-based)
│   │   ├── protocols.py            # Protocol 定義 & 資料模型
│   │   ├── registry.py             # Auto-discovery Registry
│   │   └── plugins/                # 各廠牌 Parser 插件
│   ├── repositories/               # Repository Pattern
│   │   ├── switch.py
│   │   ├── typed_records.py        # Per-type record repositories
│   │   └── ...
│   ├── schemas/                    # Pydantic schemas
│   └── services/
│       ├── indicator_service.py    # 指標評估服務
│       ├── data_collection.py      # 資料採集服務
│       ├── api_client.py           # 外部 API 客戶端 (含 MockApiClient)
│       ├── scheduler.py            # APScheduler 排程管理
│       └── client_comparison_service.py  # 客戶端前後對比
├── config/
│   ├── scheduler.yaml              # 排程設定
│   └── client_comparison.yaml      # 對比設定
├── scripts/
│   ├── factory_device_config.py    # 共用設備配置（34 台設備定義）
│   ├── init_factory_data.py        # 初始化基礎資料
│   ├── generate_factory_scenarios.py  # 產生 Mock Scenario YAML
│   ├── seed_test_data.py           # Seed 8 種指標採集資料
│   └── seed_client_data.py         # Seed 客戶端比對資料
├── tests/
│   ├── mock_api_server.py          # Mock 外部 API Server
│   └── scenarios/                  # Mock scenario YAML 檔案
├── frontend/                       # Vue 3 前端
│   └── src/
│       ├── views/
│       │   ├── Dashboard.vue       # 主 Dashboard
│       │   ├── IndicatorDetail.vue # 指標詳情
│       │   ├── Comparison.vue      # 客戶端前後對比
│       │   └── Devices.vue         # 設備清單
│       └── components/
├── docker-compose.yml              # MariaDB + phpMyAdmin
├── pyproject.toml
├── .env.example
└── README.md
```

---

## API 端點

### Dashboard

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/v1/dashboard/maintenance/{id}/summary` | 所有指標通過率摘要 |
| GET | `/api/v1/dashboard/maintenance/{id}/indicator/{type}/details` | 單一指標詳情 + 失敗清單 |

### 歲修管理

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/v1/maintenance` | 列出所有歲修作業 |
| POST | `/api/v1/maintenance` | 建立歲修作業 |
| DELETE | `/api/v1/maintenance/{id}` | 刪除歲修作業 |

### 對比分析

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/v1/comparisons/timepoints/{id}` | 歷史時間點 |
| GET | `/api/v1/comparisons/statistics/{id}` | 統計趨勢 |
| POST | `/api/v1/comparisons/generate/{id}` | 產生對比結果 |

### 設備管理

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/v1/maintenance-devices/{id}` | 設備清單 + 可達性 |
| GET | `/api/v1/mac-list/{id}` | MAC 清單 + 偵測狀態 |

---

## 支援廠牌

| 廠牌 | 平台 | Parser 支援 |
|------|------|-------------|
| Cisco | IOS | transceiver, neighbor |
| Cisco | NX-OS | transceiver, neighbor, port_channel, error, fan, power |
| HPE | Comware | transceiver, neighbor, port_channel, error, fan, power, ping, version |

---

## 環境變數

參考 `.env.example`：

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `APP_ENV` | `testing` | `testing` = MockApiClient; `production` = 真實 API |
| `DB_HOST` | `localhost` | MariaDB 位址 |
| `DB_PORT` | `3306` | MariaDB 埠號 |
| `DB_NAME` | `network_dashboard` | 資料庫名稱 |
| `DB_USER` | `admin` | 資料庫帳號 |
| `DB_PASSWORD` | `admin` | 資料庫密碼 |
| `EXTERNAL_API_SERVER` | `http://localhost:9000` | 外部 API 位址 |
| `APP_DEBUG` | `true` | 除錯模式 |

---

## 技術棧

**後端**
- Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Pydantic 2
- MariaDB (aiomysql), APScheduler
- Plugin-based Parser, Repository Pattern

**前端**
- Vue 3, Vite, Tailwind CSS, ECharts
- Axios, Day.js, Vue Router

---

## License

MIT
