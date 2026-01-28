# Network Dashboard

網路設備歲修監控系統 — 支援 8 種指標自動評估、客戶端前後對比、失敗原因追蹤。

---

## Quick Start

### 前置需求

| 工具 | 版本 |
|------|------|
| Docker & Docker Compose | 任意近期版本 |
| Python | 3.11+ |
| Node.js | 18+ |

### Step 1: Clone & 環境設定

```bash
git clone https://github.com/coolguazitech/network-dashboard.git
cd network-dashboard

# Python
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# Frontend
cd frontend && npm install && cd ..

# 環境變數
cp .env.example .env
```

### Step 2: 啟動資料庫 (Terminal 1)

```bash
docker-compose up -d
```

MariaDB `:3306` + phpMyAdmin `:8080`。

### Step 3: 啟動 Mock API Server (Terminal 2)

> 只有 `USE_MOCK_API=false` 時需要。`USE_MOCK_API=true` 可跳過此步。

```bash
uvicorn tests.mock_api_server:app --port 8001 --reload
```

### Step 4: 初始化 + Seed 資料 (一次性)

```bash
python3 scripts/seed_all.py
```

依序執行：
1. 產生 factory scenario YAML
2. 清理 DB + 建立基礎資料（switches、expectations、categories）
3. Seed 8 個指標（3 輪時間序列：T-6h、T-3h、now）
4. Seed 客戶端資料 + comparisons（3 輪）

### Step 5: 啟動 Backend (Terminal 3)

```bash
uvicorn app.main:app --reload --port 8000
```

- API 文件：http://localhost:8000/api/docs
- 健康檢查：http://localhost:8000/health

### Step 6: 啟動 Frontend (Terminal 4)

```bash
cd frontend
npm run dev
```

開啟 http://localhost:3000

主要頁面：
- **Dashboard** — 8 個指標通過率卡片 + 時間趨勢圖
- **指標詳情** — 點擊任一指標查看失敗設備清單
- **設備清單** — 新舊設備對應、可達性、MAC 偵測狀態
- **客戶端比較** — MAC 前後對比結果，含多時間點統計趨勢

---

## 模式切換

修改 `.env` 後重啟 Backend 即可生效。

| 模式 | `USE_MOCK_API` | `EXTERNAL_API_SERVER` | 需要外部 Server |
|------|:-:|---|:-:|
| **純內建 Mock** | `true` | （不重要） | 否 |
| **Mock API Server** | `false` | `http://localhost:8001` | 是（port 8001） |
| **正式環境** | `false` | `http://real-server:9000` | 是 |

- **純內建 Mock** (`USE_MOCK_API=true`) — `MockApiClient` 在記憶體產生確定性資料，不需任何外部 server。適合 UI 開發。
- **Mock API Server** (`USE_MOCK_API=false`) — 打 FastAPI Mock Server，支援 YAML scenario 故障模擬。適合整合測試。
- **正式環境** (`USE_MOCK_API=false`) — 打真實外部網路管理 API (FNA/DNA)。

### 一鍵重置

```bash
python3 scripts/seed_all.py      # 重新 seed 所有資料
uvicorn app.main:app --port 8000  # 重啟 backend
```

---

## 排程系統

設定檔：`config/scheduler.yaml`。Backend 啟動時自動載入 11 個排程 job。

| Job | 間隔 | Service |
|-----|:----:|---------|
| transceiver | 30s | DataCollectionService |
| version | 30s | DataCollectionService |
| uplink | 30s | DataCollectionService |
| fan | 30s | DataCollectionService |
| power | 30s | DataCollectionService |
| error_count | 30s | DataCollectionService |
| ping | 30s | DataCollectionService |
| port_channel | 30s | DataCollectionService |
| mac-table | 30s | DataCollectionService |
| arp-table | 30s | DataCollectionService |
| **client-collection** | **60s** | **ClientCollectionService** |

