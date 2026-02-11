# NETORA 部署與開發 SOP

> **最新版本**: `v1.2.0` (2026-02-09)
> **重大更新**: 修復 ARP 來源處理邏輯，確保客戶端偵測狀態即時反映

## 目錄

- [🚀 公司端快速更新](#公司端快速更新-v120)
- [Part 1：無腦起服務（5 分鐘）](#part-1無腦起服務5-分鐘)
- [Part 2：開發指南（外部 API 串接）](#part-2開發指南外部-api-串接)
- [Part 3：打包 Image 重新推送](#part-3打包-image-重新推送)
- [附錄：故障排查](#附錄故障排查)

---

## 🚀 公司端快速更新 (v1.2.0)

### 更新內容摘要

**版本**: `coolguazi/network-dashboard-base:v1.2.0`

**關鍵修復**:
- ✅ 修復客戶端比較頁面資料不同步問題
- ✅ 修正 Mock Fetcher 不尊重 ARP 來源配置的 bug
- ✅ 實現完整快照機制（每 30 秒確保資料一致性）
- ✅ CVE 掃描通過（0 個 CRITICAL，4 個 HIGH 系統函式庫漏洞可接受）

**影響範圍**: 客戶端偵測與比較功能

### 在公司機器上執行（3 分鐘）

```bash
# 1. 進入專案目錄
cd /path/to/netora

# 2. 修改 docker-compose.production.yml 的 image 版本
sed -i 's/network-dashboard-base:v[0-9.]*\+/network-dashboard-base:v1.2.0/' docker-compose.production.yml

# 3. 拉取新版 image
docker-compose -f docker-compose.production.yml pull

# 4. 重啟服務（零停機時間約 10 秒）
docker-compose -f docker-compose.production.yml up -d

# 5. 確認服務正常
docker-compose -f docker-compose.production.yml ps
curl http://localhost:8000/health
```

### 驗證更新

1. 登入系統後，前往「客戶端比較」頁面
2. 移除所有 ARP 來源
3. 等待 30 秒後重新整理
4. **預期結果**: 所有客戶端應顯示「未偵測」狀態
5. 重新加入 ARP 來源，等待 30 秒
6. **預期結果**: 客戶端應從「未偵測」變為「已偵測」

### 回滾方案（如遇問題）

```bash
# 回到上一版本 v1.1.0
sed -i 's/network-dashboard-base:v1.2.0/network-dashboard-base:v1.1.0/' docker-compose.production.yml
docker-compose -f docker-compose.production.yml pull
docker-compose -f docker-compose.production.yml up -d
```

---

## Part 1：無腦起服務（5 分鐘）

### 前置需求

| 項目 | 最低版本 | 說明 |
|------|---------|------|
| Docker Engine | 20.10+ | 必須支援 BuildKit |
| Docker Compose | v1.25+ | 使用 `docker-compose`（獨立安裝版） |
| 磁碟空間 | 2GB+ | image + DB 資料 |
| 網路 | 可達 DockerHub | 拉取 base image |

### 步驟

```bash
# 1. 拉取程式碼
git clone <repo-url> netora && cd netora

# 2. 建立環境設定
cp .env.production .env
```

編輯 `.env`，**必改項目**：

```ini
DB_PASSWORD=<改成強密碼>
DB_ROOT_PASSWORD=<改成強密碼>
JWT_SECRET=<改成隨機字串>
```

其他保持預設即可（`USE_MOCK_API=true` 為演示模式）。

```bash
# 3. 一鍵啟動（app + db + phpmyadmin）
docker-compose -f docker-compose.production.yml up -d

# 4. 確認三個容器都 healthy
docker-compose -f docker-compose.production.yml ps
```

預期結果：

| 容器 | 埠號 | 狀態 |
|------|------|------|
| netora_app | 8000 | healthy |
| netora_db | 3306 | healthy |
| netora_pma | 8080 | running |

```bash
# 5. Health check
curl http://localhost:8000/health
```

### 首次登入

1. 瀏覽器打開 `http://localhost:8000`
2. 帳號：`root` / 密碼：`admin123`
3. 建立歲修 → 匯入設備清單 CSV → 匯入 MAC 清單 CSV
4. 系統自動開始排程採集（每 30 秒一輪）

### 管理資料庫

phpMyAdmin：`http://localhost:8080`（使用 .env 中的 DB_USER / DB_PASSWORD 登入）

### 停止 / 重啟

```bash
# 停止
docker-compose -f docker-compose.production.yml down

# 停止並清除資料庫（重新開始）
docker-compose -f docker-compose.production.yml down -v

# 重啟
docker-compose -f docker-compose.production.yml restart
```

### 更新版本

```bash
# 修改 docker-compose.production.yml 中的 image 版本號（如 v1.2.0 → v1.3.0）
docker-compose -f docker-compose.production.yml pull
docker-compose -f docker-compose.production.yml up -d
```

---

## Part 2：開發指南（外部 API 串接）

### 2.1 架構概覽

```
┌──────────────────────────────────────────────────────┐
│  Base Image (coolguazi/network-dashboard-base:v1.2.0) │
│                                                       │
│  包含完整系統：                                         │
│  • Python 3.11 + 所有 pip 依賴                         │
│  • 前端靜態檔 (Vue 3 build)                            │
│  • FastAPI + SQLAlchemy + APScheduler                  │
│  • ConfiguredFetcher（通用 HTTP GET Fetcher）            │
│  • MockFetcher（開發測試用）                             │
│  • 所有 Parser plugins                                 │
│  • Indicator 評估引擎 + Dashboard API                   │
│  • 完整快照機制（每 30 秒確保資料一致性）                   │
└──────────────────────────────────────────────────────┘
```

**核心設計**：Base Image 已包含完整框架 + `ConfiguredFetcher`（通用 HTTP GET fetcher）。
切換 `USE_MOCK_API=false` 即自動走真實 API。**你只需要確保 Parser 能正確解析真實 API 回傳的格式。**

資料流：

```
外部 API（FNA / DNA / GNMSPING）
    ↓ HTTP GET（ConfiguredFetcher 自動處理）
    ↓ raw_output: str（API 回傳的原始文字）
Parser（你需要寫/修改的地方）
    ↓ list[ParsedData]（結構化資料）
Indicator（評估通過/失敗）
    ↓ 結果存入 DB → Dashboard 顯示
```

### 2.2 Fetcher / Parser 對應表

| Fetcher Name | API 來源 | 說明 | Parser 數量 |
|-------------|---------|------|------------|
| transceiver | FNA | 光模組 Tx/Rx 功率 | 3 (generic → per device_type) |
| port_channel | FNA | Port-Channel 狀態 | 3 |
| uplink | FNA | Uplink 鄰居拓撲 | 3 |
| error_count | FNA | Interface 錯誤計數 | 3 |
| acl | FNA | ACL 編號 | 3 |
| arp_table | FNA | ARP 表 | 3 |
| mac_table | DNA | MAC 表 | 3 (per device_type) |
| fan | DNA | 風扇狀態 | 3 |
| power | DNA | 電源供應器 | 3 |
| version | DNA | 韌體版本 | 3 |
| ping | GNMSPING | 設備可達性 | 1 |

Parser 按設備類型分：

| 設備類型 | device_type | FNA Parser 命名 | DNA Parser 命名 |
|---------|-------------|----------------|----------------|
| HPE Comware | `DeviceType.HPE` | `get_{indicator}_hpe_fna` | `get_{indicator}_hpe_dna` |
| Cisco IOS | `DeviceType.CISCO_IOS` | `get_{indicator}_ios_fna` | `get_{indicator}_ios_dna` |
| Cisco NXOS | `DeviceType.CISCO_NXOS` | `get_{indicator}_nxos_fna` | `get_{indicator}_nxos_dna` |

### 2.3 Parser 開發工具鏈（推薦流程）

使用工具鏈可以快速驗證 API 串接並生成 Parser：

```
┌─ config/api_test.yaml ─────────────────────────────────┐
│ 定義所有 API（endpoint, source, target_filter）         │
│ → 到公司只需填入真實 base_url 和 IP                      │
└───────────────┬─────────────────────────────────────────┘
                │
     make test-apis  (或 make docker-test-apis)
                │
                ▼
┌─ reports/api_test_*.json ──────────────────────────────┐
│ 每個 API 的測試結果：status, raw_data, response_time   │
│ → 確認哪些 API 能正常打通                               │
└───────────────┬─────────────────────────────────────────┘
                │
     make gen-parsers  (或 make docker-gen-parsers)
                │
                ▼
┌─ app/parsers/plugins/*_parser.py ──────────────────────┐
│ 自動生成骨架，含 raw_data 範例在 docstring 中            │
│ → 複製 raw_data 給 AI，請 AI 寫 parse() 邏輯           │
└───────────────┬─────────────────────────────────────────┘
                │
     make test-parsers  (或 make docker-test-parsers)
                │
                ▼
┌─ reports/parser_test_*.json ───────────────────────────┐
│ passed: parse() 正常回傳 > 0 筆資料                     │
│ empty: 骨架尚未填寫 parse() 邏輯                        │
│ failed: parse() 拋出例外                               │
└─────────────────────────────────────────────────────────┘
```

**本地開發（在家）**：

```bash
# 1. 啟動 Mock Server（另一個終端機）
python scripts/mock_api_server.py

# 2. 執行完整工具鏈
make test-apis       # 批次測試所有 API
make gen-parsers     # 生成 parser 骨架
make test-parsers    # 驗證 parser

# 或一次全部跑完
make all
```

**公司環境（容器內執行）**：

```bash
# 在容器內執行
make docker-test-apis
make docker-gen-parsers
make docker-test-parsers
```

**填寫 Parser 邏輯（AI 輔助）**：

1. 打開 `reports/api_test_*.json`，找到該 API 的 `raw_data`
2. 複製 raw_data 給 AI（ChatGPT / 公司內部 AI）
3. 告訴 AI 目標的 ParsedData 類型（見 2.7 節）
4. 將 AI 產出的 `parse()` 邏輯貼入骨架檔案
5. `make test-parsers` 驗證結果

### 2.4 設定外部 API 連線（.env）

```ini
# ===== 關閉 Mock 模式 =====
USE_MOCK_API=false

# ===== 外部 API 來源 (base_url + timeout) =====
FETCHER_SOURCE__FNA__BASE_URL=http://your-fna-server:8001
FETCHER_SOURCE__FNA__TIMEOUT=30
FETCHER_SOURCE__DNA__BASE_URL=http://your-dna-server:8001
FETCHER_SOURCE__DNA__TIMEOUT=30
FETCHER_SOURCE__GNMSPING__BASE_URL=http://your-gnmsping-server:8001
FETCHER_SOURCE__GNMSPING__TIMEOUT=60

# ===== Endpoint 模板 =====
FETCHER_ENDPOINT__TRANSCEIVER=/api/v1/transceiver/{switch_ip}
FETCHER_ENDPOINT__FAN=/api/v1/fan/{switch_ip}
FETCHER_ENDPOINT__POWER=/api/v1/power/{switch_ip}
FETCHER_ENDPOINT__VERSION=/api/v1/version/{switch_ip}
FETCHER_ENDPOINT__UPLINK=/api/v1/neighbors/{switch_ip}
FETCHER_ENDPOINT__ERROR_COUNT=/api/v1/error-count/{switch_ip}
FETCHER_ENDPOINT__PORT_CHANNEL=/api/v1/port-channel/{switch_ip}
FETCHER_ENDPOINT__PING=/api/v1/ping/batch
```

佔位符說明：
- `{switch_ip}` → 設備 IP（自動從 FetchContext 帶入）
- `{device_type}` → 設備類型（`hpe`/`ios`/`nxos`）
- 其他自訂 key → 自動成為 query params

### 2.5 修改 Parser（核心工作）

Parser 由工具鏈自動生成骨架，開發者只需填寫 `parse()` 邏輯。

Parser 檔案位置：`app/parsers/plugins/{api_name}_parser.py`

範例 — `get_transceiver_hpe_fna_parser.py`（自動生成後填寫）：

```python
from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, TransceiverData
from app.parsers.registry import parser_registry


class GetTransceiverHpeFnaParser(BaseParser[TransceiverData]):
    device_type = DeviceType.HPE
    command = "get_transceiver_hpe_fna"       # ★ 與 api_test.yaml 的 API name 對應

    def parse(self, raw_output: str) -> list[TransceiverData]:
        import re
        results = []
        for line in raw_output.strip().splitlines():
            match = re.match(
                r"(\S+)\s+([-\d.]+)\s+([-\d.]+)", line
            )
            if match:
                results.append(TransceiverData(
                    interface_name=match.group(1),
                    tx_power=float(match.group(2)),
                    rx_power=float(match.group(3)),
                ))
        return results


parser_registry.register(GetTransceiverHpeFnaParser())
```

> **注意**：`__init__.py` 不需要手動 import，系統使用 `auto_discover_parsers()` 自動掃描 plugins/ 目錄。

### 2.6 三處命名必須一致（關鍵！）

```
1. scheduler.yaml   →  fetchers:
                          transceiver:        ← fetcher name
                            source: FNA

2. .env             →  FETCHER_ENDPOINT__TRANSCEIVER=...    ← 大寫版

3. Parser class     →  command = "get_transceiver_hpe_fna"  ← 與 api_test.yaml 對應
                        device_type = DeviceType.HPE
```

Parser 的 `command` 對應 `api_test.yaml` 中的 API name（含廠牌後綴），
而非 scheduler.yaml 的 fetcher name。

名稱不一致 = 系統找不到 Parser = 資料流斷裂 → 顯示「無採集數據」。

### 2.7 ParsedData 資料模型（Parser 輸出契約）

Parser 的回傳類型必須是以下之一（不能改欄位名）：

| 模型 | 用途 | 必填欄位 | 可選欄位（可為空/有預設值） |
|------|------|---------|--------------------------|
| `TransceiverData` | 光模組診斷 | interface_name | tx_power, rx_power, temperature, voltage |
| `InterfaceErrorData` | 介面錯誤計數 | interface_name | crc_errors(=0), input_errors(=0), output_errors(=0), collisions(=0), giants(=0), runts(=0) |
| `FanStatusData` | 風扇狀態 | fan_id, status | speed_rpm, speed_percent |
| `PowerData` | 電源供應器 | ps_id, status | input_status, output_status, capacity_watts, actual_output_watts |
| `VersionData` | 韌體版本 | version | model, serial_number, uptime |
| `NeighborData` | 鄰居 CDP/LLDP | local_interface, remote_hostname, remote_interface | remote_platform |
| `PortChannelData` | Port-Channel | interface_name, status, members | protocol, member_status |
| `PingData` | Ping 可達性 | target, is_reachable, success_rate | avg_rtt_ms |

> **必填** = 型別為 `str` / `int` / `bool` 且無預設值，Parser 必須給值，否則 Pydantic 驗證報錯。
> **可選** = 型別帶 `| None`（預設 None）或有 `= 預設值`，不傳也不會報錯。
> 枚舉欄位（如 status）由 Pydantic 自動正規化：`"OK"` → `"ok"`、`"Normal"` → `"normal"`，不需手動轉換。

### 2.8 新增 API Source

如果有一個全新的外部 API（不在 FNA/DNA/GNMSPING 之中）：

1. `.env` 新增：
   ```ini
   FETCHER_SOURCE__CMDB__BASE_URL=http://cmdb-server:8080
   FETCHER_SOURCE__CMDB__TIMEOUT=30
   ```

2. `app/core/config.py` 的 `FetcherSourceConfig` 加欄位：
   ```python
   cmdb: SourceEntry | None = None
   ```

3. `config/scheduler.yaml` 新增 fetcher entry：
   ```yaml
   fetchers:
     new_indicator:
       source: CMDB
       interval: 120
   ```

4. `.env` 新增 endpoint：
   ```ini
   FETCHER_ENDPOINT__NEW_INDICATOR=/api/v1/new-data/{switch_ip}
   ```

5. 寫對應的 Parser plugin（見 2.5）

---

## Part 3：打包 Image 重新推送

### 3.1 一鍵打包（推薦）

修改完 Parser/Fetcher 代碼後：

```bash
# 使用遞增版本號（當前最新: v1.2.0）
bash scripts/build-and-push.sh v1.3.0
```

此腳本會依序：

1. **Build** — `docker buildx build` 產出 image
2. **CVE Scan** — Trivy 掃描 HIGH/CRITICAL 漏洞（報告存為 `trivy-report-v1.3.0.txt`）
   - ✅ 0 個 CRITICAL 才允許推送
   - ⚠️ HIGH 漏洞記錄但不阻擋（通常為系統函式庫）
3. **Push** — 推送到 DockerHub（`coolguazi/network-dashboard-base:v1.3.0` + `:latest`）

### 3.2 手動打包

```bash
# Build
docker buildx build --platform linux/amd64 \
    -f docker/base/Dockerfile \
    -t coolguazi/network-dashboard-base:v1.3.0 \
    --load .

# CVE Scan（可選）
trivy image --severity HIGH,CRITICAL coolguazi/network-dashboard-base:v1.3.0

# Push
docker login
docker push coolguazi/network-dashboard-base:v1.3.0
docker tag coolguazi/network-dashboard-base:v1.3.0 coolguazi/network-dashboard-base:latest
docker push coolguazi/network-dashboard-base:latest
```

### 3.3 公司端更新

在部署的機器上：

```bash
# 修改 docker-compose.production.yml 中的 image 版本號
# 然後：
docker-compose -f docker-compose.production.yml pull
docker-compose -f docker-compose.production.yml up -d
```

### 3.4 Docker 檔案結構

```
docker/base/Dockerfile          ← 基礎映像檔（完整系統，可獨立運行 Mock 模式）
docker/production/Dockerfile    ← 生產映像檔（覆蓋公司專屬的 Fetcher/Parser 實作）
docker-compose.production.yml   ← 一鍵起服務（app + db + phpmyadmin）
.env.production                 ← 環境變數範本
scripts/build-and-push.sh       ← 一鍵 build + scan + push
```

- **Base Image**：包含完整系統 + MockFetcher + 所有 Parser plugins，可獨立運行演示
- **Production Image**：以 Base Image 為基礎，覆蓋真實 API 的 Fetcher/Parser 實作
- 一般情況只需修改代碼後重新打包 Base Image 推送即可
- 只有在公司端有獨立於 repo 的專屬代碼時，才需要用 Production Dockerfile

---

## 附錄：故障排查

### 常見問題

| 症狀 | 可能原因 | 解決方式 |
|------|---------|---------|
| Dashboard 全部「無資料」 | Mock 模式收斂中 | 等待 MOCK_PING_CONVERGE_TIME（預設 600 秒） |
| 所有指標「無採集數據」 | Parser 未載入 or 名稱不一致 | 檢查 parser_registry 載入狀態（見下方） |
| 紫色狀態「採集異常」 | Fetcher 連不上外部 API | 檢查 `.env` BASE_URL + 網路連通性 |
| 登入失敗 401 | JWT_SECRET 變更 | 清除瀏覽器 localStorage 重新登入 |
| 部分設備無資料 | 該設備類型缺少 Parser | 檢查 device_type 是否有對應 parser |
| App 啟動後立刻退出 | DB 尚未就緒 | 確認 docker-compose 中的 depends_on + healthcheck 設定正確 |

### 除錯指令

```bash
# 查看容器日誌
docker logs netora_app -f --tail 100

# 確認 Fetcher 註冊狀態
docker logs netora_app 2>&1 | grep -i "registered.*fetcher"

# 確認 Parser 註冊狀態
docker exec netora_app python -c "
from app.parsers.registry import parser_registry
for k in parser_registry.list_parsers():
    print(f'  {k.device_type} / {k.command}')
print(f'Total: {len(parser_registry.list_parsers())} parsers')
"

# 進容器除錯
docker exec -it netora_app bash

# 測試 API 連通
curl -v http://fna-server:8001/api/v1/transceiver/10.1.1.1

# DB 備份
docker exec netora_db mysqldump -u root -p${DB_ROOT_PASSWORD} netora > backup_$(date +%Y%m%d).sql

# DB 還原
docker exec -i netora_db mysql -u root -p${DB_ROOT_PASSWORD} netora < backup.sql
```

### 重置所有資料

```bash
docker-compose -f docker-compose.production.yml down -v
docker-compose -f docker-compose.production.yml up -d
```

`-v` 會刪除資料庫 volume，啟動後重新建表。

---

## 快速參考

```
# ========== 一鍵起服務（Mock 演示） ==========
cp .env.production .env        # 改密碼
docker-compose -f docker-compose.production.yml up -d
# → http://localhost:8000  登入 root/admin123

# ========== 切換真實 API ==========
# .env 中設定 USE_MOCK_API=false + 填入 API URL
docker-compose -f docker-compose.production.yml restart app

# ========== 開發迴圈（工具鏈） ==========
1. make test-apis   → 批次打 API，拿到 raw_data（reports/api_test_*.json）
2. make gen-parsers → 生成 parser 骨架（app/parsers/plugins/）
3. 填 parse() 邏輯  → 複製 raw_data 給 AI 產出程式碼
4. make test-parsers→ 驗證 parser 輸出
5. 打包推送         → bash scripts/build-and-push.sh v1.3.0

# ========== 公司端更新（當前版本 v1.2.0） ==========
# 修改 docker-compose.production.yml 中的版本號
sed -i 's/v[0-9.]*\+/v1.3.0/' docker-compose.production.yml
docker-compose -f docker-compose.production.yml pull
docker-compose -f docker-compose.production.yml up -d
```
