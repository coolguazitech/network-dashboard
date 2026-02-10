# 公司操作手冊 - Parser 開發工具鏈

> **目標對象**: 在公司環境下進行 Parser 開發的工程師
> **前置條件**: 公司內網環境、可訪問內部 API、Docker 環境

---

## 📋 目錄

1. [環境準備](#環境準備)
2. [日常開發流程](#日常開發流程)
3. [詳細步驟說明](#詳細步驟說明)
4. [常見問題排查](#常見問題排查)
5. [實際範例](#實際範例)

---

## 環境準備

### 1. 獲取代碼

```bash
# 從 GitHub 獲取最新代碼
cd /path/to/workspace
git clone https://github.com/<your-org>/netora.git
cd netora

# 或更新現有代碼
git pull origin main
```

### 2. 配置環境變數

創建 `.env` 文件並設置 API Token：

```bash
# 複製範本
cp .env.example .env

# 編輯 .env 文件
vi .env
```

**需要設置的變數**：
```bash
# FNA API Token (從公司內部系統獲取)
FNA_TOKEN=your_fna_token_here

# DNA API (如果需要)
DNA_TOKEN=your_dna_token_here

# GNMS Ping API (如果需要)
GNMSPING_TOKEN=your_gnmsping_token_here
```

### 3. 準備執行環境

**選項 A：使用本地 Python (推薦，速度快)**

```bash
# 安裝開發依賴
pip install -r requirements-dev.txt

# 確認安裝成功
python -c "import httpx, yaml, rich; print('✅ 依賴安裝成功')"
```

**選項 B：使用 Docker 容器**

```bash
# 確認 Docker 運行中
docker-compose -f docker-compose.production.yml up -d

# 確認容器狀態
docker-compose ps
```

---

## 日常開發流程

### 完整流程圖

```
┌─────────────────────────────────────────┐
│ 1. 定義 API (config/api_test.yaml)     │
│    ↓                                    │
│ 2. 測試 API (make test-apis)           │
│    ↓                                    │
│ 3. 生成 Parser 骨架 (make gen-parsers) │
│    ↓                                    │
│ 4. 填寫 Parser 邏輯 (AI 輔助)          │
│    ↓                                    │
│ 5. 驗證 Parser (make test-parsers)     │
│    ↓                                    │
│ 6. 完成！                               │
└─────────────────────────────────────────┘
```

### 快速指令

**本地 Python 執行**：
```bash
make test-apis      # 測試所有 API
make gen-parsers    # 生成 Parser 骨架
make test-parsers   # 驗證 Parser
make all            # 一次執行全部步驟
```

**Docker 容器執行**：
```bash
make docker-test-apis      # 在容器內測試 API
make docker-gen-parsers    # 在容器內生成 Parser
make docker-test-parsers   # 在容器內驗證 Parser
make docker-all            # 在容器內執行全部步驟
```

---

## 詳細步驟說明

### 步驟 1: 定義 API

編輯 `config/api_test.yaml`，新增要測試的 API：

```bash
vi config/api_test.yaml
```

**範例：新增 HPE Fan API**

```yaml
# 在 test_targets 區塊新增測試目標
test_targets:
  - name: "SW-CORE-01"
    params:
      ip: "10.1.1.1"
      hostname: "SW-CORE-01"
      device_type: "hpe"

# 在 apis 區塊新增 API 定義
apis:
  - name: "get_fan_hpe"
    method: "GET"
    source: "DNA"
    endpoint: "/api/v1/hpe/fan"
    query_params:
      hosts: "{ip}"
    requires_auth: false
    description: "Fetch HPE fan status"
```

**重要欄位說明**：
- `name`: API 名稱（用於生成 Parser 檔名）
- `method`: HTTP 方法（GET/POST）
- `source`: API 來源（FNA/DNA/GNMSPING）
- `endpoint`: API 路徑（支援 `{ip}` 等變數）
- `query_params`: URL 參數（可選）
- `request_body_template`: POST 請求的 Body（可選）

---

### 步驟 2: 測試 API

執行批次測試，獲取所有 raw data：

```bash
# 本地執行
make test-apis

# 或在容器內執行
make docker-test-apis
```

**預期輸出**（即時顯示進度）：

```
🚀 API Batch Tester
📄 Config: config/api_test.yaml
📊 Found 5 APIs × 3 targets = 15 tests

Testing APIs...
  [████████████████████] 100% (15/15) | 3.2s
  ✅ get_fan_hpe @ SW-CORE-01 (189ms)
  ✅ get_fan_ios @ SW-DIST-01 (234ms)
  ❌ get_errors_hpe @ SW-AGG-01 (Timeout)
  ...

📝 Summary:
  ✅ Success: 14/15
  ❌ Failed: 1/15
  ⏱️  Duration: 3.45s

💾 Report saved to: reports/api_test_2026-02-09T14-30-00.json
```

**檢查測試報告**：

```bash
# 查看最新報告
ls -lht reports/api_test_*.json | head -1

# 查看報告內容
cat reports/api_test_2026-02-09T14-30-00.json | jq .

# 查看成功的 API 數量
cat reports/api_test_*.json | jq '.summary'
```

---

### 步驟 3: 生成 Parser 骨架

基於測試報告自動生成 Parser 檔案：

```bash
# 本地執行
make gen-parsers

# 或在容器內執行
make docker-gen-parsers
```

**預期輸出**：

```
📝 Parser Skeleton Generator
📄 Using report: reports/api_test_2026-02-09T14-30-00.json
📊 Found 14 successful API results

Generating parser skeletons...
  ✅ Created app/parsers/plugins/get_fan_hpe_parser.py
  ✅ Created app/parsers/plugins/get_fan_ios_parser.py
  ⏭️  Skipped get_fan_nxos_parser.py (already exists)
  ...

📝 Summary:
  ✅ Generated: 2 new parser(s)
  📁 Output directory: app/parsers/plugins/

🎉 Parser skeletons generated successfully!

Next steps:
  1. Open generated parser files
  2. Copy raw_data from report
  3. Ask AI to write parse() method
  4. Fill AI-generated code into skeleton
  5. Run 'make test-parsers' to validate
```

**生成的檔案位置**：
```
app/parsers/plugins/
├── get_fan_hpe_parser.py         (新生成)
├── get_fan_ios_parser.py         (新生成)
├── cisco_nxos_fan.py             (已存在，跳過)
└── ...
```

---

### 步驟 4: 填寫 Parser 邏輯（AI 輔助）

這是核心步驟，使用公司內部 AI 來協助生成 Parser 邏輯。

#### 4.1 獲取 raw_data

```bash
# 從測試報告中提取特定 API 的 raw_data
cat reports/api_test_2026-02-09T14-30-00.json | \
  jq '.results[] | select(.api_name == "get_fan_hpe" and .success == true) | .raw_data'
```

**範例輸出**：
```
"Fan 1/1        Ok            3200 RPM\nFan 1/2        Ok            3150 RPM\nFan 2/1        Failed        0 RPM\n"
```

#### 4.2 準備 AI Prompt

複製以下 Prompt 到公司內部 AI（如 ChatGPT、內部 LLM）：

```
我有一個 HPE 交換機 Fan 狀態的 API raw output，格式如下：

```
Fan 1/1        Ok            3200 RPM
Fan 1/2        Ok            3150 RPM
Fan 2/1        Failed        0 RPM
```

請幫我寫一個 Python parser，要符合以下要求：

1. 使用 Pydantic 的 FanData model（已定義，包含 fan_name, status, speed_rpm 欄位）
2. parse() 方法接收 raw_output: str，返回 list[FanData]
3. 使用正則表達式解析每一行
4. 處理異常情況（如空行、格式錯誤）
5. 只返回解析成功的結果

FanData 的定義如下：
```python
from pydantic import BaseModel

class FanData(BaseModel):
    fan_name: str
    status: str
    speed_rpm: int | None = None
```

請直接給我完整的 parse() 方法實作。
```

#### 4.3 填入 AI 生成的代碼

AI 會回傳類似以下的代碼：

```python
import re
from app.parsers.protocols import BaseParser, FanData
from app.core.enums import DeviceType
from app.parsers.registry import parser_registry

class GetFanHpeParser(BaseParser[FanData]):
    device_type = DeviceType.HPE
    indicator_type = "fan"
    command = "get_fan_hpe"

    def parse(self, raw_output: str) -> list[FanData]:
        results = []
        pattern = r"^Fan\s+(\S+)\s+(\S+)\s+(\d+)\s+RPM$"

        for line in raw_output.strip().splitlines():
            line = line.strip()
            if not line:
                continue

            match = re.match(pattern, line)
            if match:
                fan_name, status, speed = match.groups()
                results.append(FanData(
                    fan_name=f"Fan {fan_name}",
                    status=status,
                    speed_rpm=int(speed) if speed != "0" else None
                ))

        return results

parser_registry.register(GetFanHpeParser())
```

**將此代碼填入骨架檔案**：

```bash
# 打開生成的骨架檔案
vi app/parsers/plugins/get_fan_hpe_parser.py

# 將 AI 生成的代碼替換 TODO 區塊
# 確保保留以下部分：
# 1. import statements
# 2. class definition
# 3. device_type, indicator_type, command 欄位
# 4. parse() 方法
# 5. parser_registry.register() 註冊語句
```

---

### 步驟 5: 驗證 Parser

測試所有 Parser 是否正常工作：

```bash
# 本地執行
make test-parsers

# 或在容器內執行
make docker-test-parsers
```

**預期輸出**：

```
🧪 Parser Validator
📄 Using report: reports/api_test_2026-02-09T14-30-00.json
📦 Loaded 45 parser(s) from registry

Testing parsers...
📊 Found 14 API results to test

  ✅ GetFanHpeParser (indicator_type=fan): parsed 3 object(s)
  ✅ GetFanIosParser (indicator_type=fan): parsed 2 object(s)
  ❌ GetErrorsHpeParser (indicator_type=error_count): ValidationError: field 'interface_name' is required
  ...

┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ API Name          ┃ Parser                ┃ Status   ┃ Parsed Count┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ get_fan_hpe       │ GetFanHpeParser       │ ✅ passed│ 3           │
│ get_fan_ios       │ GetFanIosParser       │ ✅ passed│ 2           │
│ get_errors_hpe    │ GetErrorsHpeParser    │ ❌ failed│ -           │
└───────────────────┴───────────────────────┴──────────┴─────────────┘

📝 Summary:
  ✅ Passed: 12/14
  ❌ Failed: 2/14
  ⏭️  Skipped: 0/14

💾 Report saved to: reports/parser_test_2026-02-09T14-35-00.json
```

**如果有失敗的 Parser**：

```bash
# 查看詳細錯誤資訊
cat reports/parser_test_*.json | jq '.results[] | select(.status == "failed")'

# 範例輸出：
{
  "parser": "GetErrorsHpeParser (indicator_type=error_count)",
  "test_data_source": "api_name=get_errors_hpe, target=SW-CORE-01",
  "status": "failed",
  "parsed_count": 0,
  "error": "ValidationError: 1 validation error for InterfaceErrorData\ninterface_name\n  field required (type=value_error.missing)"
}

# 修正 Parser
vi app/parsers/plugins/get_errors_hpe_parser.py

# 重新測試
make test-parsers
```

---

### 步驟 6: 提交代碼

驗證通過後，提交新的 Parser：

```bash
# 查看修改的檔案
git status

# 添加新 Parser
git add app/parsers/plugins/get_fan_hpe_parser.py
git add app/parsers/plugins/get_fan_ios_parser.py

# 提交
git commit -m "feat: add HPE and IOS fan parsers

- Add GetFanHpeParser for HPE fan status
- Add GetFanIosParser for Cisco IOS fan status
- Tested with make test-parsers, all passed"

# 推送到 GitHub
git push origin main
```

---

## 常見問題排查

### Q1: `make test-apis` 失敗，顯示 `401 Unauthorized`

**原因**: Token 未設置或已過期

**解決方法**：
```bash
# 檢查 .env 文件
cat .env | grep TOKEN

# 確認 Token 有效性
curl -H "Authorization: Bearer $FNA_TOKEN" http://fna:8001/health

# 重新獲取 Token（從公司內部系統）
# 更新 .env 文件
```

---

### Q2: `make test-apis` 失敗，顯示 `TimeoutException`

**原因**: API 端點無法連接或響應過慢

**解決方法**：
```bash
# 檢查網路連接
ping fna
ping dna

# 檢查 API 服務狀態
curl http://fna:8001/health
curl http://dna:8001/health

# 檢查 config/api_test.yaml 的 endpoint 是否正確
vi config/api_test.yaml

# 調整 timeout（在 scripts/batch_test_apis.py 中）
# 將 timeout=10.0 改為 timeout=30.0
```

---

### Q3: `make gen-parsers` 沒有生成任何檔案

**原因**: 沒有成功的 API 測試結果

**解決方法**：
```bash
# 檢查最新測試報告
cat reports/api_test_*.json | jq '.summary'

# 確認至少有一個成功的 API 測試
# 如果全部失敗，先解決 API 連接問題

# 確認報告中有 raw_data
cat reports/api_test_*.json | jq '.results[] | select(.success == true) | .raw_data' | head
```

---

### Q4: `make test-parsers` 失敗，顯示 `No parser found for API 'xxx'`

**原因**: Parser 未註冊到 registry

**解決方法**：
```bash
# 檢查 Parser 檔案是否存在
ls -la app/parsers/plugins/*_parser.py

# 確認 Parser 檔案末尾有註冊語句
tail -5 app/parsers/plugins/get_fan_hpe_parser.py
# 應該包含：
# parser_registry.register(GetFanHpeParser())

# 確認 __init__.py 會自動發現 Parser
cat app/parsers/plugins/__init__.py

# 重啟 Python（如果在互動式環境）
```

---

### Q5: Parser 測試失敗，顯示 `ValidationError`

**原因**: 解析出的資料不符合 Pydantic model 定義

**解決方法**：
```bash
# 查看詳細錯誤訊息
cat reports/parser_test_*.json | jq '.results[] | select(.status == "failed")'

# 檢查 raw_data 格式
cat reports/api_test_*.json | jq '.results[] | select(.api_name == "get_fan_hpe") | .raw_data'

# 修正 Parser 的正則表達式或欄位映射
vi app/parsers/plugins/get_fan_hpe_parser.py

# 本地測試 Parser（不需要完整流程）
python -c "
from app.parsers.plugins.get_fan_hpe_parser import GetFanHpeParser
raw = 'Fan 1/1        Ok            3200 RPM'
parser = GetFanHpeParser()
print(parser.parse(raw))
"
```

---

### Q6: Docker 容器無法啟動

**原因**: 映像檔未拉取或 docker-compose 配置錯誤

**解決方法**：
```bash
# 檢查映像檔
docker images | grep netora

# 拉取最新映像檔（如果需要）
docker pull company.registry.com/netora:latest

# 檢查 docker-compose 配置
cat docker-compose.production.yml

# 重新啟動容器
docker-compose -f docker-compose.production.yml down
docker-compose -f docker-compose.production.yml up -d

# 查看容器日誌
docker-compose logs -f app
```

---

## 實際範例

### 範例 1: 新增 Cisco IOS Transceiver Parser

#### 1. 編輯 config/api_test.yaml

```yaml
test_targets:
  - name: "SW-IOS-01"
    params:
      ip: "10.2.1.1"
      hostname: "SW-IOS-01"
      device_type: "cisco_ios"

apis:
  - name: "get_transceiver_ios"
    method: "GET"
    source: "DNA"
    endpoint: "/api/v1/ios/transceiver"
    query_params:
      hosts: "{ip}"
    requires_auth: false
    description: "Fetch Cisco IOS transceiver Tx/Rx power"
```

#### 2. 測試 API

```bash
make test-apis
```

**輸出**：
```
  ✅ get_transceiver_ios @ SW-IOS-01 (345ms)
💾 Report saved to: reports/api_test_2026-02-09T15-00-00.json
```

#### 3. 查看 raw_data

```bash
cat reports/api_test_2026-02-09T15-00-00.json | \
  jq '.results[] | select(.api_name == "get_transceiver_ios") | .raw_data'
```

**輸出**：
```json
"Gi1/0/1               -2.5 dBm      -3.1 dBm\nGi1/0/2               -2.3 dBm      -3.0 dBm\n"
```

#### 4. 生成 Parser 骨架

```bash
make gen-parsers
```

**輸出**：
```
  ✅ Created app/parsers/plugins/get_transceiver_ios_parser.py
```

#### 5. 使用 AI 生成 Parser 邏輯

**給 AI 的 Prompt**：
```
我有一個 Cisco IOS 交換機 Transceiver 的 API raw output：

Gi1/0/1               -2.5 dBm      -3.1 dBm
Gi1/0/2               -2.3 dBm      -3.0 dBm

請寫一個 parser，使用 TransceiverData model：
- interface_name: str (如 "Gi1/0/1")
- tx_power_dbm: float | None
- rx_power_dbm: float | None

返回完整的 parse() 方法。
```

**AI 生成的代碼**：
```python
def parse(self, raw_output: str) -> list[TransceiverData]:
    results = []
    pattern = r"^(\S+)\s+([-\d.]+)\s+dBm\s+([-\d.]+)\s+dBm$"

    for line in raw_output.strip().splitlines():
        match = re.match(pattern, line.strip())
        if match:
            interface, tx, rx = match.groups()
            results.append(TransceiverData(
                interface_name=interface,
                tx_power_dbm=float(tx),
                rx_power_dbm=float(rx)
            ))

    return results
```

#### 6. 填入骨架並完成 Parser

```bash
vi app/parsers/plugins/get_transceiver_ios_parser.py
```

**完整代碼**：
```python
"""Parser for 'get_transceiver_ios' API."""
from __future__ import annotations

import re
from app.parsers.protocols import BaseParser, TransceiverData
from app.core.enums import DeviceType
from app.parsers.registry import parser_registry


class GetTransceiverIosParser(BaseParser[TransceiverData]):
    device_type = DeviceType.CISCO_IOS
    indicator_type = "transceiver"
    command = "get_transceiver_ios"

    def parse(self, raw_output: str) -> list[TransceiverData]:
        results = []
        pattern = r"^(\S+)\s+([-\d.]+)\s+dBm\s+([-\d.]+)\s+dBm$"

        for line in raw_output.strip().splitlines():
            match = re.match(pattern, line.strip())
            if match:
                interface, tx, rx = match.groups()
                results.append(TransceiverData(
                    interface_name=interface,
                    tx_power_dbm=float(tx),
                    rx_power_dbm=float(rx)
                ))

        return results


parser_registry.register(GetTransceiverIosParser())
```

#### 7. 驗證 Parser

```bash
make test-parsers
```

**輸出**：
```
  ✅ GetTransceiverIosParser (indicator_type=transceiver): parsed 2 object(s)

📝 Summary:
  ✅ Passed: 1/1
```

#### 8. 提交代碼

```bash
git add app/parsers/plugins/get_transceiver_ios_parser.py
git commit -m "feat: add Cisco IOS transceiver parser"
git push origin main
```

---

### 範例 2: 處理多端點 API（HPE Error Count 需要 2 個 API）

#### 1. 定義兩個獨立的 API

```yaml
apis:
  - name: "get_errors_hpe_input"
    method: "GET"
    source: "DNA"
    endpoint: "/api/v1/hpe/errors/input"
    query_params:
      hosts: "{ip}"
    requires_auth: false

  - name: "get_errors_hpe_output"
    method: "GET"
    source: "DNA"
    endpoint: "/api/v1/hpe/errors/output"
    query_params:
      hosts: "{ip}"
    requires_auth: false
```

#### 2. 測試並生成 2 個 Parser

```bash
make test-apis
make gen-parsers
```

**生成的檔案**：
- `app/parsers/plugins/get_errors_hpe_input_parser.py`
- `app/parsers/plugins/get_errors_hpe_output_parser.py`

#### 3. 分別填寫兩個 Parser 的邏輯

每個 Parser 處理自己的 raw_data 格式。

#### 4. 在 Indicator 層合併結果

```python
# app/indicators/error_count.py
class ErrorCountIndicator:
    async def evaluate(self, device: Device) -> IndicatorResult:
        # 查詢兩個 Parser 的結果
        input_errors = await repo.get_by_parser("get_errors_hpe_input")
        output_errors = await repo.get_by_parser("get_errors_hpe_output")

        # 合併計算總錯誤數
        total_errors = sum(e.error_count for e in input_errors + output_errors)

        # 評估是否通過
        passed = total_errors < threshold
        return IndicatorResult(passed=passed, details={...})
```

---

### 範例 3: 使用 POST 請求（GNMS Ping）

#### 1. 定義 POST API with request body

```yaml
test_targets:
  - name: "Ping-Batch-F18"
    params:
      tenant_group: "F18"
      ips: ["10.1.1.1", "10.1.1.2", "10.1.1.3"]

apis:
  - name: "ping_batch"
    method: "POST"
    source: "GNMSPING"
    tenant_group: "{tenant_group}"  # 用於選擇 base_url
    endpoint: "/api/ping"
    request_body_template: |
      {
        "tenant": "{tenant_group}",
        "ips": {ips},
        "timeout": 5
      }
    requires_auth: false
```

#### 2. 測試 API

```bash
make test-apis
```

**實際發送的請求**：
```http
POST https://gnmsping.dev.f18.com/api/ping
Content-Type: application/json

{
  "tenant": "F18",
  "ips": ["10.1.1.1", "10.1.1.2", "10.1.1.3"],
  "timeout": 5
}
```

#### 3. 後續流程與 GET 相同

生成 Parser → 填寫邏輯 → 驗證 → 提交。

---

## 清理與維護

### 清理測試報告

```bash
# 清理所有測試報告
make clean

# 或手動刪除
rm -f reports/api_test_*.json
rm -f reports/parser_test_*.json
```

### 查看所有已註冊的 Parser

```bash
python -c "
from app.parsers import plugins
from app.parsers.registry import parser_registry

print(f'Total parsers: {len(parser_registry)}')
for key, parser in parser_registry._parsers.items():
    print(f'  - {key}: {parser.__class__.__name__} (indicator_type={parser.indicator_type})')
"
```

### 定期同步代碼

```bash
# 拉取最新代碼
git pull origin main

# 檢查是否有新的依賴
pip install -r requirements-dev.txt

# 重啟服務（如果在運行）
docker-compose -f docker-compose.production.yml restart
```

---

## 附錄

### A. 快速參考卡

| 操作 | 本地指令 | Docker 指令 |
|------|----------|-------------|
| 測試 API | `make test-apis` | `make docker-test-apis` |
| 生成 Parser | `make gen-parsers` | `make docker-gen-parsers` |
| 驗證 Parser | `make test-parsers` | `make docker-test-parsers` |
| 全部執行 | `make all` | `make docker-all` |
| 清理報告 | `make clean` | `make clean` |
| 查看幫助 | `make help` | `make help` |

### B. 相關文件

- [README.md](../README.md) - 專案總覽
- [.env.example](../.env.example) - 環境變數範本
- [config/api_test.yaml](../config/api_test.yaml) - API 測試配置
- [app/parsers/protocols.py](../app/parsers/protocols.py) - ParsedData 類型定義

### C. 聯絡方式

如有問題，請聯絡：
- 技術負責人: [填入聯絡資訊]
- 內部 Slack: #netora-dev

---

**最後更新**: 2026-02-09
**版本**: v1.0
