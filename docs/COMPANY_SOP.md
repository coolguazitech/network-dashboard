# 公司操作手冊 - Parser 開發工具鏈 v1.4.0

> **目標對象**: 在公司環境下進行 Parser 開發的工程師
> **前置條件**: 公司內網環境、可訪問內部 API（FNA / DNA / GNMSPING）
> **最後更新**: 2026-02-12
> **工具鏈版本**: v1.4.0（21 APIs、37 parsers、FNA/DNA/GNMSPING 三源架構）

---

## 目錄

1. [工具鏈驗證結果](#工具鏈驗證結果)
2. [到公司後的操作流程（SOP）](#到公司後的操作流程sop)
3. [日常開發流程](#日常開發流程)
4. [常見問題排查](#常見問題排查)
5. [快速參考](#快速參考)

---

## 工具鏈驗證結果

以下為 2026-02-12 使用 Mock Server 進行的完整驗證：

| 步驟 | 指令 | 結果 |
|------|------|------|
| API 批次測試 | `make test-apis` | 37/37 全部成功 |
| Parser 骨架生成 | `make gen-parsers` | 37 個骨架全部生成 |
| Parser 驗證 | `make test-parsers` | 37 個骨架載入成功（empty = 尚未填寫邏輯，正常） |
| 冪等性測試 | 再次執行 `make gen-parsers` | 全部 Skipped（已存在的檔案不會被覆蓋） |

### 當前 Parser 覆蓋情況

**21 個 API 定義 → 37 個 Parser 骨架**（FNA APIs 為 generic，每個 device_type 各一個 parser）

| 分類 | API 名稱 | 來源 | HPE | IOS | NXOS |
|------|---------|------|-----|-----|------|
| Transceiver | `get_gbic_details_fna` | FNA | `get_gbic_details_hpe_fna` | `get_gbic_details_ios_fna` | `get_gbic_details_nxos_fna` |
| Port-Channel | `get_channel_group_fna` | FNA | `get_channel_group_hpe_fna` | `get_channel_group_ios_fna` | `get_channel_group_nxos_fna` |
| Uplink | `get_uplink_fna` | FNA | `get_uplink_hpe_fna` | `get_uplink_ios_fna` | `get_uplink_nxos_fna` |
| Error Count | `get_error_count_fna` | FNA | `get_error_count_hpe_fna` | `get_error_count_ios_fna` | `get_error_count_nxos_fna` |
| ACL | `get_acl_fna` | FNA | `get_acl_hpe_fna` | `get_acl_ios_fna` | `get_acl_nxos_fna` |
| ARP Table | `get_arp_table_fna` | FNA | `get_arp_table_hpe_fna` | `get_arp_table_ios_fna` | `get_arp_table_nxos_fna` |
| Static VLAN | `get_static_vlan_fna` | FNA | `get_static_vlan_hpe_fna` | `get_static_vlan_ios_fna` | `get_static_vlan_nxos_fna` |
| Dynamic VLAN | `get_dynamic_vlan_fna` | FNA | `get_dynamic_vlan_hpe_fna` | `get_dynamic_vlan_ios_fna` | `get_dynamic_vlan_nxos_fna` |
| MAC Table | DNA | DNA | `get_mac_table_hpe_dna` | `get_mac_table_ios_dna` | `get_mac_table_nxos_dna` |
| Fan | DNA | DNA | `get_fan_hpe_dna` | `get_fan_ios_dna` | `get_fan_nxos_dna` |
| Power | DNA | DNA | `get_power_hpe_dna` | `get_power_ios_dna` | `get_power_nxos_dna` |
| Version | DNA | DNA | `get_version_hpe_dna` | `get_version_ios_dna` | `get_version_nxos_dna` |
| Ping | `ping_batch` | GNMSPING | 通用（1 個 parser） | - | - |

**狀態**: 所有 37 個 parser 為空骨架（`parse()` 返回 `[]`），需到公司拿到真實 raw data 後填寫邏輯。

---

## 到公司後的操作流程（SOP）

### 第零步：拉取最新代碼

```bash
cd /path/to/netora
git pull origin main
pip install -r requirements-dev.txt
```

---

### 第一步：配置真實環境

#### 1.1 設置環境變數

```bash
cp .env.example .env
vi .env
```

填入真實 Token：
```bash
FNA_TOKEN=<從公司內部系統獲取>
GNMSPING_APP_NAME=<GNMSPING app name>
GNMSPING_TOKEN=<GNMSPING token>
```

#### 1.2 修改 API 測試配置

編輯 `config/api_test.yaml`，替換以下內容：

**sources — 替換 base_url 為真實地址**：
```yaml
settings:
  sources:
    FNA:
      base_url: "http://<真實FNA地址>:<port>"
      token_env: "FNA_TOKEN"
    DNA:
      base_url: "http://<真實DNA地址>:<port>"
      token_env: null
    GNMSPING:
      base_urls:
        Dev: "http://<Dev環境地址>"
        F18: "http://<F18環境地址>"
        # ... 依需要填入其他 tenant
      app_name_env: "GNMSPING_APP_NAME"
      token_env: "GNMSPING_TOKEN"
```

**test_targets — 替換為真實交換機 IP**：
```yaml
test_targets:
  - name: "HPE-Switch-01"
    type: "switch"
    params:
      ip: "10.x.x.x"            # 真實 HPE 交換機 IP
      hostname: "HPE-Switch-01"
      device_type: "hpe"

  - name: "IOS-Switch-01"
    type: "switch"
    params:
      ip: "10.x.x.x"            # 真實 Cisco IOS 交換機 IP
      hostname: "IOS-Switch-01"
      device_type: "cisco_ios"

  - name: "NXOS-Switch-01"
    type: "switch"
    params:
      ip: "10.x.x.x"            # 真實 Cisco NXOS 交換機 IP
      hostname: "NXOS-Switch-01"
      device_type: "cisco_nxos"

  - name: "Ping-Batch-Dev"
    type: "gnmsping"
    params:
      tenant_group: "Dev"
      addresses: ["10.x.x.x", "10.x.x.x"]
      app_name: "<app_name>"
      token: "<token>"
```

**apis — 確認 endpoint 路徑**：
- 每個 API 定義的 `endpoint` 欄位有 `# TODO: 確認真實 endpoint` 標記
- 逐一確認並修正為公司實際的 API 路徑
- 如果某個 API 不存在，將該 API 定義暫時註解掉

---

### 第二步：批次測試所有 API

```bash
make test-apis
```

**觀察重點**：

```
✅ get_gbic_details_fna @ HPE-Switch-01 (189ms)   ← 成功
❌ get_acl_fna @ IOS-Switch-01 (Timeout)            ← 失敗，記錄原因
```

**查看測試報告**：
```bash
# 摘要
cat reports/api_test_*.json | python -m json.tool | grep -A5 '"summary"'

# 查看失敗的 API
cat reports/api_test_*.json | python -c "
import json, sys
data = json.load(sys.stdin)
for r in data['results']:
    if not r['success']:
        print(f\"  ❌ {r['api_name']} @ {r['target_name']}: {r['error']} - {r.get('error_detail','')[:80]}\")
"
```

**常見失敗原因與處理**：

| 錯誤 | 原因 | 處理 |
|------|------|------|
| `401 Unauthorized` | Token 錯誤或過期 | 更新 `.env` 中的 Token |
| `TimeoutException` | API 無法連接 | 確認 base_url 和內網連通性 |
| `404 Not Found` | endpoint 路徑錯誤 | 修正 `api_test.yaml` 中的 endpoint |
| `ConnectError` | DNS 或網路問題 | 確認 source 的 base_url 是否可 ping 通 |

**處理完所有失敗後，重新測試**：
```bash
make clean && make test-apis
```

目標：所有 API 都顯示 ✅（或確認不可用的 API 已暫時註解掉）。

---

### 第三步：重新生成 Parser 骨架（使用真實 raw data）

```bash
# 先刪除舊的骨架（含 Mock 資料的），以真實資料重新生成
rm app/parsers/plugins/*_parser.py

# 重新生成
make gen-parsers
```

**為什麼要重新生成？**

骨架檔案的 docstring 中自動包含：
1. **ParsedData 欄位定義** — 直接從 `protocols.py` 提取，含完整欄位名、型別、validator
2. **完整 raw data 範例** — 從 API 測試報告中提取的真實回應

用真實資料生成的骨架是**自包含的**，不需要再手動查閱其他檔案。

---

### 第四步：用 AI 填寫 Parser 邏輯

這是核心工作。**v1.4.0 的骨架已經是自包含的**，所有需要的資訊都在檔案裡：

#### 4.1 打開骨架檔案

```bash
vi app/parsers/plugins/get_fan_hpe_dna_parser.py
```

骨架 docstring 裡已經包含：
- **ParsedData 欄位定義**（含 field validator）
- **完整真實 raw data 範例**

#### 4.2 交給 AI

將整個骨架檔案交給 AI（ChatGPT / Claude / 公司內部 AI），只需說一句：

```
請幫我填寫 parse() 方法。所有需要的資訊（raw data 格式和目標資料模型）都在 docstring 裡。
```

不需要手動從 reports 提取 raw_data，不需要另外查閱 protocols.py。

#### 4.3 貼回骨架，存檔

AI 給你 parse() 方法後，直接替換 `# TODO: Implement parsing logic` 區塊即可。

#### 4.4 建議的填寫順序（優先級）

| 優先級 | Parser 類別 | 數量 | 說明 |
|--------|-----------|------|------|
| 高 | Fan (DNA) | 3 | 風扇狀態，簡單表格格式 |
| 高 | Power (DNA) | 3 | 電源狀態，與 Fan 類似 |
| 高 | Version (DNA) | 3 | 韌體版本，key-value 格式 |
| 高 | Error Count (FNA) | 3 | CRC 錯誤計數，直接影響巡檢判定 |
| 高 | Transceiver (FNA) | 3 | 光模組功率，核心指標（多通道 QSFP） |
| 中 | Ping (GNMSPING) | 1 | 可達性，JSON 格式易解析 |
| 中 | Port-Channel (FNA) | 3 | LAG 狀態 |
| 中 | Uplink (FNA) | 3 | 鄰居拓撲 |
| 中 | Static VLAN (FNA) | 3 | 介面 VLAN 對應 |
| 中 | Dynamic VLAN (FNA) | 3 | 動態 VLAN 對應 |
| 低 | MAC Table (DNA) | 3 | MAC 表，資料量大 |
| 低 | ACL (FNA) | 3 | ACL，輔助功能 |
| 低 | ARP Table (FNA) | 3 | ARP 表，輔助功能 |

---

### 第五步：驗證 Parser

```bash
make test-parsers
```

**狀態說明**：

| 狀態 | 意義 | 行動 |
|------|------|------|
| ✅ passed | parse() 正常回傳 > 0 筆資料 | 完成！ |
| ⚠️ empty | parse() 回傳空 list | 尚未填寫邏輯，繼續填寫 |
| ❌ failed | parse() 拋出例外 | 檢查錯誤訊息，修正 parser |
| ⏭️ skipped | 找不到對應的 parser | 檢查 command 名稱是否一致 |

**查看失敗詳情**：
```bash
cat reports/parser_test_*.json | python -c "
import json, sys
data = json.load(sys.stdin)
for r in data['results']:
    if r['status'] == 'failed':
        print(f\"  ❌ {r['parser']}: {r['error']}\")
"
```

**修正 → 重新測試 → 直到全部 passed**。

---

### 第六步：提交代碼並推送

```bash
# 查看修改的檔案
git status

# 添加所有 parser 和配置
git add app/parsers/plugins/*_parser.py
git add config/api_test.yaml

# 提交
git commit -m "feat: implement parser logic with real API data

- Fill parse() logic for all parser skeletons
- Update api_test.yaml with real endpoints and IPs
- Tested with make test-parsers, all passed"

# 推送
git push origin main
```

---

### 第七步（可選）：打包新版 Docker Image

如果需要部署到生產環境：

```bash
# 打包新版 image（含新 parser）
bash scripts/build-and-push.sh v1.4.0

# 在公司部署機器上更新
sed -i 's/v[0-9.]*$/v1.4.0/' docker-compose.production.yml
docker-compose -f docker-compose.production.yml pull
docker-compose -f docker-compose.production.yml up -d
```

---

## 日常開發流程

### 新增一個 API 的完整流程

```
1. 編輯 config/api_test.yaml  → 新增 API 定義
2. make test-apis              → 測試 API 拿到 raw_data
3. make gen-parsers            → 自動生成骨架（已存在的不覆蓋）
4. 打開骨架檔案交給 AI         → 骨架已自帶 ParsedData 定義 + raw data
5. make test-parsers           → 驗證 parser
6. git add + commit + push     → 提交到 repo
```

### 快速指令

```bash
# === 本地 Python ===
make test-apis      # 批次測試所有 API
make gen-parsers    # 生成 parser 骨架
make test-parsers   # 驗證 parser
make all            # 一次執行全部（test-apis → gen-parsers → test-parsers）
make clean          # 清理 reports/

# === Docker 容器內 ===
make docker-test-apis
make docker-gen-parsers
make docker-test-parsers
make docker-all
```

### 本地開發（在家，使用 Mock Server）

```bash
# 終端 1：啟動 Mock Server
python scripts/mock_api_server.py

# 終端 2：執行工具鏈
make all
```

Mock Server 模擬 21 個 API（8 FNA + 12 DNA + 1 GNMSPING），返回固定的測試資料。
流程與公司完全相同，只是 raw_data 是 mock 的。

---

## 常見問題排查

### Q1: `make test-apis` 顯示 401 Unauthorized

**原因**: Token 未設置或已過期。

```bash
# 檢查 .env
cat .env | grep TOKEN

# 測試 Token 是否有效
curl -H "Authorization: Bearer $FNA_TOKEN" http://<FNA_BASE_URL>/health
```

### Q2: `make gen-parsers` 沒有生成任何檔案

**可能原因**：
1. 沒有成功的 API 測試 → 先執行 `make test-apis` 並確保有成功項
2. 所有檔案已存在 → generator 自動跳過已存在的檔案

```bash
# 檢查測試報告
cat reports/api_test_*.json | python -c "
import json, sys
data = json.load(sys.stdin)
print(f\"Success: {data['summary']['success']}/{data['summary']['total_tests']}\")
"

# 如需重新生成，先刪除舊骨架
rm app/parsers/plugins/*_parser.py
make gen-parsers
```

### Q3: `make test-parsers` 顯示 failed

**常見錯誤**：

| 錯誤訊息 | 原因 | 修正 |
|---------|------|------|
| `ValidationError: field 'xxx' is required` | 必填欄位未給值 | 檢查 regex 是否正確擷取了所有必填欄位 |
| `parse() must return a list` | 回傳類型錯誤 | 確保 `return results`（list） |
| `ImportError` | import 路徑錯誤 | 檢查 `from app.parsers.protocols import ...` |

**快速除錯**：
```bash
# 單獨測試一個 parser
python -c "
from app.parsers.plugins.get_fan_hpe_dna_parser import GetFanHpeDnaParser
parser = GetFanHpeDnaParser()
raw = '''Fan 1/1        Ok            3200 RPM
Fan 1/2        Ok            3150 RPM'''
result = parser.parse(raw)
for item in result:
    print(item.model_dump())
"
```

### Q4: Parser 找到了但 parsed count = 0

**原因**: `parse()` 方法的正則表達式與真實 raw_data 格式不匹配。

```bash
# 查看真實 raw_data
cat reports/api_test_*.json | python -c "
import json, sys
data = json.load(sys.stdin)
for r in data['results']:
    if r['api_name'] == '<你的API名稱>' and r['success']:
        print(repr(r['raw_data']))  # 用 repr 看清楚換行和空白
"
```

將 raw_data 和正則表達式一起交給 AI 修正。

### Q5: Docker 容器內執行失敗

```bash
# 確認容器在運行
docker-compose -f docker-compose.production.yml ps

# 進入容器手動測試
docker-compose exec app bash
python scripts/batch_test_apis.py

# 確認容器內有最新代碼
docker-compose exec app git log --oneline -3
```

---

## 快速參考

### 一頁式 SOP 摘要

```
到公司後的操作（按順序執行）：

1. git pull origin main                          # 拉最新代碼
2. vi .env                                       # 填 Token
3. vi config/api_test.yaml                       # 填真實 IP 和 endpoint
4. make test-apis                                # 測試 API → 看哪些通了
5. rm app/parsers/plugins/*_parser.py            # 刪 mock 骨架
6. make gen-parsers                              # 用真實 raw_data 重新生成
7. 逐個 parser 檔案丟給 AI 寫 parse()             # 骨架已自包含所有資訊
8. make test-parsers                             # 驗證結果
9. git add + commit + push                       # 推上 repo
```

### ParsedData 型別速查

| Parser 用途 | ParsedData 類型 | 必填欄位 |
|------------|----------------|---------|
| Fan | `FanStatusData` | fan_id, status |
| Power | `PowerData` | ps_id, status |
| Version | `VersionData` | version |
| Error Count | `InterfaceErrorData` | interface_name, crc_errors |
| Transceiver | `TransceiverData` | interface_name, channels (含 TransceiverChannelData) |
| Port-Channel | `PortChannelData` | interface_name, status, members |
| Uplink | `NeighborData` | local_interface, remote_hostname, remote_interface |
| Static VLAN | `InterfaceVlanData` | interface_name, vlan_id |
| Dynamic VLAN | `InterfaceVlanData` | interface_name, vlan_id |
| Ping | `PingResultData` | ip_address, is_reachable |
| MAC Table | `MacTableData` | mac_address, interface_name, vlan_id |
| ACL | `AclData` | interface_name, acl_number |
| ARP Table | `ArpData` | ip_address, mac_address |

完整定義見 `app/parsers/protocols.py`。

### 相關文件

| 文件 | 說明 |
|------|------|
| `config/api_test.yaml` | API 測試配置（endpoint, target, source） |
| `app/parsers/protocols.py` | ParsedData 類型定義 + BaseParser 介面 |
| `app/parsers/registry.py` | Parser 註冊中心 + auto_discover |
| `app/parsers/plugins/` | Parser 實作檔案（自動發現） |
| `reports/api_test_*.json` | API 測試報告（含 raw_data） |
| `reports/parser_test_*.json` | Parser 驗證報告 |
| `docs/DEPLOYMENT_SOP.md` | Docker 部署 + Image 打包 SOP |
| `docs/LOCAL_TESTING.md` | 本地 Mock Server 測試指南 |
