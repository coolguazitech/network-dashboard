# NETORA 公司端 SOP

> **版本**: v2.5.2 (2026-03-01)
> **適用情境**: Image 已預先 build 好並推上 DockerHub → 公司掃描後取得 registry URL → 部署 → 接真實 API → Parser 開發
>
> **v2.5.2 變更摘要**（基於 HPE FF 5945 真實設備 SNMP 驗證）:
> - **LLDP 鄰居解析修正**：`_parse_lldp_remote_index` 支援 >= 3 段索引（真實設備 TimeMark 可能很大），修正鄰居資料全部被跳過的問題
> - **LAG ActorOperState Hex-STRING 修正**：`dot3adAggPortActorOperState` 回傳 OCTET STRING，pysnmp 渲染為 hex 字串（如 `0x3d`），新增 `_parse_oper_state_byte` 正確解析
> - **Transceiver 銅纜 SFP 處理**：`hh3cTransceiverCurRXPower` 對銅纜模組回傳 `"Copper"` 字串而非數值，改為跳過非數值回應避免錯誤的 0.0 dBm 資料
>
> **v2.5.0 變更摘要**:
> - Cisco IOS per-VLAN MAC table、pysnmp v6 API 修正、Mock VTP/BRIDGE-MIB 模擬資料
>
> **v2.4.0 變更摘要**:
> - 設備清單排序：Ping 不到的新設備優先、舊設備其次
> - `.env.mock` 預設改為 SNMP Mock 模式
> - 多個 Bug 修正（Case MAC 大小寫、RESOLVED 排序 NULL 處理等）

---

## 目錄

