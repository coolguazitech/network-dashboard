# Network Dashboard - 網路設備歲修監控系統

一個用於監控網路設備歲修過程的 Dashboard 系統，支援 8 種指標自動評估、前後對比、失敗原因追蹤，協助工程師快速定位問題。

## 快速啟動

### 1. 啟動資料庫

```bash
cd network_dashboard
docker-compose up -d
```

- MariaDB: `localhost:3306` (admin/admin)
- phpMyAdmin: `http://localhost:8080`

### 2. 安裝依賴

```bash
python -m venv venv
source venv/bin/activate  # macOS/Linux
pip install -e ".[dev]"
```

### 3. 初始化測試資料

```bash
python scripts/init_factory_data.py
```

建立 `TEST-100` 歲修作業，包含 34 台新設備、設備分類、MAC 清單、期望值等。

### 4. 啟動後端

```bash
uvicorn app.main:app --reload --port 8000
```

- API 文件：`http://localhost:8000/api/docs`
- API 前綴：`/api/v1`

### 5. 啟動前端

```bash
cd frontend
npm install
npm run dev
```

- 前端：`http://localhost:3000`

---

## 資料流架構

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Scheduler Jobs │────▶│   Parser     │────▶│  DB             │
│  (APScheduler)  │     │  (解析 CLI)  │     │  collection_    │
│  各自獨立排程   │     │              │     │  records        │
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
- **Scheduler 不綁定 Indicator**：也會有 MAC TABLE、ARP TABLE 等採集 scheduler，這些不直接對應指標，而是供多個 Indicator 使用
- **兩種分母來源**（所有指標的對象皆為新設備，若未換機則新設備 = 舊設備）：
  - **期望類**（ping、port_channel、uplink）：分母來自使用者定義的期望清單（MaintenanceDeviceList、PortChannelExpectation 等）
  - **採集類**（power、fan、error_count、transceiver、version）：分母來自實際採集到的新設備資料筆數

### 為什麼需要 DB？

1. **時間序列圖表**：前端需要橫軸為時間的折線圖，需要歷史資料
2. **歲修前後對比**：PRE/POST 階段的資料需要保存才能比較
3. **系統重啟**：資料不能遺失
4. **多 Indicator 共用**：例如 transceiver raw data 可以同時算 Tx/Rx pass rate

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
│   │   └── endpoints/
│   │       ├── dashboard.py        # Dashboard 摘要 & 指標詳情
│   │       ├── maintenance.py      # 歲修作業管理
│   │       ├── comparisons.py      # 前後對比
│   │       ├── switches.py         # 設備管理
│   │       ├── categories.py       # 設備分類
│   │       ├── device_mappings.py  # 新舊設備對應
│   │       ├── interface_mappings.py
│   │       ├── mac_list.py         # MAC 清單
│   │       ├── maintenance_devices.py
│   │       ├── expectations.py     # 期望值設定
│   │       └── indicators.py       # 指標評估
│   ├── core/
│   │   ├── config.py               # pydantic-settings 設定
│   │   └── enums.py                # 列舉 (Phase, Vendor, Platform)
│   ├── db/
│   │   ├── base.py                 # SQLAlchemy async engine
│   │   └── models.py              # ORM 模型
│   ├── indicators/                 # 指標評估器
│   │   ├── base.py                 # BaseIndicator ABC + IndicatorEvaluationResult
│   │   ├── metrics.py              # Metric 評估類
│   │   ├── ping.py                 # Ping 連通性
│   │   ├── power.py                # 電源狀態
│   │   ├── fan.py                  # 風扇狀態
│   │   ├── transceiver.py          # 光模塊
│   │   ├── error_count.py          # 錯誤計數
│   │   ├── port_channel.py         # Port-Channel
│   │   ├── uplink.py               # Uplink 拓撲
│   │   └── version.py              # 韌體版本
│   ├── parsers/                    # Parser 系統 (Plugin-based)
│   │   ├── protocols.py            # Protocol 定義 & 資料模型
│   │   ├── registry.py             # Auto-discovery Registry
│   │   └── plugins/                # 各廠牌 Parser 插件
│   │       ├── cisco_nxos_*.py     # Cisco NX-OS 系列
│   │       ├── cisco_ios_*.py      # Cisco IOS 系列
│   │       ├── hpe_*.py            # HPE Comware 系列
│   │       ├── aruba_*.py          # Aruba 系列
│   │       └── ping.py             # 通用 Ping Parser
│   ├── repositories/               # Repository Pattern
│   │   ├── base.py
│   │   ├── switch.py
│   │   ├── collection_record.py
│   │   └── indicator_result.py
│   ├── schemas/                    # Pydantic schemas
│   │   ├── switch.py
│   │   └── indicator.py
│   └── services/
│       ├── indicator_service.py    # 指標評估服務 (支援 mock 模式)
│       ├── data_collection.py      # 資料採集服務
│       ├── api_client.py           # 外部 API 客戶端 (含 MockApiClient)
│       ├── scheduler.py            # APScheduler 排程管理
│       └── client_comparison_service.py
├── config/
│   ├── switches.yaml               # 設備定義
│   ├── indicators.yaml             # 指標定義
│   ├── scheduler.yaml              # 排程設定 (8 個指標 + ACL)
│   └── client_comparison.yaml      # 對比設定
├── scripts/
│   ├── init_factory_data.py        # 初始化測試資料
│   ├── seed_test_data.py
│   └── ...
├── migrations/                     # SQL migration 檔案
├── frontend/                       # Vue 3 前端
│   └── src/
│       ├── views/
│       │   ├── Dashboard.vue       # 主 Dashboard
│       │   ├── IndicatorDetail.vue # 指標詳情 (含失敗清單)
│       │   ├── Comparison.vue      # 前後對比
│       │   ├── Settings.vue        # 設定頁面
│       │   ├── Switches.vue        # 設備管理
│       │   └── Devices.vue         # 設備清單
│       └── components/
│           ├── IndicatorCard.vue
│           ├── IndicatorPie.vue
│           ├── FailureTable.vue
│           ├── CategoryModal.vue
│           └── DeviceMappingModal.vue
├── docker-compose.yml              # MariaDB + phpMyAdmin
├── pyproject.toml
├── .env
└── README.md
```

---

## API 端點

### Dashboard

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/v1/dashboard/maintenance/{id}/summary` | 所有指標通過率摘要 |
| GET | `/api/v1/dashboard/maintenance/{id}/indicator/{type}/details` | 單一指標詳情 + 失敗清單 |
| GET | `/api/v1/dashboard/maintenance/{id}/comparison` | PRE/POST 對比 |

