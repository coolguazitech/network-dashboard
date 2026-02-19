# NETORA — 歲修驗收自動化平台

網路設備歲修監控系統 — 8 大指標自動採集評估、客戶端前後 Compare、一鍵 Sanity Check。

支援 HPE、Cisco IOS、Cisco NXOS 三大廠牌/OS。

---

## 頁面預覽

### Dashboard — 即時掌握全局進度

![Dashboard](docs/screenshots/dashboard.png)

8 個指標即時通過率（光模組、風扇、電源、版本、Uplink、Port-Channel、CRC Error、Ping），點擊展開失敗清單定位問題設備。閾值可在 UI 即時調整。

| ![Dashboard 詳細](docs/screenshots/dashboard_detail.png) | ![閾值設定](docs/screenshots/threshold_config.png) |
|:---:|:---:|
| Dashboard 完整頁面 | 閾值設定彈窗 |

### 客戶端比對 — 多 Checkpoint 快照追蹤 Client 變化

![Comparison](docs/screenshots/comparison.png)

定時自動快照，選取任意兩個時間點對比 Client 變化。MAC 於新舊設備間移動自動視為正常遷移。

### 全功能 Web 介面

| ![設備管理](docs/screenshots/devices.png) | ![Client 清單](docs/screenshots/client_list.png) |
|:---:|:---:|
| 設備管理 | Client 清單 |
| ![設定頁面](docs/screenshots/settings.png) | ![報告匯出](docs/screenshots/report_preview.png) |
| 設定頁面 | 報告匯出 |

### 平台管理

| ![通訊錄](docs/screenshots/contacts.png) | ![帳號管理](docs/screenshots/user_management.png) | ![系統日誌](docs/screenshots/system_logs.png) |
|:---:|:---:|:---:|
| 通訊錄 | 帳號管理 | 系統日誌 |

---

## Quick Start

### Docker 部署（推薦）

```bash
git clone <repo-url> netora && cd netora
cp .env.production .env
# 編輯 .env：修改 DB_PASSWORD、DB_ROOT_PASSWORD、JWT_SECRET

docker-compose -f docker-compose.production.yml up -d
```

瀏覽器開啟 `http://localhost:8000`，帳號 `root` / 密碼 `admin123`。

> 詳細部署步驟見 [DEPLOYMENT_SOP.md](docs/DEPLOYMENT_SOP.md)

### 本地開發

```bash
# Python
python3 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"

# Frontend
cd frontend && npm install && cd ..

# 環境變數
cp .env.example .env

# 啟動資料庫
docker-compose up -d

# 啟動 Backend
uvicorn app.main:app --reload --port 8000
```

開發模式下透過 `docker-compose.dev.yaml` 啟動獨立的 Mock API Server，自動產生具有時間收斂行為的模擬資料，不需外部 API。

前端已預編譯至 `static/`，FastAPI 直接 serve；若需開發前端：

```bash
cd frontend && npm run dev    # http://localhost:3000
```

---

## 資料流架構

```
scheduler.yaml 定義 fetcher name + source + interval
.env 定義 FETCHER_ENDPOINT__{NAME} = endpoint 模板
    → DataCollectionService._collect_for_maintenance_device(collection_type)
        → fetcher_registry.get_or_raise(collection_type)
            → ConfiguredFetcher.fetch(ctx) → FetchResult(raw_output)
                → parser_registry.get(device_type, collection_type)
                    → Parser.parse(raw_output) → list[ParsedData]
                        → Indicator.evaluate() → pass/fail → Dashboard
```

關鍵設計：
- **採集與評估分離** — Fetcher/Parser 寫 DB，Indicator 從 DB 讀取評估，互不阻塞
- **Mock 解耦** — Mock API Server 獨立容器，主應用零 mock 程式碼
- **智慧快取** — SHA-256 hash 偵測資料變化，不變不寫 DB
- **Per-maintenance 閾值** — 每場歲修獨立閾值設定

---

## 指標總覽