- [Phase 1：公司端初始部署](#phase-1公司端初始部署)
- [Phase 1b：SNMP 模式驗證與除錯](#phase-1bsnmp-模式驗證與除錯)
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
| `coolguazi/network-dashboard-base:v2.5.2` | 主應用 |
| `coolguazi/netora-mariadb:10.11` | 資料庫 |
| `coolguazi/netora-mock-server:v2.5.2` | Mock API（僅 Mock 模式） |
| `coolguazi/netora-seaweedfs:4.13` | S3 物件儲存 |
| `coolguazi/netora-phpmyadmin:5.2` | DB 管理介面 |

掃描通過後會拿到公司內部的 image URL，例如：

```
registry.company.com/netora/network-dashboard-base:v2.5.2
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
APP_IMAGE=registry.company.com/netora/network-dashboard-base:v2.5.2
DB_IMAGE=registry.company.com/netora/netora-mariadb:10.11
MOCK_IMAGE=registry.company.com/netora/netora-mock-server:v2.5.2
```

拉取 image：

```bash
docker pull registry.company.com/netora/network-dashboard-base:v2.5.2
docker pull registry.company.com/netora/netora-mariadb:10.11
docker pull registry.company.com/netora/netora-mock-server:v2.5.2
# SeaweedFS / phpMyAdmin 如果也過了掃描，也 pull
```

### 1.4 建立環境設定 & 啟動服務

提供兩種模式，**擇一**即可：

#### 模式 A：SNMP Mock 模式（推薦，先驗證系統能跑）

```bash
cp .env.mock .env
docker compose -f docker-compose.production.yml --profile mock up -d
```

> `.env.mock` 預設為 `COLLECTION_MODE=snmp` + `SNMP_MOCK=true`。
> 10 個 SNMP 指標由 app 內建 MockSnmpEngine 產生模擬資料，Ping 和 ACL 自動 fallback 到 mock-api。
> 如需改回傳統 API Mock 模式，將 `.env` 中的 `COLLECTION_MODE` 改為 `api` 並註解掉 `SNMP_MOCK`。

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
APP_IMAGE=registry.company.com/netora/network-dashboard-base:v2.5.2

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
# FNA — 所有廠牌共用（5 個 API），IP 在 path 中
FETCHER_ENDPOINT__GET_GBIC_DETAILS=/switch/network/get_gbic_details/{switch_ip}
FETCHER_ENDPOINT__GET_CHANNEL_GROUP=/switch/network/get_channel_group/{switch_ip}
FETCHER_ENDPOINT__GET_ERROR_COUNT=/switch/network/get_interface_error_count/{switch_ip}
FETCHER_ENDPOINT__GET_STATIC_ACL=/switch/network/get_static_acl/{switch_ip}
FETCHER_ENDPOINT__GET_DYNAMIC_ACL=/switch/network/get_dynamic_acl/{switch_ip}

# DNA — 每個 device_type 用 __HPE/__IOS/__NXOS 後綴 + ?hosts={switch_ip}
FETCHER_ENDPOINT__GET_MAC_TABLE__HPE=/api/v1/hpe/macaddress/display_macaddress?hosts={switch_ip}
FETCHER_ENDPOINT__GET_MAC_TABLE__IOS=/api/v1/ios/macaddress/show_mac_address_table?hosts={switch_ip}
FETCHER_ENDPOINT__GET_MAC_TABLE__NXOS=/api/v1/nxos/macaddress/show_mac_address_table?hosts={switch_ip}
FETCHER_ENDPOINT__GET_FAN__HPE=/api/v1/hpe/environment/display_fan?hosts={switch_ip}
FETCHER_ENDPOINT__GET_FAN__IOS=/api/v1/ios/environment/show_env_fan?hosts={switch_ip}
FETCHER_ENDPOINT__GET_FAN__NXOS=/api/v1/nxos/environment/show_environment_fan?hosts={switch_ip}
FETCHER_ENDPOINT__GET_POWER__HPE=/api/v1/hpe/environment/display_power?hosts={switch_ip}
FETCHER_ENDPOINT__GET_POWER__IOS=/api/v1/ios/environment/show_env_power?hosts={switch_ip}
FETCHER_ENDPOINT__GET_POWER__NXOS=/api/v1/nxos/environment/show_environment_power?hosts={switch_ip}
FETCHER_ENDPOINT__GET_VERSION__HPE=/api/v1/hpe/version/display_version?hosts={switch_ip}
FETCHER_ENDPOINT__GET_VERSION__IOS=/api/v1/ios/version/show_version?hosts={switch_ip}
FETCHER_ENDPOINT__GET_VERSION__NXOS=/api/v1/nxos/version/show_version?hosts={switch_ip}
FETCHER_ENDPOINT__GET_INTERFACE_STATUS__HPE=/api/v1/hpe/interface/display_interface_brief?hosts={switch_ip}
FETCHER_ENDPOINT__GET_INTERFACE_STATUS__IOS=/api/v1/ios/interface/show_interface_status?hosts={switch_ip}
FETCHER_ENDPOINT__GET_INTERFACE_STATUS__NXOS=/api/v1/nxos/interface/show_interface_status?hosts={switch_ip}
FETCHER_ENDPOINT__GET_UPLINK_LLDP__HPE=/api/v1/hpe/neighbor/display_lldp_neighbor-information_list?hosts={switch_ip}
FETCHER_ENDPOINT__GET_UPLINK_LLDP__IOS=/api/v1/ios/neighbor/show_lldp_neighbors?hosts={switch_ip}
FETCHER_ENDPOINT__GET_UPLINK_LLDP__NXOS=/api/v1/nxos/neighbor/show_lldp_neighbors?hosts={switch_ip}
FETCHER_ENDPOINT__GET_UPLINK_CDP__IOS=/api/v1/ios/neighbor/show_cdp_neighbors?hosts={switch_ip}
FETCHER_ENDPOINT__GET_UPLINK_CDP__NXOS=/api/v1/nxos/neighbor/show_cdp_neighbors?hosts={switch_ip}
```

啟動（不需要 `--profile mock`）：

```bash
docker compose -f docker-compose.production.yml up -d
```

> **注意**：S3 credentials（MINIO__ACCESS_KEY / SECRET_KEY）已預設為 `minioadmin`，不需要改。

#### 模式 C：SNMP Mock 模式（與模式 A 相同，已是預設）

> **v2.5.2 起**，`.env.mock` 預設就是 SNMP Mock 模式，模式 A 和模式 C 等價。
> 如果你用 `cp .env.mock .env` 啟動，就已經是 SNMP Mock 模式了。

手動確認 `.env` 中這兩行存在：

```ini
COLLECTION_MODE=snmp
SNMP_MOCK=true
```

啟動（需要 `--profile mock`，因為 ACL/Ping 仍然會 fallback 到 mock-api）：

```bash
docker compose -f docker-compose.production.yml --profile mock up -d
```

> **SNMP Mock** 會在 app 內部產生模擬的 SNMP OID 資料，不走 REST API。
> 適合在沒有真實交換機、也不需要測試 Parser 的情況下驗證 10 個 SNMP 指標的採集流程。
> 約 5% 的設備 × API 組合會隨機出現故障（每 60 秒變化一次），模擬真實環境。

#### 模式 D：SNMP 真實模式（直接 SNMP 採集真實交換機）

```bash
cp .env.production .env
```

在 `.env` 中設定：

```ini
COLLECTION_MODE=snmp
SNMP_MOCK=false

# SNMP 社群字串（逗號分隔，依序嘗試）
SNMP_COMMUNITIES=<你的community>,public
SNMP_PORT=161
SNMP_TIMEOUT=5
```

啟動（不需要 `--profile mock`）：

```bash
docker compose -f docker-compose.production.yml up -d
```

> **注意**：SNMP 真實模式會直接對設備清單中的所有交換機發送 SNMP 請求。
> 確保防火牆允許從 Docker 容器到交換機的 UDP 161 埠。

#### 模式切換

| 切換方向 | 操作 |
|----------|------|
| Mock → 真實 API | `cp .env.production .env`，填入真實 API，重啟不帶 `--profile mock` |
| 真實 API → Mock | `cp .env.mock .env`，重啟帶 `--profile mock` |
| Mock → SNMP Mock | 在 `.env` 底部加 `COLLECTION_MODE=snmp` + `SNMP_MOCK=true`，重啟 |
| 任意 → SNMP 真實 | 設定 `COLLECTION_MODE=snmp` + `SNMP_MOCK=false` + `SNMP_COMMUNITIES=...`，重啟 |

重啟指令：

```bash
docker compose -f docker-compose.production.yml --profile mock down
docker compose -f docker-compose.production.yml --profile mock up -d   # Mock / SNMP Mock
# 或
docker compose -f docker-compose.production.yml up -d                  # 真實 API / SNMP 真實
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
# FNA API：get_gbic_details, get_channel_group, get_error_count, get_static_acl, get_dynamic_acl
curl -v -H "Authorization: Bearer <FNA_TOKEN>" \
  "http://<FNA伺服器IP>:<port>/switch/network/get_gbic_details/10.1.1.1"

# 測試 DNA 連通（不需認證）
# DNA API：get_mac_table, get_fan, get_power, get_version, get_interface_status, get_uplink_lldp, get_uplink_cdp
curl -v "http://<DNA伺服器IP>:<port>/api/v1/hpe/environment/display_fan?hosts=10.1.1.1"

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

## Phase 1b：SNMP 模式驗證與除錯

> v2.5.2 新增 SNMP 採集模式。本章教你如何驗證 SNMP 功能是否正常，以及出問題時如何修正。

### 1b.1 SNMP vs API 模式差異

| | API 模式（預設） | SNMP 模式 |
|---|---|---|
| 資料來源 | FNA / DNA REST API | 直接 SNMP GET/WALK 交換機 |
| 需要的外部服務 | FNA + DNA 伺服器 | 交換機 UDP 161 可達 |
| 支援的指標 | 全部 12 個（含 ACL） | 10 個（ACL 自動 fallback 到 API） |
| Mock 模式 | mock-api 容器 | app 內建 MockSnmpEngine |
| 環境變數 | `COLLECTION_MODE=api` | `COLLECTION_MODE=snmp` |

### 1b.2 驗證 SNMP 模式是否啟用

```bash
# 確認設定值
docker exec netora_app python -c "
from app.core.config import settings
print('COLLECTION_MODE:', settings.collection_mode)
print('SNMP_MOCK:', settings.snmp_mock)
print('SNMP_COMMUNITIES:', settings.snmp_community_list)
"
```

預期輸出（Mock 模式）：

```
COLLECTION_MODE: snmp
SNMP_MOCK: True
SNMP_COMMUNITIES: ['tccd03ro', 'public']
```

### 1b.3 驗證 10 個 SNMP Collector 載入

```bash
docker exec netora_app python -c "
from app.snmp.collection_service import _build_collector_map
collectors = _build_collector_map()
for name, c in sorted(collectors.items()):
    print(f'  {name:25s} → {type(c).__name__}')
print(f'\nTotal: {len(collectors)} collectors')
"
```

預期輸出：

```
  get_channel_group         → ChannelGroupCollector
  get_error_count           → ErrorCountCollector
  get_fan                   → FanCollector
  get_gbic_details          → TransceiverCollector
  get_interface_status      → InterfaceStatusCollector
  get_mac_table             → MacTableCollector
  get_uplink_cdp            → NeighborCdpCollector
  get_uplink_lldp           → NeighborLldpCollector
  get_power                 → PowerCollector
  get_version               → VersionCollector

Total: 10 collectors
```

> 如果少於 10 個，檢查 `app/snmp/collectors/` 目錄下的檔案是否完整。

### 1b.4 驗證 Dashboard 指標資料

等待 5 分鐘讓排程跑一輪（每 300 秒），然後檢查 Dashboard：

```bash
# 先取得 JWT token
TOKEN=$(curl -s http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"root","password":"admin123"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['token'])")

# 取得歲修 ID
MAINT=$(curl -s http://localhost:8000/api/v1/maintenance \
  -H "Authorization: Bearer $TOKEN" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d[0]['id'] if d else 'NONE')")

echo "歲修 ID: $MAINT"

# 檢查各指標
for ind in fan power version transceiver error_count channel_group uplink; do
  result=$(curl -s "http://localhost:8000/api/v1/dashboard/maintenance/$MAINT/indicator/$ind/details" \
    -H "Authorization: Bearer $TOKEN")
  total=$(echo "$result" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('total_count','?'))" 2>/dev/null)
  pass=$(echo "$result" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('pass_count','?'))" 2>/dev/null)
  echo "  $ind: $pass/$total"
done
```

預期輸出（以 18 台設備為例）：

```
歲修 ID: 2026Q1
  fan: 17/18
  power: 18/18
  version: 18/18
  transceiver: 18/18
  error_count: 62/66
  channel_group: 18/18
  uplink: 10/10
```

> - 數字不需要完全一致，但不應該是 `0/0` 或 `?/?`
> - SNMP Mock 模式下約 5% 的設備會出現隨機故障，每分鐘變化一次
> - `uplink` 的 total 是期望數量（`uplink_expectations` 表），不是設備數

### 1b.5 查看 SNMP 採集日誌

```bash
# 需要 APP_DEBUG=true 才能看到 INFO 級別日誌
# 如果看不到 SNMP 日誌，在 .env 中確認 APP_DEBUG=true

docker logs netora_app -f --tail 200 2>&1 | grep -i "snmp\|collection"
```

正常 SNMP 採集日誌範例：

```
2026-02-28 04:20:00 - app.snmp.collection_service - INFO - SNMP get_fan for 2026Q1: 18/18 ok, 2.35s
2026-02-28 04:20:25 - app.snmp.collection_service - INFO - SNMP get_power for 2026Q1: 18/18 ok, 1.89s
```

> **重要**：如果 `.env` 中 `APP_DEBUG=false`（或未設定），日誌等級為 WARNING，
> INFO 級別的 SNMP 採集成功日誌不會顯示。只有 ERROR 和 WARNING 會出現。
> 建議在驗證階段設定 `APP_DEBUG=true`。

### 1b.6 SNMP 真實模式額外驗證

如果使用 SNMP 真實模式（`SNMP_MOCK=false`），額外做以下檢查：

#### 1. SNMP 連通性測試

```bash
docker exec netora_app python -c "
import asyncio
from app.snmp.engine import AsyncSnmpEngine, SnmpEngineConfig, SnmpTarget

async def test():
    engine = AsyncSnmpEngine(SnmpEngineConfig())
    target = SnmpTarget(ip='<交換機IP>', port=161, community='<community>')
    result = await engine.get(target, '1.3.6.1.2.1.1.1.0')
    for oid, val in result.items():
        print(f'{oid} = {val}')

asyncio.run(test())
"
```

如果成功，會顯示交換機的 sysDescr（含型號和版本資訊）。
如果失敗（timeout），檢查：
- 交換機 SNMP community 是否正確
- 防火牆是否允許 UDP 161
- 容器網路是否能到達交換機

#### 2. Community 自動偵測

```bash
docker exec netora_app python -c "
import asyncio
from app.snmp.engine import AsyncSnmpEngine, SnmpEngineConfig
from app.snmp.session_cache import SnmpSessionCache

async def test():
    engine = AsyncSnmpEngine(SnmpEngineConfig())
    cache = SnmpSessionCache(
        engine=engine,
        communities=['<community1>', '<community2>', 'public'],
        port=161, timeout=5, retries=1,
    )
    target = await cache.get_target('<交換機IP>')
    print(f'IP: {target.ip}')
    print(f'Community: {target.community}')

asyncio.run(test())
"
```

### 1b.7 SNMP 採集失敗的排查流程

| 症狀 | 可能原因 | 解決方式 |
|------|---------|---------|
| 全部指標 0/0 | 排程還沒跑完第一輪 | 等 5 分鐘再檢查 |
| 全部指標 0/0（等了很久） | 沒有活躍歲修 | 登入 Dashboard 建立歲修並匯入設備清單 |
| 全部指標 0/0 | `APP_DEBUG=false`，看不到錯誤 | 設 `APP_DEBUG=true` 重啟，看日誌 |
| SNMP timeout errors | 交換機不可達 | 檢查 SNMP 連通性（1b.6 步驟 1） |
| Community detection failed | Community 字串錯誤 | 確認 `SNMP_COMMUNITIES` 設定正確 |
| 某個指標一直 0 | Collector OID 可能與設備不相容 | 用 snmpwalk 驗證 OID（見下方） |
| ACL 指標失敗 | SNMP 不支援 ACL | 正常，ACL 自動 fallback 到 FNA API |
| uplink 指標 0/0 | `uplink_expectations` 表為空 | Dashboard 設定 uplink 期望 |

#### 用 snmpwalk 驗證 OID

如果某個 SNMP 指標數據不正確，可以用 snmpwalk 確認交換機實際回傳的 OID：

```bash
# snmpwalk / snmpget 已預裝在 image 中，直接使用
docker exec -it netora_app bash

# 將 <community> 替換為實際 community string，<IP> 替換為交換機 IP
```

**廠商識別（所有設備）：**
```bash
snmpget -v2c -c <community> <IP> 1.3.6.1.2.1.1.2.0        # sysObjectID
```

**韌體版本（所有設備）：**
```bash
snmpget -v2c -c <community> <IP> 1.3.6.1.2.1.1.1.0        # sysDescr
```

**風扇狀態：**
```bash
# HPE/H3C — HH3C-ENTITY-EXT-MIB
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.25506.2.6.1.1.1.1.19  # errorStatus
snmpwalk -v2c -c <community> <IP> 1.3.6.1.2.1.47.1.1.1.1.5          # entPhysicalClass (7=fan)
snmpwalk -v2c -c <community> <IP> 1.3.6.1.2.1.47.1.1.1.1.7          # entPhysicalName

# Cisco — CISCO-ENVMON-MIB
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.9.9.13.1.4.1.3        # ciscoEnvMonFanState
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.9.9.13.1.4.1.2        # ciscoEnvMonFanDescr
```

**電源狀態：**
```bash
# HPE/H3C — 與風扇共用 ENTITY-MIB，entPhysicalClass=6 為電源
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.25506.2.6.1.1.1.1.19  # errorStatus

# Cisco — CISCO-ENVMON-MIB
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.9.9.13.1.5.1.3        # ciscoEnvMonSupplyState
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.9.9.13.1.5.1.2        # ciscoEnvMonSupplyDescr
```

**光模組（Transceiver DOM）：**
```bash
# HPE/H3C — HH3C-TRANSCEIVER-INFO-MIB
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.25506.2.70.1.1.1.1.9  # txBiasCurrent (Tx)
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.25506.2.70.1.1.1.1.12 # rxPower (Rx)
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.25506.2.70.1.1.1.1.15 # temperature
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.25506.2.70.1.1.1.1.16 # voltage

# Cisco — CISCO-ENTITY-SENSOR-MIB
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.9.9.91.1.1.1.1.4     # entSensorValue
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.9.9.91.1.1.1.1.1     # entSensorType
```

**Interface 狀態（所有設備）：**
```bash
snmpwalk -v2c -c <community> <IP> 1.3.6.1.2.1.2.2.1.8               # ifOperStatus
snmpwalk -v2c -c <community> <IP> 1.3.6.1.2.1.31.1.1.1.15           # ifHighSpeed
snmpwalk -v2c -c <community> <IP> 1.3.6.1.2.1.10.7.2.1.19           # dot3StatsDuplexStatus
```

**Interface 錯誤計數（所有設備）：**
```bash
snmpwalk -v2c -c <community> <IP> 1.3.6.1.2.1.2.2.1.14              # ifInErrors
snmpwalk -v2c -c <community> <IP> 1.3.6.1.2.1.2.2.1.20              # ifOutErrors
```

**MAC Table：**
```bash
# HPE / Cisco NX-OS — Q-BRIDGE-MIB（標準）
snmpwalk -v2c -c <community> <IP> 1.3.6.1.2.1.17.7.1.2.2.1.2        # dot1qTpFdbPort

# Cisco IOS — per-VLAN community indexing
# 1. 先確認 VLAN 清單
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.9.9.46.1.3.1.1.2      # vtpVlanState
# 2. 用 community@vlanID 走 BRIDGE-MIB（例如 VLAN 100）
snmpwalk -v2c -c <community>@100 <IP> 1.3.6.1.2.1.17.4.3.1.2        # dot1dTpFdbPort
snmpwalk -v2c -c <community>@100 <IP> 1.3.6.1.2.1.17.1.4.1.2        # dot1dBasePortIfIndex
```

> **Cisco IOS 注意**：Q-BRIDGE-MIB 在 Cisco IOS 上通常回空結果。
> 系統已自動改用 per-VLAN community indexing（`community@vlanID`），
> 遍歷 VTP VLAN 清單，逐一走 BRIDGE-MIB::dot1dTpFdbPort。
> 如果上面 vtpVlanState 有結果，系統就會自動處理。

**Port-Channel / LAG（所有設備）：**
```bash
snmpwalk -v2c -c <community> <IP> 1.2.840.10006.300.43.1.2.1.1.13   # dot3adAggPortAttachedAggID
snmpwalk -v2c -c <community> <IP> 1.2.840.10006.300.43.1.2.1.1.21   # dot3adAggPortActorOperState
```

**LLDP 鄰居（所有設備）：**
```bash
snmpwalk -v2c -c <community> <IP> 1.0.8802.1.1.2.1.4.1.1.9          # lldpRemSysName
snmpwalk -v2c -c <community> <IP> 1.0.8802.1.1.2.1.4.1.1.7          # lldpRemPortId
snmpwalk -v2c -c <community> <IP> 1.0.8802.1.1.2.1.4.1.1.8          # lldpRemPortDesc
snmpwalk -v2c -c <community> <IP> 1.0.8802.1.1.2.1.3.7.1.4          # lldpLocPortDesc
```

**CDP 鄰居（僅 Cisco）：**
```bash
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.9.9.23.1.2.1.1.6     # cdpCacheDeviceId
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.9.9.23.1.2.1.1.7     # cdpCacheDevicePort
```

**ifName 對照（除錯用，確認 ifIndex → 介面名稱映射）：**
```bash
snmpwalk -v2c -c <community> <IP> 1.3.6.1.2.1.31.1.1.1.1            # ifName
```

#### 一鍵驗證腳本

上面的指令也可以用腳本一次跑完，自動產生報告檔：

```bash
# 進入 container
docker exec -it netora_app bash

# HPE 交換機
bash /app/scripts/snmp_verify.sh <community> <交換機IP> hpe

# Cisco 交換機
bash /app/scripts/snmp_verify.sh <community> <交換機IP> cisco
```

腳本會依序測試所有 10 個 collector 用到的 OID，結果存在 `/tmp/snmp_verify_<IP>_<時間>.txt`。

取出報告：
```bash
docker cp netora_app:/tmp/snmp_verify_<IP>_<時間>.txt .
```

> 如果 snmpwalk 的回傳格式與 collector 預期不同，
> 可能需要修改 `app/snmp/collectors/` 下對應的 collector。

### 1b.8 修改 SNMP Collector 後重建 Image

如果需要修改 SNMP collector 的 OID 解析邏輯：

#### 在公司外面（有網路環境）

```bash
cd netora

# 1. 修改 collector 程式碼
vi app/snmp/collectors/fan.py    # 或其他 collector

# 2. 跑測試確認
python -m pytest tests/unit/snmp/ -v

# 3. 重建 image
docker buildx build --platform linux/amd64 \
    -f docker/base/Dockerfile \
    -t coolguazi/network-dashboard-base:v2.5.2 \
    --load .

# 4. CVE 掃描（確認沒有 CRITICAL）
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
    aquasec/trivy image --severity CRITICAL \
    coolguazi/network-dashboard-base:v2.5.2

# 5. 推送
docker push coolguazi/network-dashboard-base:v2.5.2

# 6. 匯出（如果公司不能 pull）
docker save coolguazi/network-dashboard-base:v2.5.2 | gzip > netora-app-v2.5.2.tar.gz
```

#### 在公司環境（無外網）

如果已經在公司，可以用 production Dockerfile 疊加修改：

```bash
docker build \
    --build-arg BASE_IMAGE=registry.company.com/netora/network-dashboard-base:v2.5.2 \
    -f docker/production/Dockerfile \
    -t netora-production:v2.5.2-fix1 \
    .
```

> production Dockerfile 會自動 COPY `app/snmp/` 目錄到 image 中。

然後更新 `.env` 的 `APP_IMAGE` 並重啟：

```bash
# 更新 image
sed -i 's/APP_IMAGE=.*/APP_IMAGE=netora-production:v2.5.2-fix1/' .env

# 重啟
docker compose -f docker-compose.production.yml down
docker compose -f docker-compose.production.yml up -d
```

### 1b.9 SNMP Collector 對照表

| Collector | api_name | 對應 MIB | 備註 |
|-----------|----------|---------|------|
| FanCollector | get_fan | HH3C-ENTITY-EXT (HPE), CISCO-ENVMON (Cisco) | |
| PowerCollector | get_power | HH3C-ENTITY-EXT (HPE), CISCO-ENVMON (Cisco) | |
| VersionCollector | get_version | SNMPv2-MIB::sysDescr | 標準 MIB |
| TransceiverCollector | get_gbic_details | HH3C-TRANSCEIVER (HPE), CISCO-ENTITY-SENSOR (Cisco) | |
| ErrorCountCollector | get_error_count | IF-MIB::ifInErrors / ifOutErrors | 標準 MIB |
| ChannelGroupCollector | get_channel_group | IEEE8023-LAG-MIB | 標準 MIB |
| NeighborLldpCollector | get_uplink_lldp | LLDP-MIB | 標準 MIB |
| NeighborCdpCollector | get_uplink_cdp | CISCO-CDP-MIB | 僅 Cisco |
| MacTableCollector | get_mac_table | Q-BRIDGE-MIB (HPE/NXOS), VTP+BRIDGE-MIB per-VLAN (IOS) | IOS 自動 community@vlanID |
| InterfaceStatusCollector | get_interface_status | IF-MIB / EtherLike-MIB | 標準 MIB |

> ACL（static_acl, dynamic_acl）沒有 SNMP collector，自動 fallback 到 FNA REST API。

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
  get_gbic_details:     "/switch/network/get_gbic_details/{ip}"
  get_channel_group:    "/switch/network/get_channel_group/{ip}"
  get_error_count:      "/switch/network/get_interface_error_count/{ip}"
  get_static_acl:       "/switch/network/get_static_acl/{ip}"
  get_dynamic_acl:      "/switch/network/get_dynamic_acl/{ip}"

  # DNA（每個 device_type 各自的 endpoint）
  get_mac_table:
    hpe:  "/api/v1/hpe/macaddress/display_macaddress"
    ios:  "/api/v1/ios/macaddress/show_mac_address_table"
    nxos: "/api/v1/nxos/macaddress/show_mac_address_table"
  get_fan:
    hpe:  "/api/v1/hpe/environment/display_fan"
    ios:  "/api/v1/ios/environment/show_env_fan"
    nxos: "/api/v1/nxos/environment/show_environment_fan"
  get_power:
    hpe:  "/api/v1/hpe/environment/display_power"
    ios:  "/api/v1/ios/environment/show_env_power"
    nxos: "/api/v1/nxos/environment/show_environment_power"
  get_version:
    hpe:  "/api/v1/hpe/version/display_version"
    ios:  "/api/v1/ios/version/show_version"
    nxos: "/api/v1/nxos/version/show_version"
  get_interface_status:
    hpe:  "/api/v1/hpe/interface/display_interface_brief"
    ios:  "/api/v1/ios/interface/show_interface_status"
    nxos: "/api/v1/nxos/interface/show_interface_status"
  get_uplink_lldp:
    hpe:  "/api/v1/hpe/neighbor/display_lldp_neighbor-information_list"
    ios:  "/api/v1/ios/neighbor/show_lldp_neighbors"
    nxos: "/api/v1/nxos/neighbor/show_lldp_neighbors"
  get_uplink_cdp:                                 # HPE 沒有 CDP
    ios:  "/api/v1/ios/neighbor/show_cdp_neighbors"
    nxos: "/api/v1/nxos/neighbor/show_cdp_neighbors"

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
GET http://fna-server:8001/switch/network/get_gbic_details/10.1.1.1
GET http://dna-server:8001/api/v1/hpe/environment/display_fan?hosts=10.1.1.1
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
  ERROR  get_uplink_lldp_nxos_dna     ValueError  (get_uplink_nxos_10.3.3.3.txt)

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
  ERROR  get_uplink_lldp_nxos_dna     → test_data/debug/get_uplink_lldp_nxos_dna.md
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

#### 進階技巧：先問策略，再要程式碼

如果 AI 第一次產出的 parser 仍無法正確解析，嘗試分兩步驟互動：

**第一步 — 只問策略**（不要求寫程式）：

在 bundle 最後額外補充一段：

> 先不要寫程式碼。請分析 raw data 的結構，列出你的解析策略：
> 1. 資料有幾種格式？怎麼偵測？
> 2. 每種格式分別怎麼拆解？用什麼方法（split、regex、逐行判斷）？
> 3. 每個欄位怎麼提取？

**第二步 — 確認策略後再寫程式碼**：

確認策略合理後：

> 按照上述策略實作 parser。每個步驟對應一個獨立的 method。
> 每個 regex 只負責一件事，不要試圖用一個 regex 解決所有問題。

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

### 2.7b 常見陷阱

#### get_gbic_details：多通道光模組（QSFP/QSFP28/QSFP-DD）

多通道光模組（如 40G QSFP、100G QSFP28）有 4 條 lane，每條 lane 有獨立的 Tx/Rx 功率。

**常見問題**：AI 只解析 channel 1 的數據就回報 OK，漏掉 channel 2-4。

> `make parse-debug` 的 bundle 已自動包含多通道警告（在 `scripts/generate_debug.py` 的 `EXTRA_NOTES` 中），
> 正常流程下 AI 會自動看到。如果仍然只抓 channel 1，手動提醒 AI 注意 bundle 中的 ⚠️ CRITICAL 段落。

### 2.8 Parser 開發完成檢查清單

- [ ] 所有 36 個 parser 都顯示 `OK` 或 `CONVERGED`
- [ ] 至少用 3 台以上不同設備的 raw data 驗證過
- [ ] `make parse` 的 EMPTY 和 ERROR 數量 = 0
- [ ] 修改過的 parser 檔案都已存檔

---

## Phase 3：最終部署上線

> Parser 開發完成後，重建 image 並正式部署。

### 3.1 重建 Production Image

在公司機器上，用 `docker/production/Dockerfile` 把修改過的 parser、設定檔、Alembic migration 疊加到 base image：

```bash
cd netora

# BASE_IMAGE = 公司 registry 掃描通過後的 URL
docker build \
    --build-arg BASE_IMAGE=registry.company.com/netora/network-dashboard-base:v2.5.2 \
    -f docker/production/Dockerfile \
    -t netora-production:v2.5.2 \
    .
```

> **此 Dockerfile 不需外網**，只做 `COPY` 和本地指令，可以在公司環境執行。
> 它會疊加三樣東西到 base image 上：
> 1. `app/parsers/plugins/` — 修改過的 Parser
> 2. `config/` — 設定檔（scheduler.yaml 等）
> 3. `alembic/` — 資料庫 migration（確保新版 schema 變更被包含）
>
> **注意**：如果 production Dockerfile build 有問題，可以直接用 base Dockerfile 重建整個 image：
> ```bash
> docker buildx build --platform linux/amd64 \
>     -f docker/base/Dockerfile \
>     -t netora-production:v2.5.2 \
>     --load .
> ```

### 3.2 更新 docker-compose 使用新 image

編輯 `.env`：

```ini
APP_IMAGE=netora-production:v2.5.2
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

預期應有 36 個 parser 被載入。

---

## 附錄 A-0：SNMP 真實模式上線前需要盤的資料

> 在去公司之前，先確認以下資訊。這些是 SNMP 模式上線必需的。

| # | 資料項目 | 說明 | 取得方式 |
|---|---------|------|---------|
| 1 | **SNMP Community String** | 交換機的 readonly community（可能多個） | 問網管或查 ITSM |
| 2 | **交換機清單 CSV**（含 IP、hostname、vendor） | 設備管理匯入用 | 從 CMDB 或既有系統匯出 |
| 3 | **防火牆規則確認** | Docker 主機 → 交換機 UDP 161 是否放行 | 問 NOC 或自行 telnet 測試 |
| 4 | **各廠牌交換機各一台的 IP** | 用於驗證 SNMP OID 相容性（HPE、Cisco IOS、NX-OS 各一） | 挑選測試設備 |
| 5 | **FNA API Token**（如用 API 模式） | REST API Bearer token | 問 FNA 管理員 |
| 6 | **GNMS Ping 各 tenant group 的 base URL** | F18/F6/AP/F14/F12 各自的 ping server URL | 問 GNMS 管理員 |
| 7 | **Uplink 期望清單** | 哪些設備有 uplink、期望的鄰居設備名稱 | 人工整理或匯入 |
| 8 | **Client MAC 清單 CSV** | 如需追蹤 client 漫遊 | 從 DHCP/RADIUS 匯出 |

> **關鍵**：項目 1-4 是 SNMP 模式專屬需求。確認後可以在公司用 `scripts/snmp_verify.sh` 一鍵驗證 OID 相容性。

### 如果 SNMP 有問題，帶回來的資料（手抄 checklist）

> 公司不能傳檔案出來，以下每項只需手抄 1-3 行即可。

```
=== 必帶（每項一行）===

1. sysObjectID（每個廠牌各一台，共 2-3 行）：
   snmpget -v2c -c <community> <IP> 1.3.6.1.2.1.1.2.0
   → 手抄回傳值，例如: 1.3.6.1.4.1.25506.11.1.136

2. sysDescr（每個廠牌各一台，手抄前 100 字）：
   snmpget -v2c -c <community> <IP> 1.3.6.1.2.1.1.1.0
   → 手抄 "HPE Comware Software..." 到型號為止

3. docker logs 錯誤（手抄最後 3-5 行 ERROR）：
   docker logs netora_app 2>&1 | grep "ERROR\|Traceback" | tail -5

=== 選帶（某個指標資料不對時）===

4. 該指標的 snmpwalk 前 3 行（判斷 OID 格式用）：
   snmpwalk -v2c -c <community> <IP> <OID> | head -3
   → 手抄 3 行即可（含完整 OID = value 格式）

5. SNMP community 測試結果（一個字：成功 or timeout）：
   snmpget -v2c -c <community> <IP> 1.3.6.1.2.1.1.1.0

6. vendor 欄位值（從 Dashboard 設備清單看）：
   每台設備的 vendor 是 "HPE"、"Cisco-IOS"、還是 "Cisco-NXOS"？
   → 必須精確匹配，大小寫敏感

7. Cisco IOS MAC table 驗證（一行即可）：
   snmpwalk -v2c -c <community>@1 <Cisco-IOS-IP> 1.3.6.1.2.1.17.4.3.1.2 | head -1
   → 有回傳 = per-VLAN 正常; timeout/empty = 可能 community 或防火牆問題
```

> **重要**：`vendor` 欄位必須在 CSV 匯入時正確填寫（`HPE` / `Cisco-IOS` / `Cisco-NXOS`）。
> SNMP 模式完全依賴此欄位決定用哪組 OID 採集。如果是空值會默認為 HPE，
> 導致 Cisco 設備的 fan/power/transceiver 採集到空資料。

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
| SNMP 指標全部 0/0 | SNMP 模式未啟用 | 確認 `COLLECTION_MODE=snmp`，見 [Phase 1b](#phase-1bsnmp-模式驗證與除錯) |
| SNMP 某指標錯誤 | OID 與設備不相容 | 用 snmpwalk 驗證，見 [1b.7](#1b7-snmp-採集失敗的排查流程) |
| SNMP 日誌看不到 | APP_DEBUG=false | 設 `APP_DEBUG=true` 重啟 |

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
curl -v "http://<FNA_URL>/switch/network/get_gbic_details/10.1.1.1"

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

### 完整 Parser 清單（36 個）

| # | Parser 檔案 | command | device_type | 資料來源 | 輸出模型 |
|---|------------|---------|-------------|---------|---------|
| 1 | `get_gbic_details_hpe_fna_parser.py` | `get_gbic_details_hpe_fna` | HPE | FNA | TransceiverData |
| 2 | `get_gbic_details_ios_fna_parser.py` | `get_gbic_details_ios_fna` | CISCO_IOS | FNA | TransceiverData |
| 3 | `get_gbic_details_nxos_fna_parser.py` | `get_gbic_details_nxos_fna` | CISCO_NXOS | FNA | TransceiverData |
| 4 | `get_channel_group_hpe_fna_parser.py` | `get_channel_group_hpe_fna` | HPE | FNA | PortChannelData |
| 5 | `get_channel_group_ios_fna_parser.py` | `get_channel_group_ios_fna` | CISCO_IOS | FNA | PortChannelData |
| 6 | `get_channel_group_nxos_fna_parser.py` | `get_channel_group_nxos_fna` | CISCO_NXOS | FNA | PortChannelData |
| 7 | `get_uplink_lldp_hpe_dna_parser.py` | `get_uplink_lldp_hpe_dna` | HPE | DNA | NeighborData |
| 8 | `get_uplink_lldp_ios_dna_parser.py` | `get_uplink_lldp_ios_dna` | CISCO_IOS | DNA | NeighborData |
| 9 | `get_uplink_lldp_nxos_dna_parser.py` | `get_uplink_lldp_nxos_dna` | CISCO_NXOS | DNA | NeighborData |
| 10 | `get_uplink_cdp_ios_dna_parser.py` | `get_uplink_cdp_ios_dna` | CISCO_IOS | DNA | NeighborData |
| 11 | `get_uplink_cdp_nxos_dna_parser.py` | `get_uplink_cdp_nxos_dna` | CISCO_NXOS | DNA | NeighborData |
| 12 | `get_error_count_hpe_fna_parser.py` | `get_error_count_hpe_fna` | HPE | FNA | InterfaceErrorData |
| 13 | `get_error_count_ios_fna_parser.py` | `get_error_count_ios_fna` | CISCO_IOS | FNA | InterfaceErrorData |
| 14 | `get_error_count_nxos_fna_parser.py` | `get_error_count_nxos_fna` | CISCO_NXOS | FNA | InterfaceErrorData |
| 15 | `get_static_acl_hpe_fna_parser.py` | `get_static_acl_hpe_fna` | HPE | FNA | AclData |
| 16 | `get_static_acl_ios_fna_parser.py` | `get_static_acl_ios_fna` | CISCO_IOS | FNA | AclData |
| 17 | `get_static_acl_nxos_fna_parser.py` | `get_static_acl_nxos_fna` | CISCO_NXOS | FNA | AclData |
| 18 | `get_dynamic_acl_hpe_fna_parser.py` | `get_dynamic_acl_hpe_fna` | HPE | FNA | AclData |
| 19 | `get_dynamic_acl_ios_fna_parser.py` | `get_dynamic_acl_ios_fna` | CISCO_IOS | FNA | AclData |
| 20 | `get_dynamic_acl_nxos_fna_parser.py` | `get_dynamic_acl_nxos_fna` | CISCO_NXOS | FNA | AclData |
| 21 | `get_mac_table_hpe_dna_parser.py` | `get_mac_table_hpe_dna` | HPE | DNA | MacTableData |
| 22 | `get_mac_table_ios_dna_parser.py` | `get_mac_table_ios_dna` | CISCO_IOS | DNA | MacTableData |
| 23 | `get_mac_table_nxos_dna_parser.py` | `get_mac_table_nxos_dna` | CISCO_NXOS | DNA | MacTableData |
| 24 | `get_fan_hpe_dna_parser.py` | `get_fan_hpe_dna` | HPE | DNA | FanStatusData |
| 25 | `get_fan_ios_dna_parser.py` | `get_fan_ios_dna` | CISCO_IOS | DNA | FanStatusData |
| 26 | `get_fan_nxos_dna_parser.py` | `get_fan_nxos_dna` | CISCO_NXOS | DNA | FanStatusData |
| 27 | `get_power_hpe_dna_parser.py` | `get_power_hpe_dna` | HPE | DNA | PowerData |
| 28 | `get_power_ios_dna_parser.py` | `get_power_ios_dna` | CISCO_IOS | DNA | PowerData |
| 29 | `get_power_nxos_dna_parser.py` | `get_power_nxos_dna` | CISCO_NXOS | DNA | PowerData |
| 30 | `get_version_hpe_dna_parser.py` | `get_version_hpe_dna` | HPE | DNA | VersionData |
| 31 | `get_version_ios_dna_parser.py` | `get_version_ios_dna` | CISCO_IOS | DNA | VersionData |
| 32 | `get_version_nxos_dna_parser.py` | `get_version_nxos_dna` | CISCO_NXOS | DNA | VersionData |
| 33 | `get_interface_status_hpe_dna_parser.py` | `get_interface_status_hpe_dna` | HPE | DNA | InterfaceStatusData |
| 34 | `get_interface_status_ios_dna_parser.py` | `get_interface_status_ios_dna` | CISCO_IOS | DNA | InterfaceStatusData |
| 35 | `get_interface_status_nxos_dna_parser.py` | `get_interface_status_nxos_dna` | CISCO_NXOS | DNA | InterfaceStatusData |
| 36 | `ping_batch_parser.py` | `ping_batch` | 所有 | GNMSPING | PingResultData |

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
| `TransceiverData` | 光模組（⚠️ 多通道必須解析所有 channel，見 2.7b） | interface_name, channels | temperature, voltage |
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
| `PingResultData` | Ping | target, is_reachable | — |

> status 欄位（如 FanStatusData.status）會自動正規化：
> `"OK"` / `"Ok"` / `"ok"` → `"ok"` ;  `"Normal"` → `"normal"`
>
> MAC 位址自動正規化：
> `"AA-BB-CC-DD-EE-FF"` / `"AABB.CCDD.EEFF"` → `"AA:BB:CC:DD:EE:FF"`

---

## 快速指令卡（列印帶著用）

```
# ===== Phase 1: 起服務（SNMP Mock，推薦首次驗證）=====
unzip netora-main.zip && cd netora-main
docker pull <公司registry>/network-dashboard-base:v2.5.2
cp .env.mock .env
# 編輯 .env：APP_IMAGE=<公司registry>/network-dashboard-base:v2.5.2
docker compose -f docker-compose.production.yml --profile mock up -d
# alembic 自動執行，等 30 秒
curl http://localhost:8000/health
# 瀏覽器 http://localhost:8000 → root/admin123

# ===== Phase 1: 起服務（真實 API 模式）=====
cp .env.production .env
# 編輯 .env：密碼 + APP_IMAGE + API URL + Token + endpoint
docker compose -f docker-compose.production.yml up -d

# ===== Phase 1b: SNMP 真實模式 =====
# 在 .env 設定：
#   COLLECTION_MODE=snmp
#   SNMP_MOCK=false
#   SNMP_COMMUNITIES=<community1>,<community2>
docker exec netora_app python -c "from app.core.config import settings; \
    print('MODE:', settings.collection_mode, 'MOCK:', settings.snmp_mock)"
# 等 5 分鐘後用 API 檢查指標（見 SOP Phase 1b.4）

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
    --build-arg BASE_IMAGE=<公司registry>/network-dashboard-base:v2.5.2 \
    -f docker/production/Dockerfile \
    -t netora-production:v2.5.2 .
# 編輯 .env: APP_IMAGE=netora-production:v2.5.2
docker-compose -f docker-compose.production.yml down
docker-compose -f docker-compose.production.yml up -d
# alembic 自動執行
```
