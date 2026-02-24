# 完整數據流程範例

## 假設情境

你到公司後發現 Ping API 的格式是：
```
GET /api/v1/ping/{tenant_group}/{ip}
```

## 步驟 1️⃣：資料庫中的設備資料

```sql
-- MaintenanceDeviceList 表
┌────────────────┬──────────────────┬──────────────┬──────────────┐
│ new_hostname   │ new_ip_address   │ new_vendor   │ tenant_group │
├────────────────┼──────────────────┼──────────────┼──────────────┤
│ SW-FAB-001     │ 10.1.1.1         │ HPE          │ F18          │
│ SW-FAB-002     │ 10.1.1.2         │ Cisco-IOS    │ F18          │
│ SW-DC-001      │ 10.2.1.1         │ Cisco-NXOS   │ F9           │
└────────────────┴──────────────────┴──────────────┴──────────────┘
```

## 步驟 2️⃣：系統自動讀取並建立 FetchContext

**檔案位置**: [app/services/data_collection.py:279-288](app/services/data_collection.py#L279-L288)

```python
# 從資料庫查詢設備
stmt = select(MaintenanceDeviceList).where(...)
devices = result.scalars().all()

# 對每個設備建立 FetchContext（自動從資料庫讀取所有欄位）
for device in devices:
    device_type = DeviceType(device.new_vendor)  # "HPE" → DeviceType.HPE

    ctx = FetchContext(
        switch_ip=device.new_ip_address,      # "10.1.1.1"
        switch_hostname=device.new_hostname,  # "SW-FAB-001"
        device_type=device_type,              # DeviceType.HPE
        tenant_group=device.tenant_group,     # TenantGroup.F18
        is_old_device=False,
        params={},
        http=http,
        maintenance_id=maintenance_id,
    )

    # 呼叫 Fetcher
    result = await fetcher.fetch(ctx)
```

## 步驟 3️⃣：ConfiguredFetcher 自動準備所有佔位符

**檔案位置**: [app/fetchers/configured.py:81-92](app/fetchers/configured.py#L81-L92)

```python
# 對於 SW-FAB-001，all_vars 會是：
all_vars = {
    "switch_ip": "10.1.1.1",              # ← 從 ctx.switch_ip
    "ip": "10.1.1.1",                     # ← 別名
    "hostname": "SW-FAB-001",             # ← 從 ctx.switch_hostname
    "device_type": "hpe",                 # ← 從 ctx.device_type.api_value
    "tenant_group": "f18",                # ← 從 ctx.tenant_group.value
    # params 是空的，所以沒有額外變數
}
```

## 步驟 4️⃣：讀取 Endpoint 模板並替換佔位符

**檔案位置**: [app/fetchers/configured.py:95-100](app/fetchers/configured.py#L95-L100)

```python
# 從 .env 讀取 endpoint 模板
endpoint_template = "/api/v1/ping/{tenant_group}/{ip}"
# (來自 FETCHER_ENDPOINT__PING)

# 提取佔位符
placeholders = {"tenant_group", "ip"}
# (使用正則 \{(\w+)\} 提取)

# 替換佔位符
endpoint = endpoint_template.format(
    tenant_group="f18",  # all_vars["tenant_group"]
    ip="10.1.1.1"        # all_vars["ip"]
)
# 結果: "/api/v1/ping/f18/10.1.1.1"

# 組合完整 URL
url = "http://gnms-api:8001" + "/api/v1/ping/f18/10.1.1.1"
# 結果: "http://gnms-api:8001/api/v1/ping/f18/10.1.1.1"
```

## 步驟 5️⃣：Query Params 處理

**檔案位置**: [app/fetchers/configured.py](app/fetchers/configured.py)

```python
# Query params 規則：
# 模板含 '?' → 顯式模式：query params 已在 URL 中，不再附加
# 模板不含 '?' → 自動模式：未消耗的變數自動成為 query params

# 本範例的模板 "/api/v1/ping/{tenant_group}/{ip}" 不含 '?' → 自動模式
# 未被佔位符消耗的變數自動附加：
query_params = {
    "switch_ip": "10.1.1.1",   # 未使用（已經用 {ip} 代替）
    "hostname": "SW-FAB-001",  # 未使用
    "device_type": "hpe",      # 未使用
}

# 若改為 DNA 範例（模板含 '?'）：
# 模板: "/api/v1/hpe/environment/display_fan?hosts={switch_ip}"
# → query_params = {}（顯式模式，不自動附加）
```

## 步驟 6️⃣：發送最終 HTTP 請求

**檔案位置**: [app/fetchers/configured.py](app/fetchers/configured.py)

```python
# 自動模式範例（模板不含 '?'）
resp = await client.get(
    "http://gnms-api:8001/api/v1/ping/f18/10.1.1.1",
    params={"switch_ip": "10.1.1.1", "hostname": "SW-FAB-001", "device_type": "hpe"},
)
# → GET http://gnms-api:8001/api/v1/ping/f18/10.1.1.1?switch_ip=10.1.1.1&hostname=SW-FAB-001&device_type=hpe

# 顯式模式範例（DNA 模板含 '?hosts={switch_ip}'）
resp = await client.get(
    "http://dna:8001/api/v1/hpe/environment/display_fan?hosts=10.1.1.1",
    params={},
)
# → GET http://dna:8001/api/v1/hpe/environment/display_fan?hosts=10.1.1.1
```

## 步驟 7️⃣：API 返回數據 → Parser 解析

```python
# API 返回（假設是字串格式）
raw_output = """
PING 10.1.1.1 (10.1.1.1) 56(84) bytes of data.
5 packets transmitted, 5 received, 0% packet loss, time 4005ms
"""

# Parser 解析（你需要寫的部分）
parser = parser_registry.get(device_type=DeviceType.HPE, indicator_type="ping")
parsed_items = parser.parse(raw_output)
# → [PingData(target="self", is_reachable=True, success_rate=100.0, ...)]

# 存入資料庫
await typed_repo.save_batch(
    switch_hostname="SW-FAB-001",
    raw_data=raw_output,
    parsed_items=parsed_items,
    maintenance_id=maintenance_id,
)
```

---

## 🎯 關鍵設計優勢

### 1. 完全解耦
- ✅ **資料庫 schema** 決定有哪些欄位
- ✅ **FetchContext** 無腦接收所有欄位（Pydantic 強制驗證）
- ✅ **ConfiguredFetcher** 無腦提供所有佔位符
- ✅ **Endpoint 模板** 自由選用任意佔位符

### 2. 零代碼修改
當你到公司後發現 endpoint 格式不同：

```bash
# 只需要改 .env
FETCHER_ENDPOINT__PING=/api/v1/ping/{tenant_group}/{ip}

# 或者
FETCHER_ENDPOINT__PING=/api/v1/{device_type}/ping/{switch_ip}

# 或者
FETCHER_ENDPOINT__PING=/api/v1/ping/{hostname}?tenant={tenant_group}

# 都不需要改任何 Python 代碼！
```

### 3. Pydantic 保護
如果有人忘記傳 `tenant_group`：

```python
ctx = FetchContext(
    switch_ip="10.1.1.1",
    switch_hostname="SW-FAB-001",
    device_type=DeviceType.HPE,
    # 忘記傳 tenant_group
)
# ❌ ValidationError: field required
```

---

## 📝 你需要做的事

到公司後：

1. **測試 API 格式**
   ```bash
   curl "http://api-server/api/v1/ping/f18/10.1.1.1"
   ```

2. **修改 `.env`**
   ```bash
   FETCHER_ENDPOINT__PING=/api/v1/ping/{tenant_group}/{ip}
   ```

3. **寫 Parser** (app/parsers/plugins/ping_company.py)
   ```python
   class CompanyPingParser(BaseParser[PingData]):
       device_type = None  # 通用 parser
       indicator_type = "ping"

       def parse(self, raw_output: str) -> list[PingData]:
           # 解析公司 API 返回的字串格式
           ...
   ```

4. **完成！** ✅