### 歲修管理

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/v1/maintenance` | 列出所有歲修作業 |
| POST | `/api/v1/maintenance` | 建立歲修作業 |
| DELETE | `/api/v1/maintenance/{id}` | 刪除歲修作業 |
| GET | `/api/v1/maintenance/config/{id}` | 取得歲修設定 |

### 對比分析

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/v1/comparisons/timepoints/{id}` | 歷史時間點 |
| GET | `/api/v1/comparisons/statistics/{id}` | 統計趨勢 |
| POST | `/api/v1/comparisons/generate/{id}` | 產生對比結果 |

---

## 排程設定

`config/scheduler.yaml` 定義所有資料採集任務。每個 job 的 name 即為採集的資料類型，Scheduler 與 Indicator 獨立運作：

```yaml
maintenance_id: "TEST-100"    # APM ID

jobs:
  mac-table:
    url:                       # 外部 API endpoint
    source:                    # FNA/DNA
    brand:                     # HPE/Cisco-IOS/Cisco-NXOS
    interval: 30               # seconds
    description: "MAC Table 採集"

  arp-table:
    url:
    source:
    brand:
    interval: 30
    description: "ARP Table 採集"

  transceiver:
    url:
    source:
    brand:
    interval: 30
    description: "光模組 Tx/Rx 功率資料收集"

  # ... (version, neighbor, fan, error_count, power, ping, port_channel)
```

每個 job 欄位說明：

| 欄位 | 說明 |
|------|------|
| `url` | 外部 API endpoint（採集資料來源） |
| `source` | 資料來源系統（FNA / DNA） |
| `brand` | 設備廠牌（HPE / Cisco-IOS / Cisco-NXOS） |
| `interval` | 採集間隔（秒） |
| `description` | 任務描述 |

---

## Mock 測試模式

設定 `APP_ENV=testing`（見 `.env`）即可啟用 mock 模式：

- **IndicatorService**：`evaluate_all()` 直接回傳預定義的 mock 結果，涵蓋所有 8 個指標的通過/失敗情境
- **MockApiClient**：模擬外部 API 回傳 CLI 原始文字
- 用於前端開發測試，不需要真實的外部 API 和完整採集流程

Mock 結果範例（TEST-100）：

| 指標 | 通過/總數 | 通過率 |
|------|-----------|--------|
| ping | 31/34 | 91.2% |
| power | 33/34 | 97.1% |
| fan | 34/34 | 100.0% |
| transceiver | 198/204 | 97.1% |
| error_count | 674/680 | 99.1% |
| port_channel | 30/32 | 93.8% |
| uplink | 62/64 | 96.9% |
| version | 32/34 | 94.1% |

---

## 支援廠牌

| 廠牌 | 平台 | Parser 支援 |
|------|------|-------------|
| Cisco | IOS | transceiver, neighbor |
| Cisco | NX-OS | transceiver, neighbor, port_channel, error, fan, power |
| HPE | Comware | transceiver, neighbor, port_channel, error, fan, power, ping |
| Aruba | AOS-CX | transceiver |

---

## 環境變數

```bash
# .env
DB_HOST=localhost
DB_PORT=3306
DB_NAME=network_dashboard
DB_USER=admin
DB_PASSWORD=admin

EXTERNAL_API_SERVER=http://localhost:9000
EXTERNAL_API_TIMEOUT=30

APP_NAME=Network Dashboard
APP_DEBUG=true
APP_ENV=testing  # testing = mock 模式, development/production = 真實模式
API_PREFIX=/api/v1
```

---

## 技術棧

**後端**
- Python 3.9+, FastAPI, SQLAlchemy 2.0 (async), Pydantic 2
- MariaDB (aiomysql), APScheduler
- Plugin-based Parser, Repository Pattern

**前端**
- Vue 3, Vite, Tailwind CSS, ECharts
- Axios, Day.js, Vue Router

---

## 開發工具

```bash
# 格式化
black app/
isort app/

# Lint
ruff check app/
mypy app/

# Pre-commit
pre-commit install
```

---

## License

MIT