並發保護：`max_instances=1`、`coalesce=True`、`misfire_grace_time=30s`。

---

## 資料流架構

```
Scheduler Jobs (APScheduler)
       │
       │ 呼叫 External API (or MockApiClient)
       ▼
Parser (解析 CLI output) ──▶ typed_records (per-type DB tables)
                                    │
                                    │ Indicator 讀取
                                    ▼
                              Indicator.evaluate()
                                    │
                                    ▼
                              Dashboard API (/summary, /details)
```

### 關鍵設計

- **Scheduler 與 Indicator 獨立**：Scheduler 從外部 API 採集原始資料，Indicator 從 DB 評估
- **Typed Records**：每種指標有獨立的 record 表（`ping_records`、`transceiver_records` 等）
- **兩種分母來源**（所有指標對象皆為新設備）：
  - **期望類**（ping、port_channel、uplink）：分母來自使用者定義的期望清單
  - **採集類**（power、fan、error_count、transceiver、version）：分母來自實際採集到的新設備資料筆數

---

## 指標總覽

| 指標 | 說明 | 分母來源 | 通過條件 |
|------|------|----------|----------|
| `ping` | 新設備連通性 | MaintenanceDeviceList | 可達且成功率 >= 80% |
| `power` | 電源供應器 | 新設備數 | 所有 PSU Normal |
| `fan` | 風扇狀態 | 新設備數 | 所有風扇 Normal |
| `transceiver` | 光模塊 Tx/Rx/溫度 | 新設備光模塊數 | 功率與溫度在範圍內 |
| `error_count` | 介面錯誤計數 | 新設備介面數 | CRC/In/Out 錯誤 = 0 |
| `port_channel` | Port-Channel | 期望清單 | 所有成員 UP |
| `uplink` | Uplink 拓撲 | 期望清單 | 鄰居符合期望 |
| `version` | 韌體版本 | 新設備數 | 版本符合期望值 |

---

## 待完成工作 (TODO)

### 1. 客戶端資料 Parser — `app/parsers/client_parsers.py`

5 個 parser 的 `parse()` 方法目前為 `NotImplementedError`，需根據 Fetcher 實際回傳格式實作：

| Parser | Fetcher | 輸出型別 | 欄位 |
|--------|---------|----------|------|
| `MacTableParser` | `get_mac_table` | `list[MacTableData]` | mac_address, interface_name, vlan_id |
| `ArpParser` | `get_arp_table` | `list[ArpData]` | ip_address, mac_address |
| `InterfaceStatusParser` | `get_interface_status` | `list[InterfaceStatusData]` | interface_name, link_status, speed, duplex |
| `AclParser` | `get_acl_number` | `list[AclData]` | interface_name, acl_number |
| `PingManyParser` | `ping_many` | `list[PingManyData]` | ip_address, is_reachable |

型別定義：`app/parsers/protocols.py`

### 2. Client Collection — Ping API 整合

`app/services/client_collection_service.py` 的 `_fetch_ping_many()` 目前以標準 `fetch()` 呼叫。需確認真實 API 如何接收目標 IP 清單（POST body / query params）。

### 3. Checkpoint 摘要

`app/api/endpoints/maintenance.py` 的 `_generate_checkpoint_summary()` 回傳 placeholder。應查詢該時間點附近的指標結果與客戶端資料產生真實統計。

### 4. 外部 API 設定

`config/scheduler.yaml` 各 job 的 `url`、`source`、`brand` 欄位為空。正式部署時填入真實外部 API 連線資訊。

---

## 目錄結構

