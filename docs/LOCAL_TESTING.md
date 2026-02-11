# 本地測試指南 - Parser Development Toolchain

> **目的**: 在家裡測試工具鏈的完整流程，無需連接真實 API

---

## 🎯 測試目標

即使沒有真實的 API 訪問權限，你仍然可以：

- ✅ 驗證所有腳本是否正常運行
- ✅ 測試報告生成功能
- ✅ 測試 Parser 骨架生成
- ✅ 驗證完整的工作流程
- ✅ 熟悉所有指令和輸出格式

---

## 📋 前置準備

### 1. 確認依賴已安裝

```bash
# 檢查是否已安裝開發依賴
pip list | grep -E "(httpx|pyyaml|rich|jinja2)"

# 如果沒有，安裝依賴
pip install -r requirements-dev.txt
```

### 2. 確認當前目錄

```bash
cd /workspace
pwd  # 應該顯示 /workspace
```

---

## 🚀 完整測試流程

### 步驟 1: 啟動 Mock API Server

**在第一個終端視窗**：

```bash
# 啟動 mock server
python scripts/mock_api_server.py
```

**預期輸出**：
```
============================================================
🎭 Mock API Server Started
============================================================
📍 Address: http://localhost:8001

Available endpoints:
  GET  /api/v1/hpe/fan
  GET  /api/v1/hpe/errors/summary
  GET  /api/v1/hpe/transceiver
  GET  /api/v1/ios/fan
  GET  /api/v1/nxos/fan
  POST /api/ping

Press Ctrl+C to stop
============================================================
```

**不要關閉這個終端**，讓 server 保持運行。

---

### 步驟 2: 使用測試配置

**在第二個終端視窗**：

```bash
# 備份原有配置（如果存在）
[ -f config/api_test.yaml ] && mv config/api_test.yaml config/api_test.yaml.backup

# 使用本地測試配置
cp config/api_test.yaml.local config/api_test.yaml

# 確認配置已複製
cat config/api_test.yaml | grep "localhost:8001"
```

---

### 步驟 3: 測試 API 連接

```bash
# 執行 API 批次測試
make test-apis
```

**預期輸出**（即時顯示）：

```
🚀 API Batch Tester
📄 Config: config/api_test.yaml
📊 Found 6 APIs × 3 targets = 18 tests

Testing APIs...
  [████████████████████] 100% (18/18) | 1.2s
  ✅ get_fan_hpe @ Mock-HPE-Switch (15ms)
  ✅ get_errors_hpe @ Mock-HPE-Switch (12ms)
  ✅ get_transceiver_hpe @ Mock-HPE-Switch (10ms)
  ✅ get_fan_ios @ Mock-IOS-Switch (11ms)
  ✅ get_fan_nxos @ Mock-NXOS-Switch (13ms)
  ✅ ping_batch @ Mock-HPE-Switch (14ms)
  ...

📝 Summary:
  ✅ Success: 18/18
  ❌ Failed: 0/18
  ⏱️  Duration: 1.23s

💾 Report saved to: reports/api_test_2026-02-09T16-30-00.json
```

**驗證報告內容**：

```bash
# 查看報告摘要
cat reports/api_test_*.json | jq '.summary'

# 查看某個 API 的 raw_data
cat reports/api_test_*.json | jq '.results[] | select(.api_name == "get_fan_hpe") | .raw_data'
```

**預期看到的 raw_data**：
```json
"Fan Status:\nFan 1/1        Ok            3200 RPM\nFan 1/2        Ok            3150 RPM\nFan 2/1        Ok            3180 RPM\n"
```

---

### 步驟 4: 生成 Parser 骨架

```bash
# 生成 Parser 骨架
make gen-parsers
```

**預期輸出**：

