# Parser 驗證 SOP — 到公司要做的事

> **目標**: 用真實 API raw data 驗證所有 34 個 parser 是否正確解析

---

## Step 1: 填寫測試設定 (5 分鐘)

編輯 `config/api_test.yaml`：

### 1.1 填入 API 來源 URL

```yaml
sources:
  FNA:
    base_url: "http://真實FNA的IP:PORT"    # ← 改這裡
  DNA:
    base_url: "http://真實DNA的IP:PORT"    # ← 改這裡
  GNMSPING:
    base_url: "http://真實GNMSPING的IP:PORT"  # ← 改這裡
```

### 1.2 填入測試交換機

每種 device_type 至少填一台，挑**確定在線**的：

```yaml
targets:
  - ip: "10.x.x.x"           # ← HPE 交換機 IP
    hostname: "FAB-HPE-xxx"
    device_type: hpe

  - ip: "10.x.x.x"           # ← Cisco IOS 交換機 IP
    hostname: "FAB-IOS-xxx"
    device_type: ios

  - ip: "10.x.x.x"           # ← Cisco NX-OS 交換機 IP
    hostname: "FAB-NXOS-xxx"
    device_type: nxos
```

### 1.3 設定 FNA Token

```bash
# 方法 1: 直接設環境變數
export FNA_TOKEN="你的token"

# 方法 2: 寫在 .env 檔案
echo 'FNA_TOKEN=你的token' >> .env
```

---

## Step 2: Dry Run 確認 URL (2 分鐘)

```bash
make fetch-dry
```

檢查輸出的 URL 是否正確：
- FNA: `GET http://xxx/switch/network/get_gbic_details/10.x.x.x`
- DNA: `GET http://xxx/api/v1/hpe/fan?hosts=10.x.x.x`
- 如果 endpoint 路徑不對，修改 `config/api_test.yaml` 的 `endpoint` 欄位

---

## Step 3: 撈取 Raw Data (5 分鐘)

```bash
# 全部撈
make fetch

# 或只撈特定 API（debug 用）
API=get_fan make fetch
API=get_version make fetch
```

撈完後 raw data 存在 `test_data/raw/` 目錄：
```
test_data/raw/
├── get_fan_hpe_10.1.1.1.txt
├── get_fan_ios_10.1.1.2.txt
├── get_fan_nxos_10.1.1.3.txt
├── get_version_hpe_10.1.1.1.txt
├── ...
```

### 檢查重點

- 如果某個 API 回傳 HTTP 4xx/5xx → endpoint 路徑可能不對
- 如果回傳空白 → 該交換機可能沒有對應資料
- FNA 403 → Token 可能過期或不對

---

## Step 4: 跑 Parser 測試 (2 分鐘)

```bash
# 基本測試
make parse

# 看完整 JSON 輸出
make parse-verbose
```

### 判讀結果

```
=== SUMMARY ===
  Total:        34
  OK Parsed:    28    ← 有解析出資料
  Empty result: 4     ← 沒解析出任何東西（需要看 raw data）
  Errors:       2     ← Parser 報錯（需要修 regex）
```

| 狀態 | 代表什麼 | 下一步 |
|------|----------|--------|
| OK Parsed | Parser 正確解析 | 檢查 JSON 內容是否合理 |
| Empty result | Parser 沒匹配到任何行 | 打開 raw txt 看格式，調整 parser regex |
| Error | Parser 拋出異常 | 看 error message，修 parser |

---

## Step 5: 修正 Parser (視情況)

如果某個 parser 結果不對，流程：

```bash
# 1. 看 raw data 長什麼樣
cat test_data/raw/get_fan_hpe_10.1.1.1.txt

# 2. 改 parser
#    vim app/parsers/plugins/get_fan_hpe_dna_parser.py

# 3. 重新測試（不需要重新 fetch）
API=get_fan make parse
```

常見需要調整的地方：
- **regex pattern** — 真實 API 的格式跟 NTC-templates 略有不同
- **header 跳過邏輯** — FNA 可能在 raw output 前面加了額外的標題行
- **FNA 格式轉換** — FNA 可能已經對 CLI output 做了前處理

---

## Step 6: 保存結果

```bash
# 把 raw data commit 到 repo 當 test fixture
git add test_data/raw/
git add config/api_test.yaml
git commit -m "feat: add real API raw data for parser validation"

# 如果有修改 parser
git add app/parsers/plugins/
git commit -m "fix: adjust parser regex for real API output"
```

---

## 常用指令速查

| 指令 | 說明 |
|------|------|
| `make help` | 顯示所有可用指令 |
| `make fetch-dry` | 只印 URL 不實際呼叫 |
| `make fetch` | 撈取所有 API raw data |
| `API=get_fan make fetch` | 只撈特定 API |
| `TARGET=10.1.1.1 make fetch` | 只撈特定交換機 |
| `make parse` | Parse 所有已存的 raw data |
| `make parse-verbose` | Parse 並印完整 JSON |
| `API=get_fan make parse` | 只測特定 API |
| `make test-parsers` | fetch + parse 一次跑完 |
| `make clean-raw` | 清除所有 raw data |

---

## API 對應表

| API Name | Source | Parser Command | ParsedData |
|----------|--------|---------------|------------|
| get_gbic_details | FNA | `get_gbic_details_{dt}_fna` | TransceiverData |
| get_channel_group | FNA | `get_channel_group_{dt}_fna` | PortChannelData |
| get_uplink | FNA | `get_uplink_{dt}_fna` | NeighborData |
| get_error_count | FNA | `get_error_count_{dt}_fna` | InterfaceErrorData |
| get_static_acl | FNA | `get_static_acl_{dt}_fna` | AclData |
| get_dynamic_acl | FNA | `get_dynamic_acl_{dt}_fna` | AclData |
| get_arp_table | FNA | `get_arp_table_{dt}_fna` | ArpData |
| get_mac_table | DNA | `get_mac_table_{dt}_dna` | MacTableData |
| get_fan | DNA | `get_fan_{dt}_dna` | FanStatusData |
| get_power | DNA | `get_power_{dt}_dna` | PowerData |
| get_version | DNA | `get_version_{dt}_dna` | VersionData |
| ping_batch | GNMSPING | `ping_batch` | PingResultData |

`{dt}` = `hpe` / `ios` / `nxos`，共 7×3 + 4×3 + 1 = **34 個 parser**
