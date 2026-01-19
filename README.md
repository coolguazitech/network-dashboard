# Network Dashboard - 網路設備歲修監控系統

一個用於監控網路設備歲修過程的 Dashboard 系統，支援前後對比、多種指標評估。

## 🚀 快速啟動

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

### 3. 啟動後端

```bash
uvicorn app.main:app --reload --port 8000
```

API 文件：`http://localhost:8000/api/docs`

### 4. 啟動前端

```bash
cd frontend
npm install
npm run dev
```

前端：`http://localhost:3000`

---

## 🔄 資料流架構

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Scheduled Job  │────▶│   Parser     │────▶│  DB (Raw Data)  │
│  (APScheduler)  │     │  (解析CLI)   │     │  collection_    │
│  定期撈資料     │     │              │     │  records        │
└─────────────────┘     └──────────────┘     └────────┬────────┘
        │                                             │
        │ 呼叫外部 API                                │ Indicator 查詢
        ▼                                             ▼
┌─────────────────┐                         ┌─────────────────┐
│  External API   │                         │   Indicator     │
│  (純文字回傳)   │                         │   .calculate()  │
└─────────────────┘                         │   用 Metric 計算│
                                            └────────┬────────┘
                                                     │
                                                     ▼
                                            ┌─────────────────┐
                                            │  DB (Results)   │
                                            │  indicator_     │
                                            │  results        │
                                            └────────┬────────┘
                                                     │
                                                     ▼
                                            ┌─────────────────┐
                                            │  Frontend API   │
                                            │  時間序列/Raw   │
                                            └─────────────────┘
```

### 為什麼需要 DB？

1. **時間序列圖表**：前端需要橫軸為時間的折線圖，需要歷史資料
2. **歲修前後對比**：PRE/POST 階段的資料需要保存才能比較
3. **系統重啟**：資料不能遺失
4. **多 Indicator 共用**：例如 transceiver raw data 可以同時算 Tx/Rx pass rate

---

## 🏗️ 目錄結構

```
network_dashboard/
├── app/
│   ├── api/                  # FastAPI 路由
│   ├── core/                 # 核心設定
│   │   ├── config.py         # pydantic-settings 設定
│   │   └── enums.py          # 列舉定義
│   ├── db/                   # 資料庫
│   │   ├── base.py           # SQLAlchemy 設定
│   │   └── models.py         # ORM 模型
│   ├── indicators/           # 指標系統
│   │   ├── base.py           # Indicator 抽象基類
│   │   ├── metrics.py        # Metric 評估類
│   │   └── transceiver.py    # TransceiverIndicator 實作
│   ├── parsers/              # Parser 系統 (Plugin-based)
│   │   ├── protocols.py      # Protocol 定義
│   │   ├── registry.py       # Auto-discovery Registry
│   │   └── plugins/          # Parser 插件
│   ├── repositories/         # Repository Pattern (資料存取層)
│   │   ├── base.py           # BaseRepository
│   │   ├── switch.py         # SwitchRepository
│   │   ├── collection_record.py
│   │   └── indicator_result.py
│   └── services/             # 服務層
│       ├── api_client.py     # 外部 API 客戶端
│       ├── data_collection.py # 資料收集服務
│       └── scheduler.py      # APScheduler 排程
├── config/                   # YAML 設定檔
│   ├── switches.yaml         # 設備定義
│   ├── indicators.yaml       # 指標定義
│   └── scheduler.yaml        # 排程設定
├── frontend/                 # Vue.js 前端
├── docker-compose.yml        # MariaDB + phpMyAdmin
└── pyproject.toml            # 專案設定
```

---

## 🎯 核心設計原則

### SOLID 原則應用

1. **Single Responsibility**: 每個類只做一件事
2. **Open-Closed**: Plugin-based 架構，新增功能不需修改現有程式碼
3. **Liskov Substitution**: 所有 Parser/Indicator 實作相同介面
4. **Interface Segregation**: 細分的 Protocol 定義
5. **Dependency Inversion**: 透過 Protocol 和 Repository 解耦

### Repository Pattern

```python
# 資料存取透過 Repository，不直接操作 Model
async with get_session_context() as session:
    repo = SwitchRepository(session)
    switches = await repo.get_active_switches()
```

### Scheduler 設計

```yaml
# config/scheduler.yaml
jobs:
  transceiver:
    indicator: transceiver
    interval: 300  # 每 5 分鐘
    enabled: true
```

---

## 📊 Metric 系統

支援多種評估類型：

| 類型 | 用途 | 範例 |
|------|------|------|
| `RangeMetric` | 範圍內判斷 | Tx Power -10~2 dBm |
| `ThresholdMetric` | 閾值判斷 | Error Count < 100 |
| `EqualsMetric` | 字串相等 | 版本是否升級成功 |
| `BooleanMetric` | 狀態判斷 | Fan 是否正常 |

---

## 📝 設定檔範例

### switches.yaml

```yaml
switches:
  - hostname: switch-new-01
    ip_address: 10.0.1.1
    vendor: cisco
    platform: nxos
    site: t_site

device_mappings:
  - old_hostname: switch-old-01
    new_hostname: switch-new-01

version_expectations:
  switch-new-01: "9.3(10)"
```

### scheduler.yaml

```yaml
jobs:
  transceiver:
    indicator: transceiver
    interval: 300
    enabled: true
```

---

## ⚙️ 環境變數

```bash
# .env
DB_HOST=localhost
DB_PORT=3306
DB_NAME=network_dashboard
DB_USER=admin
DB_PASSWORD=admin

EXTERNAL_API_SERVER=http://your-api-server.com
APP_DEBUG=true
```

---

## 📝 支援廠牌

| 廠牌 | 平台 | 狀態 |
|------|------|------|
| Cisco | IOS | ✅ |
| Cisco | NX-OS (N9K) | ✅ |
| HPE | ProCurve | ✅ |
| HPE | Comware | ✅ |
| Aruba | AOS | ✅ |
| Aruba | AOS-CX | ✅ |

---

## 🔧 開發工具

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

## 📄 License

MIT