```
📝 Parser Skeleton Generator
📄 Using report: reports/api_test_2026-02-09T16-30-00.json
📊 Found 18 successful API results

Generating parser skeletons...
  ✅ Created app/parsers/plugins/get_fan_hpe_parser.py
  ✅ Created app/parsers/plugins/get_errors_hpe_parser.py
  ✅ Created app/parsers/plugins/get_transceiver_hpe_parser.py
  ✅ Created app/parsers/plugins/get_fan_ios_parser.py
  ✅ Created app/parsers/plugins/get_fan_nxos_parser.py
  ⏭️  Skipped ping_batch_parser.py (already exists)

📝 Summary:
  ✅ Generated: 5 new parser(s)
  📁 Output directory: app/parsers/plugins/

🎉 Parser skeletons generated successfully!

Next steps:
  1. Open generated parser files
  2. Copy raw_data from report
  3. Ask AI to write parse() method
  4. Fill AI-generated code into skeleton
  5. Run 'make test-parsers' to validate
```

**檢查生成的檔案**：

```bash
# 查看生成的 Parser 列表
ls -lht app/parsers/plugins/*_parser.py | head -10

# 查看其中一個骨架檔案
head -50 app/parsers/plugins/get_fan_hpe_parser.py
```

**你會看到**：
- 完整的 class 定義
- Example raw output in docstring
- TODO 提示和常見 ParsedData 類型
- parse() 方法骨架

---

### 步驟 5: 填寫 Parser 邏輯（模擬）

為了測試完整流程，我們簡單填一個 Parser：

```bash
# 打開 get_fan_hpe_parser.py
vi app/parsers/plugins/get_fan_hpe_parser.py
```

**簡單範例**（你可以實際填寫或跳過）：

```python
from app.core.enums import DeviceType
from app.parsers.protocols import BaseParser, FanData
from app.parsers.registry import parser_registry

class GetFanHpeParser(BaseParser[FanData]):
    device_type = DeviceType.HPE
    indicator_type = "fan"
    command = "get_fan_hpe"

    def parse(self, raw_output: str) -> list[FanData]:
        import re
        results = []
        pattern = r"Fan\s+([\d/]+)\s+(\w+)\s+(\d+)\s+RPM"

        for line in raw_output.strip().splitlines():
            match = re.match(pattern, line)
            if match:
                fan_name, status, speed = match.groups()
                results.append(FanData(
                    fan_name=f"Fan {fan_name}",
                    status=status.lower(),
                    speed_rpm=int(speed)
                ))

        return results

parser_registry.register(GetFanHpeParser())
```

---

### 步驟 6: 驗證 Parser

```bash
# 驗證所有 Parser
make test-parsers
```

**預期輸出**：

```
🧪 Parser Validator
📄 Using report: reports/api_test_2026-02-09T16-30-00.json
📦 Loaded 28 parser(s) from registry

Testing parsers...
📊 Found 18 API results to test

  ✅ GetFanHpeParser (indicator_type=fan): parsed 3 object(s)
  ⏭️  get_errors_hpe: No parser found for API 'get_errors_hpe'
  ⏭️  get_transceiver_hpe: No parser found for API 'get_transceiver_hpe'
  ⏭️  get_fan_ios: No parser found for API 'get_fan_ios'
  ⏭️  get_fan_nxos: No parser found for API 'get_fan_nxos'
  ...

┏━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┳━━━━━━━━━━━━━┓
┃ API Name          ┃ Parser                ┃ Status   ┃ Parsed Count┃
┡━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ get_fan_hpe       │ GetFanHpeParser       │ ✅ passed│ 3           │
│ get_errors_hpe    │ N/A                   │ ⏭️ skipped│ -          │
│ get_transceiver..│ N/A                   │ ⏭️ skipped│ -          │
└───────────────────┴───────────────────────┴──────────┴─────────────┘

📝 Summary:
  ✅ Passed: 1/18
  ❌ Failed: 0/18
  ⏭️  Skipped: 17/18

💾 Report saved to: reports/parser_test_2026-02-09T16-35-00.json
```

**這是正常的**！Skipped 表示那些 Parser 骨架還沒填寫邏輯。

**查看驗證報告**：

```bash
# 查看成功的 Parser
cat reports/parser_test_*.json | jq '.results[] | select(.status == "passed")'
```

---

### 步驟 7: 一鍵執行全部流程

```bash
# 清理舊報告
make clean

# 一次執行全部步驟
make all
```

**預期輸出**：

