# NETORA 公司端 SOP

> **版本**: v2.0.0 (2026-02-22)
> **適用情境**: Image 已預先 build 好並推上 DockerHub → 公司掃描後取得 registry URL → 部署 → 接真實 API → Parser 開發

---

## 目錄

- [Phase 1：公司端初始部署](#phase-1公司端初始部署)
- [Phase 2：Parser 開發（核心工作）](#phase-2parser-開發核心工作)
- [Phase 3：最終部署上線](#phase-3最終部署上線)
- [附錄 A：故障排查](#附錄-a故障排查)
- [附錄 B：Parser 對照表](#附錄-bparser-對照表)
- [附錄 C：ParsedData 模型欄位](#附錄-cparseddata-模型欄位)

---

## Phase 1：公司端初始部署

> 到公司後的第一步：讓系統先跑起來。

### 1.1 取得 Image

將以下 image 提交公司 registry 掃描：

| Image | 用途 |
|-------|------|
| `coolguazi/network-dashboard-base:v2.0.0` | 主應用 |
| `coolguazi/netora-mariadb:10.11` | 資料庫 |
| `coolguazi/netora-mock-api:v2.0.0` | Mock API（僅 Mock 模式） |
| `coolguazi/netora-seaweedfs:4.13` | S3 物件儲存 |
| `coolguazi/netora-phpmyadmin:5.2` | DB 管理介面 |

掃描通過後會拿到公司內部的 image URL，例如：

```
registry.company.com/netora/network-dashboard-base:v2.0.0
registry.company.com/netora/netora-mariadb:10.11
...
```

記下這些 URL，後面多處要用。

> **重要**：所有 image 必須在外面預先 build 好再帶進公司。公司環境**無法執行 `docker build`**，因為 Dockerfile 中的 `pip install`、`apt-get`、`git clone` 等指令需要外網。

### 1.2 下載 Repo

從 GitHub 網頁下載 ZIP（公司不能 git clone）：

1. 打開 `https://github.com/<你的帳號>/netora`
2. 點 `Code` → `Download ZIP`
3. 解壓到工作目錄：

```bash
unzip netora-main.zip
mv netora-main netora
cd netora
```

### 1.3 設定 Image URL

在 `.env` 中加入公司 registry 的 image URL：

```bash
# 加到 .env（或 .env.mock / .env.production 複製前先加）
APP_IMAGE=registry.company.com/netora/network-dashboard-base:v2.0.0
DB_IMAGE=registry.company.com/netora/netora-mariadb:10.11
MOCK_IMAGE=registry.company.com/netora/netora-mock-api:v2.0.0
```

拉取 image：

```bash
docker pull registry.company.com/netora/network-dashboard-base:v2.0.0
docker pull registry.company.com/netora/netora-mariadb:10.11
docker pull registry.company.com/netora/netora-mock-api:v2.0.0
# SeaweedFS / phpMyAdmin 如果也過了掃描，也 pull
```

### 1.4 建立環境設定 & 啟動服務

提供兩種模式，**擇一**即可：

#### 模式 A：Mock 模式（先驗證系統能跑，不需要真實 API）

```bash
cp .env.mock .env
docker compose -f docker-compose.production.yml --profile mock up -d
```

> `.env.mock` 開箱即用，所有 API 指向內建的 mock-api 容器，不需改任何設定。

#### 模式 B：真實模式（接公司 API）

```bash
cp .env.production .env
```

編輯 `.env`，**必改項目**：

```ini
# ===== 密碼（必改）=====
DB_PASSWORD=<強密碼>
DB_ROOT_PASSWORD=<強密碼>
JWT_SECRET=<隨機字串>

# ===== Image URL（必改）=====
APP_IMAGE=registry.company.com/netora/network-dashboard-base:v2.0.0

# ===== 真實 API 來源（必改）=====
# FNA: Bearer token 認證; DNA: 不需認證; 皆無 SSL
FETCHER_SOURCE__FNA__BASE_URL=http://<FNA伺服器IP>:<port>
FETCHER_SOURCE__FNA__TIMEOUT=30
FETCHER_SOURCE__FNA__TOKEN=<FNA Bearer token>
FETCHER_SOURCE__DNA__BASE_URL=http://<DNA伺服器IP>:<port>
FETCHER_SOURCE__DNA__TIMEOUT=30

# ===== GNMS Ping（必改，POST + JSON body，每個 tenant_group 各自的 base URL）=====
GNMSPING__TIMEOUT=60
GNMSPING__ENDPOINT=/api/v1/ping
GNMSPING__TOKEN=<GNMSPING token（所有 tenant 共用）>
GNMSPING__BASE_URLS__F18=http://<GNMSPING-F18伺服器IP>:<port>
GNMSPING__BASE_URLS__F6=http://<GNMSPING-F6伺服器IP>:<port>
GNMSPING__BASE_URLS__AP=http://<GNMSPING-AP伺服器IP>:<port>
GNMSPING__BASE_URLS__F14=http://<GNMSPING-F14伺服器IP>:<port>
GNMSPING__BASE_URLS__F12=http://<GNMSPING-F12伺服器IP>:<port>

# ===== Endpoint 路徑（必改）=====
# FNA — 所有廠牌共用同一個 endpoint
FETCHER_ENDPOINT__GET_GBIC_DETAILS=/switch/network/get_gbic_details/{switch_ip}
FETCHER_ENDPOINT__GET_CHANNEL_GROUP=/switch/network/get_channel_group/{switch_ip}
FETCHER_ENDPOINT__GET_UPLINK=/switch/network/get_neighbors/{switch_ip}
FETCHER_ENDPOINT__GET_ERROR_COUNT=/switch/network/get_error_count/{switch_ip}
FETCHER_ENDPOINT__GET_STATIC_ACL=/switch/network/get_static_acl/{switch_ip}
FETCHER_ENDPOINT__GET_DYNAMIC_ACL=/switch/network/get_dynamic_acl/{switch_ip}

# DNA — 每個 device_type 各自的 endpoint
FETCHER_ENDPOINT__GET_MAC_TABLE=/api/v1/{device_type}/mac-table/{switch_ip}
FETCHER_ENDPOINT__GET_FAN=/api/v1/{device_type}/fan/{switch_ip}
FETCHER_ENDPOINT__GET_POWER=/api/v1/{device_type}/power/{switch_ip}
FETCHER_ENDPOINT__GET_VERSION=/api/v1/{device_type}/version/{switch_ip}
FETCHER_ENDPOINT__GET_INTERFACE_STATUS=/api/v1/{device_type}/interface-status/{switch_ip}
```

啟動（不需要 `--profile mock`）：

```bash
docker compose -f docker-compose.production.yml up -d
```

> **注意**：S3 credentials（MINIO__ACCESS_KEY / SECRET_KEY）已預設為 `minioadmin`，不需要改。

#### 模式切換

| 切換方向 | 操作 |
|----------|------|
| Mock → 真實 | `cp .env.production .env`，填入真實 API，重啟不帶 `--profile mock` |
| 真實 → Mock | `cp .env.mock .env`，重啟帶 `--profile mock` |

重啟指令：

```bash
docker compose -f docker-compose.production.yml --profile mock down
docker compose -f docker-compose.production.yml --profile mock up -d   # Mock
# 或
docker compose -f docker-compose.production.yml up -d                  # 真實
```

### 1.5 確認服務狀態

等待約 30 秒，確認所有容器正常：

```bash
docker compose -f docker-compose.production.yml ps
```

預期結果：

| 容器 | 埠號 | 狀態 | 備註 |
|------|------|------|------|
| netora_app | 8000 | healthy | |
| netora_db | 3306 | healthy | |
| netora_s3 | 8333 | healthy | |
| netora_pma | 8080 | running | |
| netora_mock_api | 9999 | running | 僅 Mock 模式 |

### 1.6 Health check + 首次登入

> **資料庫遷移**：容器啟動時會自動執行 `alembic upgrade head`，不需要手動操作。
> 啟動日誌會顯示 `Alembic migration completed.`。

```bash
curl http://localhost:8000/health
```

1. 瀏覽器打開 `http://localhost:8000`
2. 帳號：`root` / 密碼：`admin123`（首次登入後建議改密碼）
3. 建立歲修（Maintenance）
4. 匯入設備清單 CSV（包含 hostname, IP, device_type）
5. 匯入 MAC 清單 CSV
6. 系統自動開始排程採集

> **此時 Dashboard 上的指標可能顯示異常或無資料**，因為 Parser 是第一版，
> 可能無法正確解析真實 API 回傳的格式。這是正常的，Phase 2 會修正。

### 1.7 驗證 API 連通性

先確認 Fetcher 能連到外部 API：

```bash
# 進入容器
docker exec -it netora_app bash

# 測試 FNA 連通（替換成真實 IP，FNA 需 Bearer token）
# FNA API：get_gbic_details, get_channel_group, get_uplink, get_error_count, get_static_acl, get_dynamic_acl
curl -v -H "Authorization: Bearer <FNA_TOKEN>" \
  "http://<FNA伺服器IP>:<port>/switch/network/get_gbic_details/10.1.1.1"

# 測試 DNA 連通（不需認證）
# DNA API：get_mac_table, get_fan, get_power, get_version, get_interface_status
curl -v "http://<DNA伺服器IP>:<port>/api/v1/hpe/fan/display_fan?hosts=10.1.1.1"

# 測試 GNMSPING 連通（POST + JSON body）
curl -v -X POST "http://<GNMSPING伺服器IP>:<port>/api/v1/ping" \
  -H "Content-Type: application/json" \
  -d '{"app_name":"network_change_orchestrator","token":"<GNMSPING_TOKEN>","addresses":["10.1.1.1"]}'

# 離開容器
exit
```

如果連不上，檢查：
- `.env` 中的 `FETCHER_SOURCE__*__BASE_URL` 是否正確
- Docker 容器的 DNS 設定（是否需要加 `--dns` 或 `extra_hosts`）
- 防火牆規則

---

## Phase 2：Parser 開發（核心工作）

> 這是在公司的主要工作：用真實 API 回傳的 raw data 調整 Parser 邏輯。
>
> **核心循環**：`撈資料 → 測試 Parser → 產生 AI Bundle → 餵給公司 AI → 貼回修正後的 Parser → 重複`

### 2.1 前置：安裝 Python 環境（在容器外執行）

如果公司機器有 Python 3.11+：

```bash
cd netora
pip install httpx pyyaml pydantic pydantic-settings pymysql bcrypt pyjwt sqlalchemy alembic aiomysql
```

如果公司機器**沒有** Python，可以全部在容器內操作（見 [2.1b 容器內操作](#21b-容器內操作替代方案)）。

### 2.1b 容器內操作（替代方案）

如果不想在 host 安裝 Python，所有操作都可以在容器內進行。
需要先修改 `docker-compose.production.yml`，讓關鍵目錄可寫入：

在 `app` 服務下新增 `volumes`：

```yaml
  app:
    # ... 其他設定不變 ...
    volumes:
      - app_data:/app/data
      - ./config/seaweedfs_s3.json:/app/config/seaweedfs_s3.json:ro
      # ↓ 新增以下三行（讓 parser 開發可以在容器內讀寫）
      - ./config:/app/config
      - ./test_data:/app/test_data
      - ./app/parsers/plugins:/app/app/parsers/plugins
```

然後重啟並進入容器：

```bash
docker-compose -f docker-compose.production.yml up -d
docker exec -it netora_app bash

# make 和 scripts 已預裝在 image 裡，直接使用
cd /app
```

> **重要**：以下步驟 2.2 ~ 2.8 的所有 `make` 指令，
> 在 host 有 Python 就在 host 的 `netora/` 目錄執行；
> 否則就在容器內的 `/app` 目錄執行。

### 2.2 填寫 API 測試設定

編輯 `config/api_test.yaml`，填入所有 `TODO` 欄位：

```yaml
# ── API 來源 ──
sources:
  FNA:
    base_url: "http://<FNA伺服器IP>:<port>"    # ★ 填入
    timeout: 30
    auth:
      type: header
      token_env: FNA_TOKEN                      # 如需 token，設定環境變數 FNA_TOKEN=xxx
  DNA:
    base_url: "http://<DNA伺服器IP>:<port>"    # ★ 填入
    timeout: 30
    auth: null

# ── Endpoint 路徑 ──
endpoints:
  # FNA（所有廠牌共用）
  get_gbic_details:     "/switch/network/get_gbic_details/{ip}"       # ★ 填入
  get_channel_group:    "/switch/network/get_channel_group/{ip}"      # ★ 填入
  get_uplink:           "/switch/network/get_neighbors/{ip}"          # ★ 填入
  get_error_count:      "/switch/network/get_error_count/{ip}"        # ★ 填入
  get_static_acl:       "/switch/network/get_static_acl/{ip}"        # ★ 填入
  get_dynamic_acl:      "/switch/network/get_dynamic_acl/{ip}"       # ★ 填入

  # DNA（每個 device_type 各自的 endpoint）
  get_mac_table:
    hpe:  "/api/v1/hpe/mac-table/display_mac_table"                  # ★ 填入
    ios:  "/api/v1/ios/mac-table/show_mac_table"
    nxos: "/api/v1/nxos/mac-table/show_mac_table"
  get_fan:
    hpe:  "/api/v1/hpe/fan/display_fan"
    ios:  "/api/v1/ios/fan/show_fan"
    nxos: "/api/v1/nxos/fan/show_fan"
  get_power:
    hpe:  "/api/v1/hpe/power/display_power"
    ios:  "/api/v1/ios/power/show_power"
    nxos: "/api/v1/nxos/power/show_power"
  get_version:
    hpe:  "/api/v1/hpe/version/display_version"
    ios:  "/api/v1/ios/version/show_version"
    nxos: "/api/v1/nxos/version/show_version"
  get_interface_status:
    hpe:  "/api/v1/hpe/interface-status/display_interface"
    ios:  "/api/v1/ios/interface-status/show_interface"
    nxos: "/api/v1/nxos/interface-status/show_interface"

# ── 測試目標（每種廠牌至少一台）──
targets:
  - ip: "10.x.x.x"           # ★ 填入 HPE 交換機 IP
    hostname: "SW-HPE-01"
    device_type: hpe
  - ip: "10.x.x.x"           # ★ 填入 Cisco IOS 交換機 IP
    hostname: "SW-IOS-01"
    device_type: ios
  - ip: "10.x.x.x"           # ★ 填入 Cisco NX-OS 交換機 IP
    hostname: "SW-NXOS-01"
    device_type: nxos
```

如果 FNA 需要認證 token：

```bash
export FNA_TOKEN=<你的FNA API token>
```

### 2.3 驗證 URL（Dry Run）

先不實際呼叫，只印出 URL 確認路徑正確：

```bash
make fetch-dry
```

預期輸出類似：

```
GET http://fna-server:8001/switch/network/get_fan/10.1.1.1
GET http://dna-server:8001/api/v1/hpe/fan/display_fan?hosts=10.1.1.1
...
```

確認所有 URL 路徑正確，沒有空白或錯誤。

### 2.4 撈取真實 API Raw Data

```bash
# 撈取所有 API 的 raw data（存到 test_data/raw/）
make fetch
```

> **首次執行會自動清空 `test_data/raw/`**

輸出範例：

```
[1/33] get_fan / hpe / 10.1.1.1 ... OK (2,341 bytes)
[2/33] get_fan / ios / 10.2.2.2 ... OK (1,890 bytes)
[3/33] get_fan / nxos / 10.3.3.3 ... FAIL (Connection refused)
...
```

如果某些 API 失敗（連線逾時等），先確認 URL 正確。可以只撈特定 API：

```bash
# 只撈 get_fan
API=get_fan make fetch

# 只撈特定交換機
TARGET=10.1.1.1 make fetch

# 加長 timeout
TIMEOUT=60 make fetch
```

撈完後，確認 `test_data/raw/` 有 `.txt` 檔案：

```bash
ls test_data/raw/
# 預期看到: get_fan_hpe_10.1.1.1.txt, get_fan_ios_10.2.2.2.txt, ...
```

### 2.5 測試 Parser

```bash
make parse
```

輸出範例：

```
  OK     get_fan_hpe_dna         3 records   (get_fan_hpe_10.1.1.1.txt)
  EMPTY  get_fan_ios_dna         0 records   (get_fan_ios_10.2.2.2.txt)
  ERROR  get_uplink_nxos_fna     ValueError  (get_uplink_nxos_10.3.3.3.txt)

  SUMMARY: 10 OK / 8 EMPTY / 2 ERROR
```

- **OK** = Parser 正確解析出資料
- **EMPTY** = Parser regex 沒有匹配到任何資料（需要修正）
- **ERROR** = Parser 丟出例外（需要修正）

### 2.6 產生 AI 評估 Bundle（核心步驟）

```bash
make parse-debug
```

此命令會為每個需要修正的 parser 產生一個 `.md` 檔案到 `test_data/debug/`：

```
  EMPTY  get_fan_ios_dna         → test_data/debug/get_fan_ios_dna.md
  ERROR  get_uplink_nxos_fna     → test_data/debug/get_uplink_nxos_fna.md
     OK  get_fan_hpe_dna         → test_data/debug/get_fan_hpe_dna.md

  Generated:  15 bundles
  Converged:  0 (AI confirmed OK)
  Remaining:  15 need AI review

  Workflow:
  1. Open a .md file from test_data/debug/
  2. Copy entire content → paste to AI
  3. AI replies OK → make parse-ok P=get_fan_hpe_dna
     AI replies with code → paste into app/parsers/plugins/
  4. Run make parse-debug again → repeat until all converged
```

### 2.7 AI 協助修正 Parser（迭代循環）

**對每個 `.md` 檔案重複以下步驟**：

#### Step 1: 複製 Bundle 內容給公司 AI

```bash
cat test_data/debug/get_fan_ios_dna.md
```

**整個 .md 檔案的內容**全部複製，貼到公司 AI 的對話框。

> Bundle 內容包含：
> - Parser 的任務說明（AI 看得懂的 prompt）
> - 當前 parser 原始碼
> - ParsedData 模型定義
> - 真實 raw data 樣本
> - 當前 parse 結果（OK/EMPTY/ERROR）
> - AI 的回覆規則（OK 或回傳完整修正後的 parser）

#### Step 2: AI 回覆處理

**情況 A — AI 回覆 `OK`**：

表示 parser 輸出正確。標記為已收斂：

```bash
make parse-ok P=get_fan_ios_dna
```

**情況 B — AI 回覆完整 Python 程式碼**：

1. 複製 AI 回覆的完整 parser 程式碼
2. 貼到對應的 parser 檔案：

```bash
# 檔名 = parser_command + _parser.py
vi app/parsers/plugins/get_fan_ios_dna_parser.py
```

3. **整個檔案內容替換**為 AI 回覆的程式碼（不要只改部分！）
4. 儲存

#### Step 3: 重新測試

```bash
# 只測試改過的 parser
API=get_fan make parse

# 或全部重新測試
make parse
```

#### Step 4: 重新產生 Bundle

```bash
make parse-debug
```

已收斂的 parser 會自動跳過，只處理仍有問題的。

#### 重複直到全部收斂

```
  All parsers converged!
```

### 2.8 Parser 開發完成檢查清單

- [ ] 所有 34 個 parser 都顯示 `OK` 或 `CONVERGED`
- [ ] 至少用 3 台以上不同設備的 raw data 驗證過
- [ ] `make parse` 的 EMPTY 和 ERROR 數量 = 0
- [ ] 修改過的 parser 檔案都已存檔

---

## Phase 3：最終部署上線

> Parser 開發完成後，重建 image 並正式部署。

### 3.1 重建 Production Image

在公司機器上，用 `docker/production/Dockerfile` 把修改過的 parser 疊加到 base image：

```bash
cd netora

# BASE_IMAGE = 公司 registry 掃描通過後的 URL
docker build \
    --build-arg BASE_IMAGE=registry.company.com/netora/network-dashboard-base:v2.0.0 \
    -f docker/production/Dockerfile \
    -t netora-production:v2.0.0 \
    .
```

> **注意**：如果 production Dockerfile build 有問題，可以直接用 base Dockerfile 重建整個 image：
> ```bash
> docker buildx build --platform linux/amd64 \
>     -f docker/base/Dockerfile \
>     -t netora-production:v2.0.0 \
>     --load .
> ```

### 3.2 更新 docker-compose 使用新 image

編輯 `.env`：

```ini
APP_IMAGE=netora-production:v2.0.0
```

或直接改 `docker-compose.production.yml` 的 `image` 欄位。

### 3.3 移除開發用 volume（如果有加）

如果在 Phase 2 有加 volume mount（步驟 2.1b），**現在移除**：

```yaml
  app:
    volumes:
      - app_data:/app/data
      - ./config/seaweedfs_s3.json:/app/config/seaweedfs_s3.json:ro
      # ↓ 刪除以下三行（parser 已 bake 進 image，不再需要 mount）
      # - ./config:/app/config
      # - ./test_data:/app/test_data
      # - ./app/parsers/plugins:/app/app/parsers/plugins
```

### 3.4 重啟服務

```bash
docker-compose -f docker-compose.production.yml down
docker-compose -f docker-compose.production.yml up -d

# 確認狀態
docker-compose -f docker-compose.production.yml ps
curl http://localhost:8000/health
```

### 3.5 驗證上線

> 資料庫遷移會在容器啟動時自動執行。

1. 登入 `http://localhost:8000`（root / admin123）
2. 選擇歲修 ID
3. 等待 5 分鐘讓排程採集跑一輪（每 300 秒 = 5 分鐘）
4. 檢查 Dashboard 指標：
   - 應看到各指標有通過率百分比
   - 不應出現紫色「採集異常」（除非 API 確實連不上）
   - 不應出現灰色「無資料」（除非是剛啟動還沒跑完第一輪）
5. 檢查系統日誌頁面，確認沒有 ERROR

```bash
docker logs netora_app -f --tail 200
```

### 3.6 確認 Parser 載入狀態

```bash
docker exec netora_app python -c "
from app.parsers.registry import auto_discover_parsers, parser_registry
count = auto_discover_parsers()
print(f'Loaded {count} parser modules')
for p in parser_registry.list_parsers():
    print(f'  {p.device_type} / {p.command}')
print(f'Total: {len(parser_registry._parsers)} parsers')
"
```

預期應有 34 個 parser 被載入。

---

## 附錄 A：故障排查

### 常見問題

| 症狀 | 可能原因 | 解決方式 |
|------|---------|---------|
| `make fetch` 全部 Connection refused | API URL 錯誤 | 確認 `config/api_test.yaml` 的 `sources.*.base_url` |
| `make fetch` 部分 401 Unauthorized | FNA 需要 token | `.env` 設定 `FETCHER_SOURCE__FNA__TOKEN=xxx`；`make fetch` 用 `export FNA_TOKEN=xxx` |
| `make parse` 全部 EMPTY | 真實 API 格式與 mock 不同 | 正常，進入 `make parse-debug` AI 修正流程 |
| `make fetch-dry` 路徑有空白 | endpoint 沒填 | 填寫 `config/api_test.yaml` 中的 TODO |
| Dashboard 顯示「採集異常」| Fetcher 連不上 API | 確認 `.env` 中 `FETCHER_SOURCE__*__BASE_URL` 正確 |
| Dashboard 全部「無資料」| 排程未執行或 API 未連 | 等 5 分鐘讓排程跑一輪，檢查日誌 |
| App 啟動後退出 | DB 未就緒 | 確認 DB 容器 healthy：`docker-compose ps` |
| Image pull 失敗 | Registry 不可達 | 確認公司 registry URL 正確 |
| 登入失敗 401 | JWT_SECRET 變更 | 清除瀏覽器 localStorage，重新登入 |
| 圖片上傳失敗 | SeaweedFS 沒 ready | 確認 netora_s3 容器 healthy |

### 離線傳入 Image（如果 Registry 不可達）

在公司外面：

```bash
docker save coolguazi/network-dashboard-base:v2.0.0 | gzip > netora-app-v2.0.0.tar.gz
docker save coolguazi/netora-mariadb:10.11 | gzip > netora-mariadb-10.11.tar.gz
docker save coolguazi/netora-mock-api:v2.0.0 | gzip > netora-mock-api-v2.0.0.tar.gz
docker save coolguazi/netora-seaweedfs:4.13 | gzip > netora-seaweedfs-4.13.tar.gz
docker save coolguazi/netora-phpmyadmin:5.2 | gzip > netora-phpmyadmin-5.2.tar.gz
```

帶 tar.gz 到公司後：

```bash
docker load < netora-app-v2.0.0.tar.gz
docker load < netora-mariadb-10.11.tar.gz
docker load < netora-mock-api-v2.0.0.tar.gz
docker load < netora-seaweedfs-4.13.tar.gz
docker load < netora-phpmyadmin-5.2.tar.gz
```

### 版本更新（重要）

公司環境**無法 `docker build`**（無外網，`pip install` / `apt-get` / `git clone` 會失敗）。

更新流程：

1. **在公司外面**（有網路的環境）rebuild image 並推到 registry 或匯出 tar.gz
2. **帶進公司**後 `docker pull` 或 `docker load`
3. 重啟服務：

```bash
docker compose -f docker-compose.production.yml --profile mock down   # Mock 模式
docker compose -f docker-compose.production.yml --profile mock up -d
# 或
docker compose -f docker-compose.production.yml down                  # 真實模式
docker compose -f docker-compose.production.yml up -d
```

### 除錯指令

```bash
# 查看容器日誌
docker logs netora_app -f --tail 100

# 進入容器
docker exec -it netora_app bash

# 測試 API 連通性（容器內）
curl -v "http://<FNA_URL>/switch/network/get_fan/10.1.1.1"

# DB 備份
docker exec netora_db mysqldump -u root -p<密碼> netora > backup_$(date +%Y%m%d).sql

# DB 還原
docker exec -i netora_db mysql -u root -p<密碼> netora < backup.sql

# 重置所有資料（從零開始）
docker-compose -f docker-compose.production.yml down -v
docker-compose -f docker-compose.production.yml up -d
# alembic 會自動執行
```

---

## 附錄 B：Parser 對照表

### 檔案命名規則

```
app/parsers/plugins/{api_name}_{device_type}_{source}_parser.py
```

### 完整 Parser 清單（34 個）

| # | Parser 檔案 | command | device_type | 資料來源 | 輸出模型 |
|---|------------|---------|-------------|---------|---------|
| 1 | `get_gbic_details_hpe_fna_parser.py` | `get_gbic_details_hpe_fna` | HPE | FNA | TransceiverData |
| 2 | `get_gbic_details_ios_fna_parser.py` | `get_gbic_details_ios_fna` | CISCO_IOS | FNA | TransceiverData |
| 3 | `get_gbic_details_nxos_fna_parser.py` | `get_gbic_details_nxos_fna` | CISCO_NXOS | FNA | TransceiverData |
| 4 | `get_channel_group_hpe_fna_parser.py` | `get_channel_group_hpe_fna` | HPE | FNA | PortChannelData |
| 5 | `get_channel_group_ios_fna_parser.py` | `get_channel_group_ios_fna` | CISCO_IOS | FNA | PortChannelData |
| 6 | `get_channel_group_nxos_fna_parser.py` | `get_channel_group_nxos_fna` | CISCO_NXOS | FNA | PortChannelData |
| 7 | `get_uplink_hpe_fna_parser.py` | `get_uplink_hpe_fna` | HPE | FNA | NeighborData |
| 8 | `get_uplink_ios_fna_parser.py` | `get_uplink_ios_fna` | CISCO_IOS | FNA | NeighborData |
| 9 | `get_uplink_nxos_fna_parser.py` | `get_uplink_nxos_fna` | CISCO_NXOS | FNA | NeighborData |
| 10 | `get_error_count_hpe_fna_parser.py` | `get_error_count_hpe_fna` | HPE | FNA | InterfaceErrorData |
| 11 | `get_error_count_ios_fna_parser.py` | `get_error_count_ios_fna` | CISCO_IOS | FNA | InterfaceErrorData |
| 12 | `get_error_count_nxos_fna_parser.py` | `get_error_count_nxos_fna` | CISCO_NXOS | FNA | InterfaceErrorData |
| 13 | `get_static_acl_hpe_fna_parser.py` | `get_static_acl_hpe_fna` | HPE | FNA | AclData |
| 14 | `get_static_acl_ios_fna_parser.py` | `get_static_acl_ios_fna` | CISCO_IOS | FNA | AclData |
| 15 | `get_static_acl_nxos_fna_parser.py` | `get_static_acl_nxos_fna` | CISCO_NXOS | FNA | AclData |
| 16 | `get_dynamic_acl_hpe_fna_parser.py` | `get_dynamic_acl_hpe_fna` | HPE | FNA | AclData |
| 17 | `get_dynamic_acl_ios_fna_parser.py` | `get_dynamic_acl_ios_fna` | CISCO_IOS | FNA | AclData |
| 18 | `get_dynamic_acl_nxos_fna_parser.py` | `get_dynamic_acl_nxos_fna` | CISCO_NXOS | FNA | AclData |
| 19 | `get_mac_table_hpe_dna_parser.py` | `get_mac_table_hpe_dna` | HPE | DNA | MacTableData |
| 20 | `get_mac_table_ios_dna_parser.py` | `get_mac_table_ios_dna` | CISCO_IOS | DNA | MacTableData |
| 21 | `get_mac_table_nxos_dna_parser.py` | `get_mac_table_nxos_dna` | CISCO_NXOS | DNA | MacTableData |
| 22 | `get_fan_hpe_dna_parser.py` | `get_fan_hpe_dna` | HPE | DNA | FanStatusData |
| 23 | `get_fan_ios_dna_parser.py` | `get_fan_ios_dna` | CISCO_IOS | DNA | FanStatusData |
| 24 | `get_fan_nxos_dna_parser.py` | `get_fan_nxos_dna` | CISCO_NXOS | DNA | FanStatusData |
| 25 | `get_power_hpe_dna_parser.py` | `get_power_hpe_dna` | HPE | DNA | PowerData |
| 26 | `get_power_ios_dna_parser.py` | `get_power_ios_dna` | CISCO_IOS | DNA | PowerData |
| 27 | `get_power_nxos_dna_parser.py` | `get_power_nxos_dna` | CISCO_NXOS | DNA | PowerData |
| 28 | `get_version_hpe_dna_parser.py` | `get_version_hpe_dna` | HPE | DNA | VersionData |
| 29 | `get_version_ios_dna_parser.py` | `get_version_ios_dna` | CISCO_IOS | DNA | VersionData |
| 30 | `get_version_nxos_dna_parser.py` | `get_version_nxos_dna` | CISCO_NXOS | DNA | VersionData |
| 31 | `get_interface_status_hpe_dna_parser.py` | `get_interface_status_hpe_dna` | HPE | DNA | InterfaceStatusData |
| 32 | `get_interface_status_ios_dna_parser.py` | `get_interface_status_ios_dna` | CISCO_IOS | DNA | InterfaceStatusData |
| 33 | `get_interface_status_nxos_dna_parser.py` | `get_interface_status_nxos_dna` | CISCO_NXOS | DNA | InterfaceStatusData |
| 34 | `ping_batch_parser.py` | `ping_batch` | 所有 | GNMSPING | PingResultData |

### 三處命名必須一致

```
1. config/scheduler.yaml    →  get_fan:              ← fetcher key
                                 source: DNA

2. .env                     →  FETCHER_ENDPOINT__GET_FAN=/api/v1/{device_type}/fan/{switch_ip}

3. Parser class             →  command = "get_fan_hpe_dna"
                                device_type = DeviceType.HPE
```

命名不一致 = 系統找不到 Parser = Dashboard 顯示「無資料」

---

## 附錄 C：ParsedData 模型欄位

> Parser 的輸出必須符合以下模型。欄位名稱不能改。

| 模型 | 用途 | 必填欄位 | 可選欄位 |
|------|------|---------|---------|
| `TransceiverData` | 光模組 | interface_name, channels | temperature, voltage |
| `TransceiverChannelData` | 光模組通道 | channel(1-4) | tx_power, rx_power, bias_current_ma |
| `InterfaceErrorData` | CRC 錯誤 | interface_name | crc_errors(=0，inbound+outbound 加總) |
| `FanStatusData` | 風扇 | fan_id, status | speed_rpm, speed_percent |
| `PowerData` | 電源 | ps_id, status | input_status, output_status, capacity_watts, actual_output_watts |
| `VersionData` | 韌體 | version | model, serial_number, uptime |
| `NeighborData` | 鄰居 | local_interface, remote_hostname, remote_interface | remote_platform |
| `PortChannelData` | Port-Channel | interface_name, status, members | protocol, member_status |
| `AclData` | ACL | interface_name | acl_number |
| `MacTableData` | MAC 表 | mac_address, interface_name | vlan_id(=0) |
| `InterfaceStatusData` | 介面狀態 | interface_name, link_status | speed, duplex |
| `PingResultData` | Ping | target, is_reachable, success_rate | avg_rtt_ms |

> status 欄位（如 FanStatusData.status）會自動正規化：
> `"OK"` / `"Ok"` / `"ok"` → `"ok"` ;  `"Normal"` → `"normal"`
>
> MAC 位址自動正規化：
> `"AA-BB-CC-DD-EE-FF"` / `"AABB.CCDD.EEFF"` → `"AA:BB:CC:DD:EE:FF"`

---

## 快速指令卡（列印帶著用）

```
# ===== Phase 1: 起服務 =====
unzip netora-main.zip && cd netora-main
docker pull <公司registry>/network-dashboard-base:v2.0.0
cp .env.production .env
# 編輯 .env：密碼 + APP_IMAGE + API URL + Token + endpoint
docker-compose -f docker-compose.production.yml up -d
# alembic 自動執行，等 30 秒
curl http://localhost:8000/health
# 瀏覽器 http://localhost:8000 → root/admin123

# ===== Phase 2: Parser 開發循環 =====
vi config/api_test.yaml                     # 填 TODO：sources + endpoints + targets
make fetch-dry                              # 確認 URL 正確
make fetch                                  # 撈取 raw data
make parse                                  # 測試 parser
make parse-debug                            # 產生 AI bundle

# 對每個 test_data/debug/xxx.md：
#   1. cat test_data/debug/xxx.md → 複製全部內容給公司 AI
#   2. AI 回 OK → make parse-ok P=xxx
#   3. AI 回代碼 → 貼到 app/parsers/plugins/xxx_parser.py
#   4. make parse-debug → 重複到全部 converged

# ===== Phase 3: 最終部署 =====
docker build \
    --build-arg BASE_IMAGE=<公司registry>/network-dashboard-base:v2.0.0 \
    -f docker/production/Dockerfile \
    -t netora-production:v2.0.0 .
# 編輯 .env: APP_IMAGE=netora-production:v2.0.0
docker-compose -f docker-compose.production.yml down
docker-compose -f docker-compose.production.yml up -d
# alembic 自動執行
```
