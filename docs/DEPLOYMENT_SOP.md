# NETORA 部署與開發 SOP

> **最新版本**: `v2.17.1` (2026-03-20)
> **重大更新**: Alembic migration 完整化、Indicators enum/schema 修復、歲修刪除級聯修復

## 目錄

- [🚀 公司端快速更新](#公司端快速更新-v222)
- [Part 1：無腦起服務（5 分鐘）](#part-1無腦起服務5-分鐘)
- [Part 2：開發指南（外部 API 串接）](#part-2開發指南外部-api-串接)
- [Part 3：打包 Image 重新推送](#part-3打包-image-重新推送)
- [附錄：故障排查](#附錄故障排查)

---

## 🚀 公司端快速更新 (v2.17.1)

### 更新內容摘要

**版本**: `coolguazi/network-dashboard-base:v2.17.1`

**新功能 (v2.16.0 → v2.17.1)**:
- ✅ **通訊錄階層分類**: 支援父分類→子分類一層架構，側欄樹狀展示
- ✅ **通訊錄 CSV 匯入/匯出**: 支援 `category_name` + `sub_category_name` 欄位，自動建立分類層級
- ✅ **通訊錄新欄位**: 新增部門、分機、備註欄位
- ✅ **client_id 主鍵**: Cases、ClientRecord、SeverityOverride 等 7 張表改用 client_id 作為關聯鍵
- ✅ **拓樸視覺化強化**: 連線標籤顯示節點名稱、狀態持久化 (localStorage)、30 秒動態輪詢
- ✅ **介面格式參考面板**: 側邊標籤常駐顯示，點擊展開完整參考表

**修復 (v2.17.1)**:
- ✅ **entrypoint.sh K8s 相容**: 新增 DB 等待迴圈（最多 60 秒），fresh DB 主動 create_all + stamp head
- ✅ **Alembic migration 完整化**: 新增 `l7f8g9h0i1j2` migration，涵蓋 client_id (7 表)、parent_id、contacts 新欄位、title 擴充、email 移除
- ✅ **歲修刪除級聯修復**: contact_categories 自引用 FK 先刪子分類再刪父分類；新增 SeverityOverride 刪除
- ✅ **Indicators API 修復**: IndicatorObjectType 新增 DEVICE 列舉值；DisplayConfigSchema/ObservedFieldSchema 欄位允許 None
- ✅ MAC 刪除級聯清理 (Case、ClientRecord、ClientComparison)
- ✅ Case API 回傳 client_id 欄位
- ✅ CVE 掃描通過（0 個 CRITICAL）

**影響範圍**: entrypoint 啟動流程、DB Migration、通訊錄、案件、MAC 清單、拓樸、Indicators

**DB Migration**: 此版本的 entrypoint.sh 已完全自動化：
- **全新 DB**: 等待 DB 就緒 → create_all 建表 → alembic stamp head（K8s/docker-compose 皆適用）
- **既有 DB**: 自動偵測版本 → alembic upgrade head
- **不再需要手動 ALTER TABLE**

### 在公司機器上執行（5 分鐘）

> **前提**：新版 image 已提交公司 registry 掃描通過。
> 公司環境無法 `git clone`/`git pull`，需從 GitHub 下載 ZIP。

```bash
# 1. 從 GitHub 下載最新 ZIP（在可上網的電腦操作，再傳到公司機器）
#    GitHub → Code → Download ZIP

# 2. 在公司機器上解壓並替換程式碼
unzip netora-main.zip
cp -r netora-main/* /path/to/netora/
cd /path/to/netora

# 3. 更新 .env 中的 image 版本號（如果 registry URL 有變）
#    確認 APP_IMAGE 指向公司 registry 的新版本

# 4. 重啟服務（alembic migration 自動執行）
docker compose -f docker-compose.production.yml up -d

# 5. 確認服務正常
docker compose -f docker-compose.production.yml ps
curl http://localhost:8000/health
```

### 驗證更新

1. 確認 health check 回傳 `scheduler_running: true`
2. 等待 60 秒，檢查系統日誌無 `success_rate` 相關錯誤
3. 前往「歲修設定」頁面，確認可正常開啟
4. **預期結果**: 所有客戶端應顯示「未偵測」狀態
5. 重新加入 ARP 來源，等待 30 秒
6. **預期結果**: 客戶端應從「未偵測」變為「已偵測」

### 回滾方案（如遇問題）

```bash
# 回到上一版本 v2.16.0
sed -i 's/network-dashboard-base:v2.17.1/network-dashboard-base:v2.16.0/' docker-compose.production.yml
docker compose -f docker-compose.production.yml pull
docker compose -f docker-compose.production.yml up -d
# 回滾 DB migration
docker exec netora_app alembic downgrade k6e7f8g9h0i1
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
# 1. 取得程式碼
#    開發環境: git clone <repo-url> netora && cd netora
#    公司環境: 從 GitHub 下載 ZIP 並解壓
unzip netora-main.zip && mv netora-main netora && cd netora

# 2. 建立環境設定
cp .env.production .env
```

編輯 `.env`，**必改項目**：

```ini
DB_PASSWORD=<改成強密碼>
DB_ROOT_PASSWORD=<改成強密碼>
JWT_SECRET=<改成隨機字串>
```

其他保持預設即可。

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
# 1. 從 GitHub 下載最新 ZIP 並解壓替換程式碼
# 2. 確認 .env 中 APP_IMAGE 指向新版 image
# 3. 重啟服務
docker compose -f docker-compose.production.yml up -d
```

---

## Part 2：開發指南（外部 API 串接）

### 2.1 架構概覽

```
┌──────────────────────────────────────────────────────┐
│  Base Image (coolguazi/network-dashboard-base:v2.16.0) │
│                                                       │
│  包含完整系統：                                         │
│  • Python 3.11 + 所有 pip 依賴                         │
│  • 前端靜態檔 (Vue 3 build)                            │
│  • FastAPI + SQLAlchemy + APScheduler                  │
│  • ConfiguredFetcher（通用 HTTP GET Fetcher）            │
│  • 所有 Parser plugins                                 │
│  • Indicator 評估引擎 + Dashboard API                   │
│  • 完整快照機制（每 30 秒確保資料一致性）                   │
└──────────────────────────────────────────────────────┘
```

**核心設計**：Base Image 已包含完整框架 + `ConfiguredFetcher`（通用 HTTP GET fetcher）。
只需在 `.env` 設定 `FETCHER_SOURCE__*__BASE_URL` 指向真實 API。**你只需要確保 Parser 能正確解析真實 API 回傳的格式。**

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

### 2.3 設定外部 API 連線（.env）

```ini
# ===== 外部 API 來源 (base_url + timeout) =====
FETCHER_SOURCE__FNA__BASE_URL=http://your-fna-server:8001
FETCHER_SOURCE__FNA__TIMEOUT=30
FETCHER_SOURCE__DNA__BASE_URL=http://your-dna-server:8001
FETCHER_SOURCE__DNA__TIMEOUT=30
FETCHER_SOURCE__GNMSPING__BASE_URL=http://your-gnmsping-server:8001
FETCHER_SOURCE__GNMSPING__TIMEOUT=60

# ===== Endpoint 模板（名稱必須與 scheduler.yaml 的 fetcher key 一致）=====
# FNA — 所有廠牌共用，IP 在 path 中
FETCHER_ENDPOINT__GET_GBIC_DETAILS=/switch/network/get_gbic_details/{switch_ip}
FETCHER_ENDPOINT__GET_CHANNEL_GROUP=/switch/network/get_channel_group/{switch_ip}
FETCHER_ENDPOINT__GET_ERROR_COUNT=/switch/network/get_interface_error_count/{switch_ip}
FETCHER_ENDPOINT__GET_STATIC_ACL=/switch/network/get_static_acl/{switch_ip}
FETCHER_ENDPOINT__GET_DYNAMIC_ACL=/switch/network/get_dynamic_acl/{switch_ip}

# DNA — 每個 device_type 用 __HPE/__IOS/__NXOS 後綴 + ?hosts={switch_ip}
# （預設值已內建於 config.py，可不設定；若需覆蓋則按以下格式）
FETCHER_ENDPOINT__GET_FAN__HPE=/api/v1/hpe/environment/display_fan?hosts={switch_ip}
FETCHER_ENDPOINT__GET_FAN__IOS=/api/v1/ios/environment/show_env_fan?hosts={switch_ip}
FETCHER_ENDPOINT__GET_FAN__NXOS=/api/v1/nxos/environment/show_environment_fan?hosts={switch_ip}
# ... 其餘 6 個 DNA API 同理（完整範例見 .env.production）
```

佔位符說明：
- **FNA**：`{switch_ip}` → 設備 IP 在 URL path 中，Bearer token 認證
  `GET {FNA_BASE_URL}/switch/network/get_gbic_details/10.1.1.1`
- **DNA**：用 `__HPE`/`__IOS`/`__NXOS` 後綴設定 per-device-type endpoint，
  IP 透過 `?hosts={switch_ip}` 顯式傳遞（模板含 `?` → 不自動附加其他 query params）
  `GET {DNA_BASE_URL}/api/v1/hpe/environment/display_fan?hosts=10.1.1.1`

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
# 使用遞增版本號（當前最新: v2.16.0）
bash scripts/build-and-push.sh v2.16.0
```

此腳本會依序：

1. **Build** — `docker buildx build` 產出 image
2. **CVE Scan** — Trivy 掃描 HIGH/CRITICAL 漏洞（報告存為 `trivy-report-v2.16.0.txt`）
   - ✅ 0 個 CRITICAL 才允許推送
   - ⚠️ HIGH 漏洞記錄但不阻擋（通常為系統函式庫）
3. **Push** — 推送到 DockerHub（`coolguazi/network-dashboard-base:v2.16.0` + `:latest`）

### 3.2 手動打包

```bash
# Build
docker buildx build --platform linux/amd64 \
    -f docker/base/Dockerfile \
    -t coolguazi/network-dashboard-base:v2.16.0 \
    --load .

# CVE Scan（可選）
trivy image --severity HIGH,CRITICAL coolguazi/network-dashboard-base:v2.16.0

# Push
docker login
docker push coolguazi/network-dashboard-base:v2.16.0
docker tag coolguazi/network-dashboard-base:v2.16.0 coolguazi/network-dashboard-base:latest
docker push coolguazi/network-dashboard-base:latest
```

### 3.3 公司端更新

> 公司環境無外網，不能 `docker pull` / `git pull`。更新流程：

1. **外部**：Build 新版 image → push DockerHub → 提交公司 registry 掃描
2. **外部**：從 GitHub 下載最新程式碼 ZIP
3. **公司**：解壓 ZIP 替換程式碼
4. **公司**：確認 `.env` 中 `APP_IMAGE` 指向公司 registry 的新版 image
5. **公司**：重啟服務

```bash
docker compose -f docker-compose.production.yml up -d
```

### 3.4 Docker 檔案結構

```
docker/base/Dockerfile          ← 基礎映像檔（完整系統，可獨立運行 Mock 模式）
docker/production/Dockerfile    ← 生產映像檔（覆蓋公司專屬的 Fetcher/Parser 實作）
docker-compose.production.yml   ← 一鍵起服務（app + db + phpmyadmin）
.env.production                 ← 環境變數範本
scripts/build-and-push.sh       ← 一鍵 build + scan + push
```

- **Base Image**：包含完整系統 + 所有 Parser plugins
- **Production Image**：以 Base Image 為基礎，覆蓋真實 API 的 Fetcher/Parser 實作
- 一般情況只需修改代碼後重新打包 Base Image 推送即可
- 只有在公司端有獨立於 repo 的專屬代碼時，才需要用 Production Dockerfile

---

## 附錄：故障排查

### 常見問題

| 症狀 | 可能原因 | 解決方式 |
|------|---------|---------|
| Dashboard 全部「無資料」 | 採集尚未完成或 API 未連線 | 檢查 fetcher 來源設定和 API 連通性 |
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
# .env 中設定 FETCHER_SOURCE__*__BASE_URL 指向真實 API
docker-compose -f docker-compose.production.yml restart app

# ========== 公司端更新（當前版本 v2.16.0） ==========
# 1. 從 GitHub 下載最新 ZIP 並解壓替換程式碼
# 2. 確認 .env 中 APP_IMAGE 指向公司 registry 的新版 image
# 3. 重啟服務
docker compose -f docker-compose.production.yml up -d
```