```
🚀 Testing all APIs from config/api_test.yaml...
[... API testing output ...]
✅ Report saved to reports/api_test_*.json

📝 Generating parser skeletons...
[... Parser generation output ...]
✅ Parser skeletons generated in app/parsers/plugins/

🧪 Testing parsers with raw data...
[... Parser validation output ...]
✅ Validation report saved to reports/parser_test_*.json

🎉 All steps completed!
```

---

## 🎓 學習重點

通過這次本地測試，你應該：

### ✅ 熟悉了完整流程
1. 啟動 API server（在公司是真實的內網 API）
2. 配置 `config/api_test.yaml`
3. 執行 `make test-apis` → 生成報告
4. 執行 `make gen-parsers` → 生成骨架
5. 填寫 Parser 邏輯（使用 AI 輔助）
6. 執行 `make test-parsers` → 驗證

### ✅ 理解了工具輸出
- API 測試報告格式（JSON）
- Parser 骨架結構
- 驗證報告的 passed/failed/skipped 狀態

### ✅ 發現了潛在問題
- 哪些 Parser 需要特別關注
- raw_data 格式是否符合預期
- 正則表達式是否正確

---

## 🔍 驗證測試結果

### 檢查點 1: Mock Server 是否正常運作

```bash
# 在 Mock Server 運行時，測試單個端點
curl http://localhost:8001/api/v1/hpe/fan?hosts=10.1.1.1
```

**應該看到**：
```
Fan Status:
Fan 1/1        Ok            3200 RPM
Fan 1/2        Ok            3150 RPM
Fan 2/1        Ok            3180 RPM
```

### 檢查點 2: API 測試報告是否生成

```bash
ls -lht reports/api_test_*.json | head -1
```

### 檢查點 3: Parser 骨架是否生成

```bash
ls -lt app/parsers/plugins/*_parser.py | head -5
```

### 檢查點 4: Parser 驗證報告是否生成

```bash
ls -lht reports/parser_test_*.json | head -1
```

---

## 🧹 清理測試環境

測試完成後：

```bash
# 1. 停止 Mock Server（在第一個終端按 Ctrl+C）

# 2. 恢復原有配置（如果需要）
[ -f config/api_test.yaml.backup ] && mv config/api_test.yaml.backup config/api_test.yaml

# 3. 清理測試報告（可選）
make clean

# 4. 刪除測試生成的 Parser 骨架（可選）
rm -f app/parsers/plugins/get_*_parser.py
```

---

## 🎯 在公司的差異

在公司環境下，唯一的差異是：

| 項目 | 在家（Mock） | 在公司（真實） |
|------|-------------|---------------|
| **API Server** | `localhost:8001` | 內網真實 API（FNA/DNA/GNMSPING） |
| **配置文件** | `api_test.yaml.local` | `api_test.yaml`（真實 IP） |
| **Token** | 不需要 | 需要從 `.env` 讀取 |
| **raw_data** | Mock 資料 | 真實設備回應 |
| **流程** | 完全相同 ✅ | 完全相同 ✅ |

---

## 💡 常見問題

### Q1: Mock Server 啟動失敗，顯示 "Address already in use"

**解決**：
```bash
# 查找佔用 8001 port 的程式
lsof -i :8001

# 或換一個 port（需要同時修改 mock_api_server.py 和 api_test.yaml.local）
```

### Q2: make test-apis 顯示 "Connection refused"

**檢查**：
1. Mock Server 是否在運行
2. `config/api_test.yaml` 的 base_url 是否為 `http://localhost:8001`

### Q3: 生成的 Parser 骨架沒有包含 raw_data

**可能原因**：
- API 測試失敗（沒有 raw_data）
- 檢查 `reports/api_test_*.json` 確認 `success: true` 和 `raw_data` 欄位

---

## 📚 下一步

完成本地測試後，你已經熟悉了整個流程！

到公司時：
1. ✅ 直接使用真實配置（參考 [COMPANY_SOP.md](COMPANY_SOP.md)）
2. ✅ 執行相同的流程
3. ✅ 處理真實的 raw_data
4. ✅ 修正任何格式差異

**你已經準備好了！** 🚀

---

**最後更新**: 2026-02-09
**適用版本**: Parser Development Toolchain v1.1