| 指標 | 說明 | 分母來源 | 通過條件 |
|------|------|----------|----------|
| Ping | 設備連通性 | MaintenanceDeviceList | 可達且成功率 >= 80% |
| 光模組 | Tx/Rx/溫度/電壓 | 採集光模塊數 | 功率與溫度在閾值內 |
| 風扇 | 風扇運轉狀態 | 採集設備數 | 所有風扇 ok/good/normal |
| 電源 | PSU 供電狀態 | 採集設備數 | 所有 PSU ok/good/normal |
| 版本 | 韌體版本比對 | 採集設備數 | 與期望版本一致 |
| Uplink | 上行鏈路鄰居 | 期望清單 | 鄰居符合期望 |
| Port-Channel | LAG 成員完整性 | 期望清單 | 所有成員 UP |
| 錯誤計數 | CRC/Error 計數 | 採集介面數 | 未超過閾值 |

---

## 目錄結構

```
app/
├── main.py                        # FastAPI 入口
├── api/endpoints/                  # REST API 端點
├── core/
│   ├── config.py                  # pydantic-settings (.env)
│   ├── enums.py                   # DeviceType, OperationalStatus
│   └── timezone.py                # 時區處理
├── db/
│   ├── base.py                    # SQLAlchemy async engine
│   └── models.py                  # ORM 模型
├── fetchers/
│   ├── base.py                    # BaseFetcher, FetchContext, FetchResult
│   ├── registry.py                # FetcherRegistry + setup_fetchers()
│   └── configured.py              # ConfiguredFetcher (通用 HTTP GET)
├── indicators/                    # 8 種指標評估器 (BaseIndicator)
├── parsers/
│   ├── protocols.py               # BaseParser, ParsedData 型別
│   ├── registry.py                # ParserRegistry (auto-discover, generic fallback)
│   └── plugins/                   # Parser 實作 (hpe_*, cisco_ios_*, cisco_nxos_*, ping)
├── repositories/                  # Data access layer
└── services/
    ├── data_collection.py         # 指標資料採集
    ├── client_collection_service.py  # 客戶端資料採集
    ├── client_comparison_service.py  # 客戶端前後對比
    ├── indicator_service.py       # Dashboard 指標彙整
    ├── scheduler.py               # APScheduler 排程管理
    ├── change_cache.py            # SHA-256 hash 變化偵測快取
    ├── system_log.py              # 系統日誌服務
    └── threshold_service.py       # Per-maintenance 閾值管理

config/
├── scheduler.yaml                 # 排程設定 (fetcher name, source, interval)
└── client_comparison.yaml         # Client 比對設定

mock_server/                       # 獨立 Mock API Server (Docker 容器)

frontend/                          # Vue 3 + Vite + Tailwind + ECharts
docker-compose.dev.yaml            # 開發用 (app + db + mock-api + phpMyAdmin)
docker-compose.production.yml      # 生產部署 (app + db + phpMyAdmin)
```

---

## 環境變數

參考 `.env.example`：

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `DB_HOST` | `localhost` | MariaDB 位址 |
| `DB_PORT` | `3306` | MariaDB 埠號 |
| `DB_NAME` | `netora` | 資料庫名稱 |
| `JWT_SECRET` | — | JWT 簽名金鑰（生產環境必改） |
| `FETCHER_SOURCE__FNA__BASE_URL` | `http://localhost:8001` | FNA API 位址 |
| `FETCHER_SOURCE__DNA__BASE_URL` | `http://localhost:8001` | DNA API 位址 |
| `FETCHER_ENDPOINT__*` | — | 各 fetcher 的 endpoint 模板 |
| `TRANSCEIVER_TX_POWER_MIN` | `-12.0` | 光模塊 TX 功率下限 (dBm) |
| `TIMEZONE` | `Asia/Taipei` | 系統時區 |

---

## 技術棧

**後端** — Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Pydantic 2, MariaDB (aiomysql), APScheduler

**前端** — Vue 3, Vite, Tailwind CSS, ECharts, Axios, Vue Router

**部署** — Docker, Docker Compose

---

## 文件索引

| 文件 | 內容 |
|------|------|
| [USER_AND_DEV_GUIDE.md](docs/USER_AND_DEV_GUIDE.md) | 系統概覽 + 前端使用說明（保姆級）+ 開發人員指南（擴充 Parser/Fetcher） |
| [DEPLOYMENT_SOP.md](docs/DEPLOYMENT_SOP.md) | 部署 SOP + 外部 API 串接 + Docker Image 打包推送 |
| [PPT_OUTLINE.md](docs/PPT_OUTLINE.md) | 簡報大綱與截圖清單 |