```
network_dashboard/
├── app/
│   ├── main.py                           # FastAPI 入口
│   ├── api/
│   │   ├── routes.py                     # Router 彙整
│   │   └── endpoints/                    # 各功能端點
│   ├── core/
│   │   ├── config.py                     # pydantic-settings (.env)
│   │   └── enums.py                      # Phase, Vendor, Platform
│   ├── db/
│   │   ├── base.py                       # SQLAlchemy async engine
│   │   └── models.py                     # ORM 模型
│   ├── indicators/                       # 8 種指標評估器
│   ├── parsers/
│   │   ├── client_parsers.py             # 客戶端 parser (TODO)
│   │   ├── protocols.py                  # ParsedData 型別
│   │   ├── registry.py                   # Parser auto-discovery
│   │   └── hpe_comware/                  # HPE Comware parsers
│   ├── repositories/                     # Data access layer
│   └── services/
│       ├── api_client.py                 # External / Mock API client
│       ├── data_collection.py            # 指標資料採集
│       ├── client_collection_service.py  # 客戶端資料採集 (Phase 1-4)
│       ├── scheduler.py                  # APScheduler 排程管理
│       └── client_comparison_service.py  # 客戶端前後對比
├── config/
│   ├── scheduler.yaml                    # 排程設定
│   ├── indicators.yaml                   # 指標評估規則
│   └── switches.yaml                     # Switch 定義
├── scripts/
│   ├── seed_all.py                       # 統一 seed（一鍵）
│   ├── init_factory_data.py              # DB 初始化
│   ├── generate_factory_scenarios.py     # YAML scenario 產生
│   ├── factory_device_config.py          # 共用設備配置
│   └── seed_client_data.py              # 客戶端資料 seed
├── tests/
│   ├── mock_api_server.py                # Mock API Server
│   └── scenarios/                        # YAML scenario 檔案
├── frontend/                             # Vue 3 + Vite + Tailwind + ECharts
├── docker-compose.yml                    # MariaDB + phpMyAdmin
├── .env.example                          # 環境變數模板
└── pyproject.toml
```

---

## API 端點

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/v1/dashboard/maintenance/{id}/summary` | 所有指標通過率摘要 |
| GET | `/api/v1/dashboard/maintenance/{id}/indicator/{type}/details` | 單一指標詳情 + 失敗清單 |
| GET | `/api/v1/maintenance` | 歲修列表 |
| POST | `/api/v1/maintenance` | 建立歲修 |
| DELETE | `/api/v1/maintenance/{id}` | 刪除歲修 + 所有相關資料 |
| GET | `/api/v1/comparisons/timepoints/{id}` | 歷史時間點 |
| GET | `/api/v1/comparisons/statistics/{id}` | 統計趨勢 |
| POST | `/api/v1/comparisons/generate/{id}` | 產生對比結果 |
| GET | `/api/v1/maintenance-devices/{id}` | 設備清單 + 可達性 |
| GET | `/api/v1/mac-list/{id}` | MAC 清單 + 偵測狀態 |
| POST | `/api/v1/indicators/{name}/collect` | 手動觸發採集 |

完整 API 文件：http://localhost:8000/api/docs

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
| `DB_HOST` | `localhost` | MariaDB 位址 |
| `DB_PORT` | `3306` | MariaDB 埠號 |
| `DB_NAME` | `network_dashboard` | 資料庫名稱 |
| `DB_USER` | `admin` | 資料庫帳號 |
| `DB_PASSWORD` | `admin` | 資料庫密碼 |
| `EXTERNAL_API_SERVER` | `http://localhost:9000` | 外部 API 位址 |
| `EXTERNAL_API_TIMEOUT` | `30` | API timeout (秒) |
| `USE_MOCK_API` | `false` | `true` = 內建 MockApiClient；`false` = 打 EXTERNAL_API_SERVER |
| `APP_ENV` | `development` | 環境 (development / production) |
| `APP_DEBUG` | `false` | Debug 模式 + auto-reload |

---

## 技術棧

**後端** — Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Pydantic 2, MariaDB (aiomysql), APScheduler

**前端** — Vue 3, Vite, Tailwind CSS, ECharts, Axios, Vue Router
