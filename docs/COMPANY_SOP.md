# NETORA 公司端 SOP

> **版本**: v2.21.4 (2026-04-13)
> **適用情境**: Image 已預先 build 好並推上 DockerHub → 公司掃描後取得 registry URL → 部署 → 接真實 API → Parser 開發
>
> **v2.21.4 變更摘要**:
> - **[功能] GNMS MacARP Client 自動匯入**：Client 清單新增「從 GNMS 匯入」精靈，透過 GNMS MacARP API 批次查詢設備的 Client MAC/IP，支援分批（每批 100 台）、設備篩選、分組標記備註/負責人、去重匯入。新增 `GNMS_MACARP__BASE_URL` / `GNMS_MACARP__TOKEN` 環境變數
> - **[功能] Tenant Group 擴充**：從 5 個（F18/F6/AP/F14/F12）擴充至 13 個，新增 Infra/Fab200mm/F15/F16/F20/F21/F22/F23，GNMS Ping base URL 同步更新
> - **[功能] Client/設備清單「清空全部」按鈕**：一鍵清空整份清單，附二次確認對話框
> - **[改善] Health endpoint 版本動態化**：`/health` 回傳的 `version` 從寫死改為讀取 `APP_VERSION` 環境變數
> - **[DB] Alembic migration `q2r3s4t5u6v7`**：擴充 `tenant_group` ENUM 欄位，含防禦性 table 存在檢查
> - **[Fix] NX-OS SNMP OID 修正**：Fan/Power 從 `CISCO-ENVMON-MIB`（IOS 專用）改為 `CISCO-ENTITY-FRU-CONTROL-MIB`（NX-OS 正確 MIB），修正 NX-OS 設備 Fan/Power 狀態無法正確採集的問題
> - **[改善] 前端版本號顯示**：右下角固定顯示當前版本號
> - **[安全] CVE 修復**：升級 pyasn1、wheel，移除系統層有 CVE 的舊套件
> - **[改善] 拓樸節點三色邏輯**：綠色=正常、橘色=驗收異常(ping 得到)、紅色=Ping 不可達，取代舊的藍色階層+紅色失敗
> - **[Critical Fix] Alembic migration `p1q2r3s4t5u6` 防禦性修復**：`packages` 欄位已存在時跳過 ADD COLUMN，修復 `create_all` DB 升級時 `Duplicate column name` 錯誤
> - **[改善] SNMP hard timeout 45s→90s**：Core 設備 MAC table 大，45s 不夠導致整台 timeout
> - **[功能] 案件「不處理」按鈕**：新案件可直接標記不處理，不需先接受再改狀態
> - **[改善] 拓樸節點顏色優化**：紅(Ping不可達)/黃(驗收異常)/綠(正常) 三色清晰區分，ping fail 加粗亮邊框
>
> **v2.20.2 變更摘要**:
> - **[Bugfix] FNA parser regex 修正**：FNA API 回傳 `show install active` 時所有 package 在同一行（空格分隔），舊 regex 用 `^`（行首錨點）導致只抓到第一個或零個 package。移除行首錨點，改為全文搜尋 `flash:/\S+` / `bootflash:/\S+`，正確抓取所有 package
>
> **v2.20.1 變更摘要**:
> - **[架構] get_version 改為 API passthrough**：SNMP 模式下 `get_version` 不再走 SNMP `sysDescr.0`，改為與 ACL/Ping 一樣走 REST API passthrough（FNA `show install active`），確保即使 `COLLECTION_MODE=snmp` 也能拿到完整的韌體 + 補丁列表
>
> **v2.20.0 變更摘要**:
> - **[架構] 版本採集改用 FNA `show install active`**：從 SNMP `sysDescr.0`（只看到單一版本字串）改為 FNA CLI `show install active`，可看到完整的韌體版本 + 補丁列表
> - **[架構] 版本資料模型重構**：`VersionData.version: str` → `VersionData.packages: list[str]`，DB 欄位從 `VARCHAR(255)` 改為 `JSON`，儲存完整安裝套件列表
> - **[功能] 版本驗收 substring 匹配**：期望值以分號分隔多個子字串（如 `R1238P06;R1238P06H01`），每個子字串只要是某個實際 package 的 substring 即算匹配，不再要求完全一字不漏比對
> - **[功能] 新增 FNA Parsers**：`get_version_hpe_fna`（`flash:` 開頭）、`get_version_ios_fna`（`bootflash:`）、`get_version_nxos_fna`（`bootflash:`），解析 `show install active` 輸出
> - **[設定] FNA 端點統一**：`FETCHER_ENDPOINT__GET_VERSION` 從 per-device-type DNA dict 改為單一 FNA 端點 `/switch/network/get_install_active/{switch_ip}`
> - **[DB] Alembic migration `p1q2r3s4t5u6`**：自動將舊 `version` 欄位資料轉為 JSON array，向下相容
> - **[改善] Transceiver -36.95 dBm 忽略邏輯**：光模塊有安裝但未對接（-36.95 dBm sentinel）的情況不再算失敗，該設備所有 interface 都是此狀態時自動通過
> - **[改善] Uplink 驗收不再要求鄰居在設備清單**：只要本機 LLDP/CDP 採集到鄰居 B 且 interface 吻合，B 不必被 SNMP 採集也算通過。新增 interface-level 精確匹配
> - **[改善] SNMP timeout 日誌增強**：WARNING 日誌加入 error reason、OID info、GET vs WALK 資訊
>
> **v2.19.15 變更摘要**:
> - **[Bugfix] 拓樸 per-port 物理約束去重**：一個 port 不可能同時接兩條線，topology API 加入 `used_ports` 集合確保每個 `(hostname, interface)` 只出現一次，消除 LLDP 雙向發現產生的重複 link
> - **[Bugfix] expected_fail link 同樣遵守 per-port 去重**：未匹配的期望 link 若其 port 已被 discovered link 佔用，不再額外產生虛線，避免同一 port 出現兩條線
> - **[改善] 拓樸 link 標籤混合狀態註記**：當同一對設備間同時存在「實際發現」和「期望未匹配」的 link 時，label 標註 `[實際]` / `[✗ 期望]` 區分
>
> **v2.19.14 變更摘要**:
> - **[Bugfix] Uplink 唯一約束修正**：migration `i4c5d6e7f8g9` 錯誤地將 `uk_uplink_expectation` 從 `(maintenance_id, hostname, local_interface)` 改為 `(maintenance_id, hostname, expected_neighbor)`，導致同一設備到同一鄰居的多條 uplink（如雙 uplink）CSV 匯入失敗。新增 migration `o0p1q2r3s4t5` 修正回 `local_interface`
> - **[Bugfix] 拓樸狀態 interface-level 精確比對**：原本拓樸 API 只比對 hostname pair 就標記 `expected_pass`，即使實際 interface 不匹配。修正為逐條比對 `(hostname, local_interface, expected_neighbor, expected_interface)`，不匹配的 interface 正確標記為 `discovered`，未匹配的期望正確標記為 `expected_fail`
>
> **v2.19.13 變更摘要**:
> - **[Bugfix] CSV 匯入範本欄位修正**：Contacts 範本第 2 列缺少 `department` 欄位導致後續欄位全部位移；Device Mapping 範本第 2 列多一個逗號導致 `new_hostname` 以後的欄位全部錯位
> - **[Bugfix] Scheduler 採集迴圈崩潰自動重啟**：`_collection_loop` 加入 `add_done_callback`，崩潰後 10 秒自動重啟，不再需要手動重啟容器
> - **[Bugfix] SNMP probe lock race condition**：`setdefault` 取代 check-then-set，防止兩個 coroutine 同時為同一 IP 建立不同的 Lock。`clear()` 時清理已釋放的 lock 防止無限增長
> - **[Bugfix] LatestClientRecord unique constraint**：新增 Alembic migration 修正 DB unique constraint 從 `(maintenance_id, mac_address)` 改為 `(maintenance_id, client_id)`，與 ORM model 定義一致
> - **[Bugfix] hostname_map 重複項**：`dict[str, list]` 改為 `dict[str, set]`，防止同一 IP 出現重複的 `(hostname, tenant_group)` 配對
> - **[防護] write_log 例外隔離**：Scheduler 中所有 `write_log` 呼叫包裹 try-except，DB log 寫入失敗不再中斷採集迴圈
> - **[清理] 移除 device_mappings 死代碼**：`client_comparison_service.py` 移除 5 處從未使用的 `MaintenanceDeviceList` DB 查詢，每次比較減少 1 次無用 query
> - **[功能] 案件 IGNORED 狀態**：新增 `CaseStatus.IGNORED`，允許將不需處理的案件標記為已忽略
>
> **v2.19.12 變更摘要**:
> - **[Bugfix] 拓樸 link label 移除 hostname 前綴**：ECharts `{c}` formatter 會自動附加 `[source]` / `[target]` 到 edge value，改用 closure function 直接回傳介面名稱，label 只顯示 `WGE1/0/51 ↔ TE1/0/1` 不再有 `[SW-ACCESS-01]` 前綴
> - **[改善] Link label 水平顯示**：加入 `rotate: 0` 讓 link 上的介面名稱保持水平方向，與 node 名稱方向一致，不再沿著連線旋轉
> - **[Bugfix] 拓樸 link 去重修復**：`remote_interface` 存入 DB 前未做 normalize（如 `Twenty-FiveGigE1/0/53` vs `WGE1/0/53`），導致同一條實體 link 從兩端各出現一次。加入 `remote_interface` normalize 後去重正確，每條 link 只顯示一次
> - **[改善] 前端介面名稱縮寫補全**：Topology.vue `shortIf()` 新增 `Twenty-FiveGigE`、`HundredGigE`、`FortyGigE`、`TwentyFiveGigE` 等中間形式的 regex 映射
>
> **v2.19.9 變更摘要**:
> - **[Bugfix] 介面名稱正規化統一**：所有期望值 API（uplink/port-channel 的 create/update/import-csv）在寫入 DB 前統一用 `normalize_interface_name()` 正規化。使用者可填寫全稱（`Port-Channel1`）、縮寫（`Po1`）或任意大小寫（`port-channel1`），系統自動轉為 canonical 短格式與 SNMP 採集資料一致，不再因格式不同導致驗收比對失敗
> - **[改善] Port-Channel 指標比對強化**：indicator 中的 `_normalize_name()` 改用系統級 `normalize_interface_name()`（70+ 種介面格式），member interface 比對也加入正規化，確保 `GigabitEthernet0/1` 與 `GE0/1` 能正確匹配
>
> **v2.19.8 變更摘要**:
> - **[Critical Fix] 改用 base Dockerfile 建構**：`docker/production/Dockerfile` 基於舊版 v2.5.3 base image，缺少 v2.15.0+ 新增的模組（`app.core.interfaces` 等），導致 `ModuleNotFoundError` 啟動失敗。改用 `docker/base/Dockerfile` 建構完整 image
> - **[Bugfix] 全部 15 個 Alembic 遷移加入防禦性檢查**：所有 migration 使用 `information_schema` 查詢確認 table/column/constraint 是否存在再操作，修復 `create_all()` 建表後 migration 重複執行的 `Duplicate column` / `Table doesn't exist` 錯誤
>
> **v2.19.7 變更摘要**:
> - **[Bugfix] Alembic arp_sources 遷移防禦**：`367a4017ffee`, `d7e0f1a2b3c4` 加入 table/column 存在性檢查
> - **[Bugfix] snmp_engine 向後相容**：使用 `getattr(settings, 'snmp_engine', 'subprocess')`
>
> **v2.19.6 變更摘要**:
> - **[效能] Collector 並行化**：每台設備的 8 個 collector 從串行改為 `asyncio.gather` 並行執行，每台設備時間從 ~80s 降到 ~12s（slowest collector），full_round 總時間從 ~10 min 降到 ~2 min
> - **[效能] Hard timeout 簡化**：並行後 hard timeout 不再隨 collector 數量增長，統一 `max(45, 15+15) = 45s`，所有 round 相同
>
> **v2.19.5 變更摘要**:
> - **[即時性] 兩階段採集**：已知可達設備（community cache 命中）優先採集（Phase 1, ~2s），不必等待不通設備探測超時（Phase 2, ~96s）。380 台不通 + 20 台可達的場景下，可達設備資料從 ~96s 延遲降到 ~2s
> - **[效能] NEGATIVE_TTL 180s→600s**：不通設備跳過 ~3 輪 fast_round 再重試，避免每輪浪費 ~96s 重新探測已知不通設備
>
> **v2.19.4 變更摘要**:
> - **[Root Fix] SubprocessSnmpEngine**：用 `asyncio.create_subprocess_exec("snmpget"/"snmpbulkwalk")` 取代 pysnmp，每個 SNMP 操作獨立進程，徹底消除 pysnmp `AbstractTransportDispatcher._cbFun` 崩潰和 event loop 卡死
> - **[Root Fix] 進程隔離**：50+ 台設備併發不再崩潰（每個 subprocess 獨立 PID/socket，OS 輕鬆處理），timeout 時 `proc.kill()` 立即乾淨回收
> - **[效能] Negative cache fast-path**：不可達設備在取 semaphore **之前**就跳過，不佔併發 slot，600s 後自動重試
> - **[效能] SNMP_CONCURRENCY 20→50**：subprocess 引擎安全支援高併發
> - **[設定] 新增 `SNMP_ENGINE` 環境變數**：`subprocess`（預設，推薦）或 `pysnmp`（legacy fallback）
>
> **v2.19.3 變更摘要**:
> - **[Critical] pysnmp engine 延遲清理**：timeout 後不再立即 closeDispatcher()，改為延遲 3 秒讓 uvloop pending callback 先 drain，修復 `AbstractTransportDispatcher._cbFun` 崩潰
> - **[Critical] 不再覆蓋成功資料**：SNMP 採集失敗時只記錄 error，不會用空 batch 覆蓋之前成功的資料（修復「驗收成功數字下降」問題）
> - **[效能] SNMP_CONCURRENCY 50→20**：50 個同時 pysnmp engine（各一個 UDP socket）超過系統承受上限，降到 20 穩定運行
> - **[效能] DEVICE_HARD_TIMEOUT 90s→60s**：搭配降低的 concurrency，更快釋放 semaphore slot
> - **[排程] full_round 1800s→600s**：原 30 分鐘太久，首次失敗要等半小時才重試 → 現 10 分鐘
> - **[排程] fast_round/ACL 120s→180s**：配合 concurrency=20，200 台設備需 ~150s 完成，留 30s buffer
>
> **v2.19.2 變更摘要**:
> - **[效能] GNMSPING timeout 60s→15s**：原 60s 導致 ping job 執行超過 15s 間隔 → 被 skip → 燈號不正確
> - **[效能] fast_round 間隔 300s→120s**：客戶端相關採集更頻繁，設備恢復後更快更新狀態
> - **[效能] Negative cache TTL 300s→180s（可設定）**：新增 `SNMP_NEGATIVE_TTL` 環境變數，不再與 fast_round 同步過期導致每輪重試不通設備
> - **[排程] ACL 採集間隔 300s→120s**：與 fast_round 同步，加快客戶端認證狀態更新
>
> **v2.19.1 變更摘要**:
> - **[效能] SNMP timeout 大幅降低**：snmp_timeout 8s→3s, retries 2→1, probe 3s→2s（per-PDU 從 26s 降到 8s，不通設備不再卡 semaphore slot）
> - **[效能] Per-device hard timeout**：每台設備整體 SNMP 階段上限 90s，超時直接 cancel 釋放 slot
> - **[效能] walk_timeout 120s→60s**：正常 walk 5-15s 完成，60s 已很寬裕
> - **[效能] ACL 併發降低 20→10**，加 httpx 連線池限制（防 FNA RemoteProtocolError）
>
> **v2.19.0 變更摘要**:
> - **[架構重構] Device-Centric Collection Rounds**：SNMP 採集從舊的 job-centric（12 個獨立 job 各自遍歷 400 台設備）重構為 device-centric（2 個輪次，每台設備只探測一次 community 後依序跑所有 collectors）
> - **fast_round (300s)**：client 相關 SNMP collectors（mac_table, interface_status），每台設備 community 探測 1 次 + walk 2 次
> - **full_round (1800s)**：指標類 SNMP collectors（fan, power, version, gbic, error_count, channel_group, lldp, cdp），每台設備 community 探測 1 次 + walk 8 次
> - **ACL legacy jobs (300s)**：get_static_acl, get_dynamic_acl 走 REST API passthrough，獨立排程不走 SNMP rounds
> - **移除 is_reachable 過濾**：不再依賴 ping 結果決定是否 SNMP 採集，消除首次啟動時 ping 未跑導致所有設備被跳過的 chicken-and-egg 問題
> - **Per-IP probe lock**：同一 IP 同時被多個 coroutine 請求時只探測一次，其餘等待結果，避免重複 SNMP probe
> - **DB 連線減少 10 倍**：從 10 jobs × 400 devices = 4000 次 session 降為 400 次（每台設備一次 session 寫入所有 collector 結果）
> - **不通設備一次判定整台跳過**：community probe 失敗後該設備所有 collector 立即標記 unreachable 並寫入 empty batch，UI 可見狀態
>
> **v2.19.0 變更摘要**:
> - **[Production Bug] Community 探測快速 timeout**：探測用 3s×1 retry（原 8s×3=26s），SNMP 不通的設備從 52s 降到 ~16s 就放棄
> - **Negative cache**：SNMP 不通的設備記錄 5 分鐘冷卻期，後續 job 直接跳過（0s），不再重複浪費 semaphore slot
> - **Community cache 跨 job 共享**：已知 community 的設備後續 job 不再重新探測
>
> **v2.18.3 變更摘要**:
> - **全域 SNMP Semaphore**：所有 SNMP job 共用一個 `Semaphore(SNMP_CONCURRENCY)`，防止 N 個 job 同時跑時併發量爆炸壓垮設備 SNMP agent
> - **分級排程 Interval**：Client 相關（mac_table, interface_status, ACL）300s，指標類（fan, power, version 等）1800s，避免所有 job 擠在同一時段
> - **Walk timeout 預設 120s**：大型 MAC/transceiver table 需要 60-90s，舊預設 30s 不夠
> - **Collector retry 預設 1 次**：搭配 walk_timeout=120s，最壞 ~241s/device（原 366s）
>
> **v2.18.2 變更摘要**:
> - **[Production Bug] SNMP Engine 隔離**：每次 `get()`/`walk()` 建立獨立 `PySnmpEngine`，消除共享 `transportDispatcher` 造成的跨操作污染與級聯 reset → OOMKill 問題
> - **Per-PDU hard timeout cap**：新增 `_MAX_PDU_WAIT=30s`，避免 `SNMP_TIMEOUT=30` 導致單次 PDU 等待高達 95 秒
>
> **v2.18.1 變更摘要**:
> - **SNMP bulkCmd hang 防護**：為每個 `bulkCmd`/`getCmd` PDU 加入 `asyncio.wait_for` hard timeout，防止單一 PDU 永久阻塞 event loop（修復 v2.16.0 移除 `wait_for` 後的 regression）
>
> **v2.18.0 變更摘要**:
> - **K8s API/Scheduler 分離架構**：新增 `ENABLE_SCHEDULER` 環境變數，同一 image 可分別部署為 API-only（水平擴展）或 Scheduler-only（固定 1 replica），附完整 K8s manifest 範例（附錄 E）
> - **DB 連線池可調**：新增 `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` 環境變數，API 和 Scheduler 可獨立調整連線池大小
> - **Device Ping 分批**：比照 Client Ping 加入 500/batch chunking，避免大量 IP 一次送出導致 GNMSPING timeout
> - **拓樸 Edge Label 方向修正**：使用 hash 排序 + dx 判斷，確保每個介面名稱靠近對應節點
> - **拓樸 Edge Label 格式改用 `{c}` formatter**：修復 ECharts graph edge label 不支援 function formatter 的問題
>
> **v2.15.3 變更摘要**:
> - **[Production Bug] Client Ping 修復**：修復 5000+ IP ping 結果導致 `Data too long for column 'raw_data'` 錯誤（TEXT 64KB → MEDIUMTEXT 16MB）
> - **Alembic Migration 自動適配**：Entrypoint 自動偵測 `create_all` 建的 DB（無 `alembic_version` 表），stamp 後執行 pending migrations，解決舊部署 migration 永遠不跑的問題
>
> **v2.15.2 變更摘要**:
> - **拓樸 Edge Label 修正**：修復選取節點後不相干連線顯示錯誤介面資訊（ECharts closure formatter 替換為靜態格式 + blur 狀態隱藏 edgeLabel）
>
> **v2.15.1 變更摘要**:
> - **DB Migration 補齊**：修正 UplinkExpectation unique constraint（`local_interface` → `expected_neighbor`）、raw_data TEXT → MEDIUMTEXT、新增效能索引（client_records, mac_list, cases）
> - **Migration 防禦性設計**：所有新 migration 加入 IF NOT EXISTS 檢查，相容 create_all 與 alembic 兩種建表方式
>
> **v2.15.0 變更摘要**:
> - **拓樸視覺化**：ECharts graph 拓樸圖（BFS 階層配置、Uplink 期望狀態、Pin-to-device 模式）
> - **SQL 查詢優化**：MAC stats / 設備 stats / 可達性使用 SQL 聚合（不載入全表），Error count 用 window function 批量查詢
> - **介面模組集中化**：新增 `app/core/interfaces.py`，統一所有介面名稱正規化與分類邏輯
> - **Client Ping 差異寫入**：in-place UPDATE 取代全量 batch 替換，降低 DB 寫入量
> - **Retention 清理**：新增 `cleanup_old_batches()` 清理活躍歲修中超齡的舊 batch
> - **DB 模型改進**：raw_data 改為 MEDIUMTEXT、新增索引（client_records, mac_list, cases）
> - **前端改進**：載入遮罩、並行資料載入、AbortController、案件時間線 4 態變化配色
> - **介面參考面板**：滑出式面板顯示系統支援的介面類型指引
>
> **v2.14.0 變更摘要**:
> - **Ping 效能優化**：`concurrent_tasks` 10→100、`count` 2→1、`timeout` 2s→1s、`chunk_size` 300→500，2000 IPs 預估從 ~50s 降至 ~8s
> - **Ping 間隔加速**：device_ping / client_ping 從 30s 縮至 15s，燈號更即時
> - **SNMP 採集加速**：`snmp_concurrency` 10→50（v2.19.4 subprocess 引擎安全支援 50+），400 台設備每 job 從 ~200s 降至 ~40s
> - **採集間隔縮短**：所有 SNMP/FNA 採集從 600s 降至 300s，client_collection 同步降至 300s
> - **測試覆蓋**：1374 tests 全部通過
>
> **v2.13.0 變更摘要**:
> - **Client MAC 匹配優先級修復**：設備清單包含 AGG/CORE 交換機時，同一 MAC 會出現在 edge access port 和 uplink port，舊邏輯只看資料完整度會選到錯誤的 uplink。新增五層逐步篩選規則：(1) 有 ACL → (2) 非 port-channel → (3) 無 LLDP/CDP 鄰居 → (4) Speed 最小 → (5) MAC 數量最少，全部平手則該次 client 屬性設為空
> - **LLDP/CDP 介面名稱正規化修復**：`local_interface` 欄位在 DB 寫入時未經過 `normalize_interface_name()`，導致鄰居比對永遠不匹配，修復 repository 層並在讀取時加上防禦性正規化
> - **測試覆蓋**：1374 tests 全部通過
>
> **v2.12.1 變更摘要**:
> - **Client 刪除孤兒資料修復**：刪除 Client 時同步清理 Case（含 CaseNote CASCADE）、SeverityOverride、ReferenceClient、LatestClientRecord，涵蓋單筆刪除、批量刪除、全部清空三個入口
> - **測試覆蓋**：1374 tests 全部通過
>
> **v2.12.0 變更摘要**:
> - **Client Ping 燈號即時化**：Client 清單 ping 燈號改為直接讀取 `ping_records`（~30 秒更新），不再依賴 `client_collection` 120 秒週期，與設備 ping 同步即時
> - **Client Ping 分批送出**：`_run_client_ping()` 新增 chunk_size=300 分批機制，避免大量 IP（3000+）一次送出導致 GNMS Ping API timeout
> - **排程間隔調整**：SNMP/FNA 採集從 300s 改為 600s、Client Collection 從 120s 改為 600s，降低 API/DB 負載
> - **測試覆蓋**：1374 tests 全部通過
>
> **v2.11.0 變更摘要**:
> - **案件摘要輸入覆蓋徹底修復**：新增本地編輯狀態追蹤（`editingSummaryId` / `editingSummaryValue`），focus 時捕獲本地值、input 時同步、blur 時才寫回，任何 Vue 重新渲染（loadStats 等）都不會覆蓋正在輸入的摘要
> - **訪客註冊表單必填標記**：選擇歲修、帳號、密碼、確認密碼四個欄位加上紅色 `*` 必填標記，與顯示名稱欄位一致
> - **測試覆蓋**：1374 tests 全部通過
>
> **v2.10.0 變更摘要**:
> - **期望值設備清單限制移除**：Uplink / Version / Port-Channel 三類期望值不再限制 hostname 必須存在於設備清單中（期望值與設備清單解耦，避免刪除設備後邏輯矛盾）
> - **Uplink 雙向鄰居查找**：評估時同時檢查正向（hostname 的鄰居含 expected_neighbor）和反向（expected_neighbor 的鄰居含 hostname），解決用戶填反本地/鄰居導致有資料卻判定失敗的問題
> - **LLDP Port ID MAC 地址處理**：當 `lldpLocPortId` / `lldpRemPortId` 為 hex 編碼的 MAC 地址（subtype=3）時，自動回退到 `lldpLocPortDesc` / `lldpRemPortDesc`，避免介面名稱顯示為 `0x54778a1ba584`
> - **Modal 拖曳關閉修復**：所有表單視窗的背景遮罩從 `@click.self` 改為 `@mousedown.self`，防止在輸入框內拖曳選取文字時視窗意外關閉
> - **案件摘要輸入中斷修復**：修復 15 秒自動刷新的 race condition — 將 activeElement 檢查從 API 請求前移至回應後，防止刷新覆蓋用戶正在輸入的摘要
> - **測試覆蓋**：1374 tests 全部通過
>
> **v2.9.0 變更摘要**:
> - **SNMP INT32_MAX 哨兵值處理**：HPE 設備回傳 `2147483647`（INT32_MAX）表示「不可用」，SNMP collector 偵測到此值自動轉為 None，避免異常數值寫入資料庫
> - **Pydantic 模型約束放寬**：移除 `TransceiverChannelData` 的 tx_power/rx_power 及 `TransceiverData` 的 temperature/voltage 數值範圍限制（ge/le），改由 collector 層處理異常值
> - **LLDP 介面優先順序修正**：local_interface / remote_interface 改為優先使用 `lldpLocPortId` / `lldpRemPortId`，PortDesc 僅作為 fallback（修復 port description 覆蓋 interface name 的問題）
> - **Ping JSON 格式支援**：修復 Scheduler 的 device_ping / client_ping 無法解析真實 GNMS Ping API 的 JSON 回應（`{"result": {"ip": {"is_alive": true}}}`），原本僅支援 CSV 導致所有 ping 結果判定為不可達
> - **Static ACL named ACL 支援**：HPE `packet-filter name <acl_name> inbound` 語法，原本錯誤擷取 `name` 關鍵字而非實際 ACL 名稱
> - **Dynamic ACL block 格式支援**：HPE `display mac-authentication connection` 的真實輸出為 key-value block 格式（`Access interface:` / `Authorization ACL number/name:`），新增 block parser 支援
> - **測試覆蓋**：1368 tests 全部通過
>
> **v2.8.0 變更摘要**:
> - **Error Count 詳細資訊修復**：失敗項目新增 `interface` 欄位，reason 顯示具體介面增量（如 `CRC 增長: GE1/0/2(+1); GE1/0/10(+2)`），超過 5 介面自動截斷
> - **Transceiver 改為設備層級評估**：分母從介面數改為設備數，無光模塊記錄的設備視為通過（修復 0/0 問題），失敗項目含逐介面異常細節
> - **屬性變化偵測 15 分鐘判定修正**：改用「轉換時間點」（None→值的實際發生時間）取代「最後採集時間」，修復 collector 持續採集導致永遠紅燈的 bug
> - **測試覆蓋**：1360 tests 全部通過
>
> **v2.7.0 變更摘要**:
> - **安全性修復**：Indicator 端點 (timeseries/rawdata/collect) 補上 `check_maintenance_access` 權限檢查，修復 Guest 可跨歲修存取的問題
> - **分頁效能修復**：Indicator raw data 從全載入 + Python 切片改為 SQL OFFSET/LIMIT，大幅減少記憶體使用
> - **屬性變化偵測邏輯修正**：設備離線 (→ None) 改為正常（綠色）；設備上線 (None →) 15 分鐘內為異常（紅色），超過 15 分鐘才算穩定（綠色）
> - **設備清單 UI 優化**：隱藏 Device Type 欄位，加大 Hostname 和備註欄空間
> - **測試覆蓋提升**：測試數從 ~800 增至 1356（新增 indicator 端點、parser plugin、協議模型、邊界條件測試）
>
> **v2.6.0 變更摘要**:
> - **HPE Transceiver OID 修正**：5 個 HH3C-TRANSCEIVER-INFO-MIB OID 移除多餘 `.1` 路徑段，新增 QSFP 多通道 (per-lane TX/RX) OID 支援
> - **HPE LLDP 本地介面修正**：新增 `lldpLocPortId` 走訪，修復 HPE 僅填充 LocPortId 而非 LocPortDesc 導致的本地介面名稱錯誤
> - **CRC Error 指標改為設備層級**：分母 = 設備數（非介面數），分子 = 任一介面有 CRC 增長的設備數，修復全零設備顯示 0/0 的問題
> - **GNMS Ping 請求體修正**：補齊 `count`、`interval`、`timeout`、`family`、`privileged` 等必要欄位，修復 400 Bad Request
>
> **v2.5.3 變更摘要**:
> - Docker image 重建、SNMP 除錯指南、OID 全量驗證
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

- [從舊版升級到 v2.21.0（必讀）](#從舊版升級到-v2210必讀)
- [Phase 1：公司端初始部署](#phase-1公司端初始部署)
- [Phase 1b：SNMP 模式驗證與除錯](#phase-1bsnmp-模式驗證與除錯)
- [Phase 2：Parser 開發（核心工作）](#phase-2parser-開發核心工作)
- [Phase 3：最終部署上線](#phase-3最終部署上線)
- [附錄 A：故障排查](#附錄-a故障排查)
- [附錄 B：Parser 對照表](#附錄-bparser-對照表)
- [附錄 C：ParsedData 模型欄位](#附錄-cparseddata-模型欄位)
- [附錄 D：SNMP 程式碼除錯指南（自己看懂 + 找問題）](#附錄-dsnmp-程式碼除錯指南自己看懂--找問題)
- [附錄 E：Kubernetes 部署指南（API / Scheduler 分離架構）](#附錄-ekubernetes-部署指南api--scheduler-分離架構)

---

## 從舊版升級到 v2.21.0（必讀）

> 如果公司環境已有舊版（v2.19.x ~ v2.20.x）在跑，照以下步驟升級。
> **全新部署**請直接跳到 [Phase 1](#phase-1公司端初始部署)。

### 升級步驟

#### Step 1：更新 Image

將新版 image 提交公司 registry 掃描：

| Image | 版本 |
|-------|------|
| `coolguazi/network-dashboard-base:v2.21.4` | 主應用 |
| `coolguazi/netora-mock-server:v2.21.4` | Mock API（僅 Mock 模式需要） |

掃描通過後更新 `.env`：

```ini
APP_IMAGE=registry.company.com/netora/network-dashboard-base:v2.20.2
MOCK_IMAGE=registry.company.com/netora/netora-mock-server:v2.21.4   # Mock 模式才需要
```

#### Step 2：修改 .env 中的版本端點（必做，否則啟動失敗）

**刪除**舊的 per-device-type 版本端點（如果有的話）：

```ini
# ❌ 刪除以下三行（v2.19.x 舊格式，會導致 Pydantic 驗證失敗）
FETCHER_ENDPOINT__GET_VERSION__HPE=/api/v1/hpe/version/display_version?hosts={switch_ip}
FETCHER_ENDPOINT__GET_VERSION__IOS=/api/v1/ios/version/show_version?hosts={switch_ip}
FETCHER_ENDPOINT__GET_VERSION__NXOS=/api/v1/nxos/version/show_version?hosts={switch_ip}
```

**新增**單一 FNA 端點：

```ini
# ✅ v2.20.0+ 新格式：單一 FNA 端點，所有廠牌共用
FETCHER_ENDPOINT__GET_VERSION=/switch/network/get_install_active/{switch_ip}
```

> **不改會怎樣？** 舊的三行 `__HPE/__IOS/__NXOS` 後綴會被 Pydantic 解析成 dict，
> 但新版 config 定義是 `str` → 啟動時報 `ValidationError: Input should be a valid string` → **App 無法啟動**。

#### Step 3：重啟服務

```bash
# 正常重啟（不需要刪 PVC / volume，alembic 會自動遷移）
docker compose -f docker-compose.production.yml down
docker compose -f docker-compose.production.yml up -d

# 或 K8s
kubectl rollout restart deployment/netora-app
```

#### Step 4：驗證

```bash
# 1. 確認啟動成功
curl http://localhost:8000/health

# 2. 確認 alembic 遷移完成（看 entrypoint 日誌）
docker logs netora_app 2>&1 | grep -i "alembic\|migration\|stamp"
# 應看到: "Running stamp_revision -> q2r3s4t5u6v7" 或 "Database is already at latest migration"

# 3. 確認 DB schema（packages 欄位應為 longtext/JSON）
docker exec netora_db mariadb -uadmin -padmin netora -e "DESCRIBE version_records;" | grep packages
# 應看到: packages    longtext    YES

# 4. 等一輪採集後確認版本資料正確
docker exec netora_db mariadb -uadmin -padmin netora -e "SELECT switch_hostname, packages FROM version_records LIMIT 3;"
# 應看到 JSON array 格式，如: ["flash:/5710-CMW710-BOOT-R1238P06.bin", ...]
```

### DB 遷移說明（不需手動操作）

| 舊 DB 狀態 | Alembic 自動處理 |
|-----------|----------------|
| v2.19.x（有 `version` VARCHAR 欄位） | Migration `p1q2r3s4t5u6` 自動轉 packages JSON + `q2r3s4t5u6v7` 擴充 tenant_group ENUM |
| v2.20.x（已有 `packages` JSON 欄位） | Migration `q2r3s4t5u6v7` 擴充 tenant_group ENUM |
| 全新 DB（空的） | `create_all` 建表 → stamp head，直接建出正確 schema |

> **PVC 不需要刪除**。Alembic 會自動偵測 DB 狀態並執行對應遷移。舊資料會被保留並轉換格式。

---

## Phase 1：公司端初始部署

> 到公司後的第一步：讓系統先跑起來。

### 1.1 取得 Image

將以下 image 提交公司 registry 掃描：

| Image | 用途 |
|-------|------|
| `coolguazi/network-dashboard-base:v2.21.4` | 主應用 |
| `coolguazi/netora-mariadb:10.11` | 資料庫 |
| `coolguazi/netora-mock-server:v2.21.4` | Mock API（僅 Mock 模式） |
| `coolguazi/netora-seaweedfs:4.13` | S3 物件儲存 |
| `coolguazi/netora-phpmyadmin:5.2` | DB 管理介面 |

掃描通過後會拿到公司內部的 image URL，例如：

```
registry.company.com/netora/network-dashboard-base:v2.19.0
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
APP_IMAGE=registry.company.com/netora/network-dashboard-base:v2.20.2
DB_IMAGE=registry.company.com/netora/netora-mariadb:10.11
MOCK_IMAGE=registry.company.com/netora/netora-mock-server:v2.21.4
```

拉取 image：

```bash
docker pull registry.company.com/netora/network-dashboard-base:v2.20.2
docker pull registry.company.com/netora/netora-mariadb:10.11
docker pull registry.company.com/netora/netora-mock-server:v2.21.4
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
APP_IMAGE=registry.company.com/netora/network-dashboard-base:v2.19.0

# ===== 真實 API 來源（必改）=====
# FNA: Bearer token 認證; DNA: 不需認證; 皆無 SSL
FETCHER_SOURCE__FNA__BASE_URL=http://<FNA伺服器IP>:<port>
FETCHER_SOURCE__FNA__TIMEOUT=30
FETCHER_SOURCE__FNA__TOKEN=<FNA Bearer token>
FETCHER_SOURCE__DNA__BASE_URL=http://<DNA伺服器IP>:<port>
FETCHER_SOURCE__DNA__TIMEOUT=30

# ===== GNMS Ping（必改，POST + JSON body，每個 tenant_group 各自的 base URL）=====
GNMSPING__TIMEOUT=15                           # 原 60s 導致 ping job 超時被 skip → 燈號錯誤
GNMSPING__ENDPOINT=/api/v1/ping
GNMSPING__TOKEN=<GNMSPING token（所有 tenant 共用）>
GNMSPING__BASE_URLS__Infra=http://public-gnmspingsvc.netsre.icsd.tsmc.com/
GNMSPING__BASE_URLS__Fab200mm=http://public-gnmspingsvc.netsre.edg.200mm.tsmc.com/
GNMSPING__BASE_URLS__AP=http://public-gnmspingsvc.netsre.edg.ap.tsmc.com/
GNMSPING__BASE_URLS__F6=http://public-gnmspingsvc.netsre.edg.f6.tsmc.com/
GNMSPING__BASE_URLS__F12=http://public-gnmspingsvc.netsre.edg.f12.tsmc.com/
GNMSPING__BASE_URLS__F14=http://public-gnmspingsvc.netsre.edg.f14.tsmc.com/
GNMSPING__BASE_URLS__F15=http://public-gnmspingsvc.netsre.edg.f15.tsmc.com/
GNMSPING__BASE_URLS__F16=http://public-gnmspingsvc.netsre.edg.f16.tsmc.com/
GNMSPING__BASE_URLS__F18=http://public-gnmspingsvc.netsre.edg.f18.tsmc.com/
GNMSPING__BASE_URLS__F20=http://public-gnmspingsvc.netsre.edg.f12.tsmc.com/
GNMSPING__BASE_URLS__F21=http://public-gnmspingsvc.netsre.edg.f21.tsmc.com/
GNMSPING__BASE_URLS__F22=http://public-gnmspingsvc.netsre.edg.f22.tsmc.com/
GNMSPING__BASE_URLS__F23=http://public-gnmspingsvc.netsre.edg.f23tsmc.com/

# ===== GNMS MacARP（v2.21.0 新增，Client 自動匯入用）=====
GNMS_MACARP__BASE_URL=http://netinv.netsre.icsd.tsmc.com
GNMS_MACARP__TOKEN=<GNMS MacARP Bearer token>
GNMS_MACARP__TIMEOUT=60
GNMS_MACARP__BATCH_SIZE=100

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
# v2.20.0: 版本採集改用 FNA (show install active)，不再需要 per-device-type DNA 端點
FETCHER_ENDPOINT__GET_VERSION=/switch/network/get_install_active/{switch_ip}
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

> **v2.5.3 起**，`.env.mock` 預設就是 SNMP Mock 模式，模式 A 和模式 C 等價。
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

# SNMP 效能參數（v2.19.4 建議值）
SNMP_ENGINE=subprocess        # subprocess（net-snmp CLI，推薦）或 pysnmp（legacy）
SNMP_TIMEOUT=3                # per-PDU timeout，3×(1+1)+2=8s
SNMP_RETRIES=1                # PDU retry，搭配 negative cache 快速跳過不通設備
SNMP_CONCURRENCY=50           # 全域 semaphore slot（subprocess 進程隔離，50+ 安全）
SNMP_WALK_TIMEOUT=30          # 單次 walk deadline（需 < hard_timeout 讓多 collector 有預算）
SNMP_COLLECTOR_RETRIES=1      # collector 層 retry
SNMP_MAX_REPETITIONS=25       # GETBULK max-repetitions
SNMP_NEGATIVE_TTL=600         # 不通設備冷卻期 600s（跳過 ~3 輪 fast_round 再重試）
```

> **v2.19.4 參數調校說明**（Root Fix: subprocess 引擎取代 pysnmp，徹底消除併發崩潰）：
>
> | 參數 | v2.19.3 值 | v2.19.4 建議值 | 改善效果 |
> |------|-----------|---------------|---------|
> | `SNMP_ENGINE` | _(無)_ | **subprocess** | net-snmp CLI 取代 pysnmp，進程隔離不再崩潰 |
> | `SNMP_CONCURRENCY` | 20 | **50** | subprocess 每個操作獨立 PID/socket，50+ 安全 |
> | `SNMP_WALK_TIMEOUT` | 60 | **30** | 需 < per-collector budget(15s×N)，避免一個慢 walk 吃掉所有預算 |
> | `DEVICE_HARD_TIMEOUT` | 60s (固定) | **動態** | `max(45, N×15+15)`: fast_round(2)=45s, full_round(8)=135s |
>
> **為什麼 subprocess 是根解**：pysnmp 在高併發下 `AsyncioDispatcher._cbFun` 回調衝突導致 event loop 停擺。
> subprocess 引擎每個 SNMP 操作用 `asyncio.create_subprocess_exec()` 啟動獨立進程，
> 完全進程隔離（獨立 PID/socket），timeout 時 `proc.kill()` 立即乾淨回收。
> OS 輕鬆處理 200+ 併發進程，不存在 callback 競爭問題。
>
> **不可達設備三層防護**：
> 1. Negative cache fast-path — 已知不通設備在取 semaphore **之前**跳過（0ms），不佔併發 slot
> 2. subprocess timeout → `proc.kill()` — 首次探測不通時立即乾淨回收，不汙染 event loop
> 3. Hard timeout 兜底 — `asyncio.wait_for()` 包住整個 SNMP phase，永不卡死 semaphore slot
>
> **為什麼 walk_timeout 從 60s 降到 30s**：hard_timeout = `max(45, N×15+15)`，
> full_round(8 collectors) = 135s。若 walk_timeout=60s，一個慢 walk 就吃掉近半預算。
> 30s 已很寬裕（正常 walk 5-15s），且確保多個 collector 有足夠預算。

#### `config/scheduler.yaml` 建議值（v2.19.4）

> `config/scheduler.yaml` 控制各採集器的排程間隔。Image 內已包含預設值，
> 部署時可用 volume mount 覆蓋（`./config/scheduler.yaml:/app/config/scheduler.yaml`）。

```yaml
fetchers:
  # Client 相關 — 180s (3min)，歸入 fast_round
  get_mac_table:        { source: DNA, interval: 180 }
  get_interface_status: { source: DNA, interval: 180 }
  get_static_acl:       { source: FNA, interval: 180 }
  get_dynamic_acl:      { source: FNA, interval: 180 }

  # 指標類 — 600s (10min)，歸入 full_round
  get_fan:              { source: DNA, interval: 600 }
  get_power:            { source: DNA, interval: 600 }
  get_version:          { source: FNA, interval: 600 }  # v2.20.0: 改用 FNA (show install active)
  get_gbic_details:     { source: FNA, interval: 600 }
  get_error_count:      { source: FNA, interval: 600 }
  get_channel_group:    { source: FNA, interval: 600 }
  get_uplink_lldp:      { source: DNA, interval: 600 }
  get_uplink_cdp:       { source: DNA, interval: 600 }

  # Ping — 15s（獨立排程）
  gnms_ping:            { source: GNMSPING, interval: 15 }
```

> | 排程 | 間隔 | 說明 |
> |------|------|------|
> | `fast_round` | 180s | 取 Client 相關 collectors 的最小 interval；200 台/concurrency(50)×15s ≈ 60s |
> | `full_round` | 600s | 取指標類 collectors 的最大 interval；200 台/concurrency(50)×45s ≈ 180s |
> | `device_ping` | 15s | 設備 ICMP Ping（獨立排程） |
> | `client_ping` | 15s | 客戶端 ICMP Ping（獨立排程） |
> | `client_collection` | 300s | 組裝 SNMP + Ping 結果成 Case |
> | `retention` | 30min | 清理過期資料 |

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

> v2.5.3 新增 SNMP 採集模式。本章教你如何驗證 SNMP 功能是否正常，以及出問題時如何修正。

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
# HPE/H3C — HH3C-TRANSCEIVER-INFO-MIB (hh3cTransceiverInfoEntry, indexed by ifIndex)
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.25506.2.70.1.1.1.9    # hh3cTransceiverCurTXPower (單通道 Tx)
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.25506.2.70.1.1.1.12   # hh3cTransceiverCurRXPower (單通道 Rx)
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.25506.2.70.1.1.1.15   # hh3cTransceiverTemperature
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.25506.2.70.1.1.1.16   # hh3cTransceiverVoltage
# HPE/H3C — hh3cTransceiverChannelEntry (QSFP 多通道, indexed by ifIndex.channel)
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.25506.2.70.1.2.1.2    # hh3cTransceiverChannelCurTXPower
snmpwalk -v2c -c <community> <IP> 1.3.6.1.4.1.25506.2.70.1.2.1.3    # hh3cTransceiverChannelCurRXPower

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
    -t coolguazi/network-dashboard-base:v2.19.12 \
    --load .

# 4. CVE 掃描（確認沒有 CRITICAL）
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
    aquasec/trivy image --severity CRITICAL \
    coolguazi/network-dashboard-base:v2.19.12

# 5. 推送
docker push coolguazi/network-dashboard-base:v2.19.12

# 6. 匯出（如果公司不能 pull）
docker save coolguazi/network-dashboard-base:v2.19.12 | gzip > netora-app-v2.9.0.tar.gz
```

#### 在公司環境（無外網）

如果已經在公司，可以用 production Dockerfile 疊加修改：

```bash
docker build \
    --build-arg BASE_IMAGE=registry.company.com/netora/network-dashboard-base:v2.19.0 \
    -f docker/production/Dockerfile \
    -t netora-production:v2.9.0-fix1 \
    .
```

> production Dockerfile 會自動 COPY `app/snmp/` 目錄到 image 中。

然後更新 `.env` 的 `APP_IMAGE` 並重啟：

```bash
# 更新 image
sed -i 's/APP_IMAGE=.*/APP_IMAGE=netora-production:v2.9.0-fix1/' .env

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
  get_version: "/switch/network/get_install_active/{switch_ip}"  # v2.20.0: FNA 統一端點
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
    --build-arg BASE_IMAGE=registry.company.com/netora/network-dashboard-base:v2.19.0 \
    -f docker/production/Dockerfile \
    -t netora-production:v2.9.0 \
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
>     -t netora-production:v2.9.0 \
>     --load .
> ```

### 3.2 更新 docker-compose 使用新 image

編輯 `.env`：

```ini
APP_IMAGE=netora-production:v2.9.0
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
| App 啟動報 `ValidationError: Input should be a valid string`，日誌顯示 `fetcher_endpoint.get_version` 收到 dict `{'nxos': '...'}` | `.env` 仍有舊版 per-device-type 端點 `FETCHER_ENDPOINT__GET_VERSION__HPE/IOS/NXOS`，Pydantic 解析成 dict 而非 str | **刪除**舊的三行 `__HPE/__IOS/__NXOS`，**新增**一行 `FETCHER_ENDPOINT__GET_VERSION=/switch/network/get_install_active/{switch_ip}`，見 [升級 Step 2](#step-2修改-env-中的版本端點必做否則啟動失敗) |
| App 啟動報 DB connection timeout 60s | DB 容器尚未就緒或連線資訊錯誤 | 確認 DB 容器 healthy（`docker ps`），檢查 `.env` 中 `DB_HOST`/`DB_PORT`/`DB_PASSWORD` 是否正確，K8s 環境確認 Service/Endpoint 可達 |

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
| 30 | `get_version_hpe_fna_parser.py` | `get_version_hpe_fna` | HPE | FNA | VersionData |
| 31 | `get_version_ios_fna_parser.py` | `get_version_ios_fna` | CISCO_IOS | FNA | VersionData |
| 32 | `get_version_nxos_fna_parser.py` | `get_version_nxos_fna` | CISCO_NXOS | FNA | VersionData |
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

## 附錄 D：SNMP 程式碼除錯指南（自己看懂 + 找問題）

> 當 SNMP 採集出問題，你可以自己追蹤程式碼找到根因。
> 這份指南用昨天「只有 version 成功」的案例來示範完整的除錯流程。

### D.1 SNMP 採集資料流（從排程到寫入 DB）

```
排程觸發 (scheduler.py)
  │
  ├─ _run_collection("get_fan")
  │
  └─ SnmpCollectionService.collect()          ← app/snmp/collection_service.py
      │
      ├─ 載入活躍歲修的設備清單
      │
      └─ 對每台設備平行執行（全域 Semaphore，所有 job 共用 SNMP_CONCURRENCY=20）：
          │
          ├─ session_cache.get_target(ip)      ← app/snmp/session_cache.py
          │   └─ 逐一嘗試 community → engine.get(sysObjectID.0)
          │       └─ 成功 → 快取 community，回傳 SnmpTarget
          │       └─ 全失敗 → SnmpTimeoutError
          │
          ├─ collector.collect_with_retry()    ← app/snmp/collector_base.py
          │   └─ 最多重試 3 次（間隔 1s, 2s）
          │       │
          │       └─ collector.collect()        ← app/snmp/collectors/fan.py (等)
          │           └─ engine.walk(target, OID_PREFIX)  ← app/snmp/engine.py
          │               └─ pysnmp bulkCmd → UDP 161 → 交換機
          │           └─ session_cache.get_ifindex_map()
          │           └─ 解析 varbind → 建立 ParsedData
          │
          └─ 寫入 DB（batch 存到 collection_data 表）
```

**關鍵分層：**

| 層級 | 檔案 | 職責 | 如果這層壞了 |
|------|------|------|------------|
| 1. 排程 | `app/scheduler.py` | 定時觸發 | 全部指標都不會跑 |
| 2. 服務 | `app/snmp/collection_service.py` | 載設備、平行採集、寫 DB | 全部設備都失敗 |
| 3. 快取 | `app/snmp/session_cache.py` | Community 偵測、ifIndex 對照 | 單台設備全部 collector 失敗 |
| 4. 收集器 | `app/snmp/collectors/*.py` | OID walk + 資料解析 | 單一指標失敗（如只有 fan 壞） |
| 5. 引擎 | `app/snmp/engine.py` | SNMP GET/WALK 底層通訊 | 所有用到 walk() 的 collector 爆 |

### D.2 從日誌判斷哪一層出問題

```bash
# 開啟完整日誌（必須！預設 WARNING 級別看不到大多數資訊）
# 在 .env 中設定：
APP_DEBUG=true

# 看日誌
docker logs netora_app -f --tail 200 2>&1 | grep -i "snmp\|collection\|error\|timeout"
```

**日誌訊息 → 問題在哪一層：**

| 你看到的日誌 | 出問題的層 | 意思 |
|-------------|-----------|------|
| `Running scheduled collection for 'get_fan'` 之後沒有任何日誌 | 2. 服務層 | 載入設備清單或初始化 engine 出錯 |
| `All communities failed for 10.0.0.1` | 3. 快取層 | Community 字串錯誤或交換機不回應 |
| `Community for 10.0.0.1: tccd03ro` | 3. 快取層 ✅ | Community 偵測成功（正常） |
| `get_fan: timeout for 10.0.0.1, retry 1/2` | 4. 收集器層 | walk() 超時，正在重試 |
| `SNMP WALK timeout: 10.0.0.1 prefix=1.3.6...` | 5. 引擎層 | bulkCmd 超時，網路問題 |
| `SNMP WALK error: ...` | 5. 引擎層 | pysnmp 回傳錯誤 |
| `SNMP get_fan for 2026Q1: 18/18 ok, 2.35s` | 全部正常 ✅ | 成功採集 |
| `SNMP get_fan for 2026Q1: 15/18 ok, 5.12s` | 部分設備失敗 | 3 台出問題，看 ERROR 日誌找原因 |
| `ValueError` / `TypeError` / `KeyError` | 4. 收集器層 | collector 程式碼 bug（解析錯誤） |

### D.3 案例：昨天「只有 version 成功」的追蹤過程

**Step 1：觀察症狀**
- version ✅ 成功寫入 DB
- 其他 9 個指標 ❌ 全部 0/0

**Step 2：看 version 和其他 collector 有什麼不同**

打開 `app/snmp/collectors/version.py`：
```python
# 第 68 行
result = await engine.get(target, SYS_DESCR)    # ← 用 get()
```

打開任何其他 collector，例如 `app/snmp/collectors/fan.py`：
```python
error_varbinds = await engine.walk(target, ...)  # ← 用 walk()
```

**差異：version 用 `get()`，其他 9 個都用 `walk()`。**

**Step 3：檢查 engine.py 的 walk() 實作**

打開 `app/snmp/engine.py`，找到 `_walk_impl()` 方法（第 162 行）：
```python
# 第 217-222 行（修復後的程式碼）
for var_bind_row in var_bind_table:
    if not var_bind_row:
        out_of_scope = True
        break
    oid, val = var_bind_row[0]    # ← 關鍵：取 [0] 解 2D 表格
```

如果原本寫的是 `oid, val = var_bind_row`（沒有 `[0]`），
pysnmp v6 回傳的 `var_bind_row` 是一個 `list[ObjectType]`，不是 `tuple`，
直接 unpack 就會 `ValueError: too many values to unpack`。

**Step 4：結論**

```
engine.get()  → getCmd()  → 回傳 1D [ObjectType, ...] → ✅ 正常 unpack
engine.walk() → bulkCmd() → 回傳 2D [[ObjectType], ...] → ❌ ValueError
```

只有 version 用 get()，所以只有 version 成功。

### D.4 除錯 Checklist：一步步排查

當某個指標出問題時，按這個順序檢查：

#### Step 1：確認問題範圍

```
□ 全部指標、全部設備 → 問題在 排程 或 服務層
□ 全部指標、單台設備 → 問題在 快取層（community 或 連通性）
□ 單一指標、全部設備 → 問題在 收集器層（collector 程式碼 bug）
□ 單一指標、單台設備 → 問題在 特定 OID 與特定設備的組合
```

#### Step 2：看日誌找錯誤

```bash
# 開 DEBUG 模式
# .env → APP_DEBUG=true → 重啟

# 找 ERROR 和 WARNING
docker logs netora_app --tail 500 2>&1 | grep -E "ERROR|WARNING|Traceback|ValueError|TypeError"

# 找特定 collector 的日誌
docker logs netora_app --tail 500 2>&1 | grep "get_fan"
```

#### Step 3：手動測 SNMP 連通

```bash
docker exec -it netora_app bash

# 測 GET（scalar OID，version 用的方式）
snmpget -v2c -c <community> <IP> 1.3.6.1.2.1.1.1.0

# 測 WALK（table OID，其他 collector 用的方式）
snmpwalk -v2c -c <community> <IP> 1.3.6.1.2.1.31.1.1.1.1   # ifName
```

如果 `snmpget` 成功但 `snmpwalk` 失敗 → 問題在交換機的 GETBULK 支援
如果兩個都失敗 → community 錯誤或網路不通

#### Step 4：看 collector 程式碼

每個 collector 的結構都一樣：

```python
# app/snmp/collectors/xxx.py
class XxxCollector(BaseSnmpCollector):
    api_name = "get_xxx"                       # ← Dashboard 上的指標名稱

    async def collect(self, target, device_type, session_cache, engine):
        # 1. Walk OID 拿 raw data
        varbinds = await engine.walk(target, SOME_OID)     # ← 這一步拿到的是 [(oid_str, val_str), ...]

        # 2. 拿 ifIndex → ifName 對照表
        ifindex_map = await session_cache.get_ifindex_map(target.ip)

        # 3. 解析 varbind → ParsedData
        for oid_str, val_str in varbinds:
            idx = self.extract_index(oid_str, SOME_OID)    # ← 從完整 OID 取出索引（如 ifIndex）
            value = self.safe_int(val_str)                 # ← 安全轉整數（失敗回 0）
            ifname = ifindex_map.get(int(idx))             # ← 查介面名稱
            # ... 建立 ParsedData ...

        return raw_text, results
```

**常見出錯點：**

| 位置 | 可能錯誤 | 怎麼看 |
|------|---------|--------|
| `engine.walk()` | OID 不支援、timeout | 看 ERROR 日誌或手動 snmpwalk |
| `extract_index()` | OID 結構與預期不同 | 用 snmpwalk 看實際回傳的完整 OID |
| `safe_int()` | 回傳不是數字（如 "Copper"、"0xa2"） | 用 snmpwalk 看回傳值的格式 |
| `ifindex_map.get()` | ifIndex 查不到 ifName | 手動 snmpwalk ifName 對照 |

#### Step 5：用 snmpwalk 對比程式預期

如果收集器的解析有問題，最關鍵的一步是用 snmpwalk 看**實際回傳的格式**：

```bash
# 例如懷疑 LAG 的 ActorOperState 有問題
snmpwalk -v2c -c <community> <IP> 1.2.840.10006.300.43.1.2.1.1.21
```

如果看到回傳是：
```
SNMPv2-SMI::...21.49153 = Hex-STRING: 3D
```

但 collector 用 `safe_int()` 解析 → `safe_int("0x3d")` 回傳 0 → **bug！**

修法：需要特殊解析函式（像我們加的 `_parse_oper_state_byte()`）。

**常見的 pysnmp 回傳格式陷阱：**

| MIB SYNTAX 定義 | pysnmp `prettyPrint()` 回傳格式 | 正確解析方式 |
|----------------|-------------------------------|------------|
| `INTEGER` | `"42"` | `safe_int()` 或 `int()` |
| `Counter32` | `"12345"` | `safe_int()` 或 `int()` |
| `OCTET STRING (SIZE(1))` | `"0x3d"` 或 `"3D"` | 需要特殊 hex parser |
| `DisplayString` | `"GigabitEthernet1/0/1"` | 直接當字串用 |
| `OBJECT IDENTIFIER` | `"1.3.6.1.4.1.25506..."` | 直接當字串比對 |
| 銅纜光模組特殊值 | `"Copper"` / `"N/A"` | `try: int(val)` + `except` 跳過 |

### D.5 程式碼檔案導覽

如果你需要改程式碼，這是每個檔案的用途：

```
app/snmp/
├── engine.py              # 底層 SNMP 通訊（get/walk/bulkCmd）
│                            通常不需要改，除非 pysnmp 行為有變
│
├── session_cache.py       # Community 偵測 + ifIndex/bridge port 快取
│                            如果某台交換機的 community 偵測邏輯需要調整
│
├── collection_service.py  # 採集服務主流程（載設備、平行採集、寫 DB）
│                            如果要改採集並行度或重試邏輯
│
├── collector_base.py      # Collector 基底類別（retry、extract_index、safe_int）
│                            所有 collector 的共用方法在這
│
├── oid_maps.py            # 所有 OID 常數 + 值對照表
│                            如果需要新增 OID 或改值映射
│
└── collectors/            # 10 個 collector（每個指標一個檔案）
    ├── fan.py             # HPE: ENTITY-MIB + HH3C-ENTITY-EXT
    ├── power.py           # HPE: ENTITY-MIB + HH3C-ENTITY-EXT
    ├── version.py         # SNMPv2-MIB sysDescr（唯一用 get() 的）
    ├── transceiver.py     # HPE: HH3C-TRANSCEIVER / Cisco: ENTITY-SENSOR
    ├── error_count.py     # IF-MIB ifInErrors + ifOutErrors
    ├── channel_group.py   # IEEE8023-LAG-MIB
    ├── neighbor_lldp.py   # LLDP-MIB
    ├── neighbor_cdp.py    # CISCO-CDP-MIB（僅 Cisco）
    ├── mac_table.py       # Q-BRIDGE / BRIDGE-MIB
    └── interface_status.py # IF-MIB + EtherLike-MIB
```

### D.6 自己修 Bug 的流程

如果你在公司遇到問題，需要自己修的話：

```
1. 看日誌 → 確定是哪個 collector 壞了
     ↓
2. snmpwalk → 看交換機實際回傳的 OID 格式和值
     ↓
3. 比對 collector 程式碼 → 找到解析那一段
     ↓
4. 改程式碼（vi app/snmp/collectors/xxx.py）
     ↓
5. 在公司重建 image（見 SOP 1b.8）：
   docker build \
     --build-arg BASE_IMAGE=<公司registry>/network-dashboard-base:v2.19.0 \
     -f docker/production/Dockerfile \
     -t netora-production:v2.9.0-fix1 .
     ↓
6. 重啟服務，觀察日誌確認修復
```

**改 collector 程式碼的注意事項：**

1. 每個 collector 的 `collect()` 方法必須回傳 `tuple[str, list[ParsedData]]`
2. `extract_index(oid_str, OID_PREFIX)` → 取出 OID 的最後一段索引
3. `safe_int(val_str, default=0)` → 安全轉整數，失敗回 default
4. 如果遇到非 INTEGER 的 SYNTAX（如 OCTET STRING），需要自己寫解析
5. 改完後如果有網路環境，可以跑測試：`python -m pytest tests/unit/snmp/ -v`

### D.7 歷史 Bug 參考

以下是已經修過的 bug，如果遇到類似問題可以參考修法：

| Bug | 根因 | 修法 | 修在哪 |
|-----|------|------|--------|
| 全部 collector 爆掉，只有 version 活 | pysnmp v6 `bulkCmd` 回傳 2D 表格，`walk()` 沒處理 | `var_bind_row[0]` 取第一個元素 | `engine.py:222` |
| SNMP 完全連不上 | `SNMP_COMMUNITIES` 設定值解析錯誤（list vs str） | 改 config 為 str + property 拆分 | `config.py` |
| LLDP 鄰居全部被跳過 | `lldpRemTimeMark` 可以很大（如 1338488631），索引 >= 3 段 | `_parse_lldp_remote_index()` 改用 `parts[-2]`, `parts[-1]` | `neighbor_lldp.py:51` |
| LAG 成員狀態全 down | `ActorOperState` 是 OCTET STRING(1)，pysnmp 回 `"0x3d"` | 新增 `_parse_oper_state_byte()` 處理 hex | `channel_group.py:42` |
| 銅纜 SFP 出現錯誤的 0.0 dBm | 銅纜模組回 `"Copper"` 不是數字，`safe_int()` 回 0 | `try: int(val)` + `except` 跳過 | `transceiver.py:98` |

---

## 快速指令卡（列印帶著用）

```
# ===== Phase 1: 起服務（SNMP Mock，推薦首次驗證）=====
unzip netora-main.zip && cd netora-main
docker pull <公司registry>/network-dashboard-base:v2.19.0
cp .env.mock .env
# 編輯 .env：APP_IMAGE=<公司registry>/network-dashboard-base:v2.19.0
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
    --build-arg BASE_IMAGE=<公司registry>/network-dashboard-base:v2.19.0 \
    -f docker/production/Dockerfile \
    -t netora-production:v2.9.0 .
# 編輯 .env: APP_IMAGE=netora-production:v2.9.0
docker-compose -f docker-compose.production.yml down
docker-compose -f docker-compose.production.yml up -d
# alembic 自動執行
```

---

## 附錄 E：Kubernetes 部署指南（API / Scheduler 分離架構）

> **適用情境**：從 Docker Compose 遷移到 Kubernetes，或需要水平擴展 API 層。
>
> **架構原理**：同一個 image 透過環境變數 `ENABLE_SCHEDULER` 控制角色：
> - `true`（預設）= 啟動排程 + API（Scheduler Pod）
> - `false` = 只跑 API，不啟動排程（API Pod）
>
> 分離的好處：
> 1. **隔離**：採集任務（SNMP/Ping）不阻塞 API 回應
> 2. **獨立擴展**：API 流量大加 replica，採集不受影響
> 3. **故障不擴散**：Worker OOM 不影響 API 服務

### E.1 資源分配建議

以 **400 台設備** 為基準：

| 元件 | 類型 | Replicas | CPU req/limit | MEM req/limit | PVC |
|------|------|----------|---------------|---------------|-----|
| **netora-api** | Deployment | 2-3 | 200m / 1000m | 256Mi / 512Mi | — |
| **netora-scheduler** | Deployment | **1** | 500m / 2000m | 1Gi / 4Gi | — |
| **mariadb** | StatefulSet | 1 | 500m / 2000m | 512Mi / 2Gi | 20Gi (SSD) |
| **seaweedfs** | StatefulSet | 1 | 100m / 500m | 256Mi / 1Gi | 10Gi |
| **phpmyadmin** | Deployment | 1 | 50m / 500m | 128Mi / 256Mi | — |

> **v2.19.6 Scheduler 資源需求變更（Collector 並行化）**：
>
> v2.19.6 起每台設備的 8 個 collector 並行執行（`asyncio.gather`），峰值 subprocess 數量 = `SNMP_CONCURRENCY × 8`。
> 每個 `snmpbulkwalk` subprocess 約 5MB RSS，需要相應調整 Scheduler memory：
>
> | SNMP_CONCURRENCY | 峰值 subprocess | 峰值額外 RAM | 建議 Scheduler MEM limit | full_round 預估時間 (400 台) |
> |---|---|---|---|---|
> | 50（預設） | 400 | ~2GB | **4Gi** | ~2 min |
> | 30（保守） | 240 | ~1.2GB | **3Gi** | ~3.5 min |
> | 20（省資源） | 160 | ~800MB | **2Gi** | ~5 min |
>
> CPU 影響小（subprocess 為 I/O bound），CPU limit 維持 2000m 即可。

> **設備規模換算**：
> - 200-500 台：上表配置
> - 500-1000 台：Scheduler CPU 1000m/4000m、MEM 2Gi/8Gi、DB PVC 50Gi
> - 1000+ 台：Scheduler CPU 2000m/4000m、MEM 4Gi/8Gi、DB PVC 100Gi
> - API 不用調，加 replica 即可

### E.2 Manifest 範例

#### API Deployment（可水平擴展）

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: netora-api
  labels:
    app: netora
    role: api
spec:
  replicas: 2
  selector:
    matchLabels:
      app: netora
      role: api
  template:
    metadata:
      labels:
        app: netora
        role: api
    spec:
      containers:
      - name: app
        image: registry.company.com/netora/network-dashboard-base:v2.19.0
        ports:
        - containerPort: 8000
        env:
        - name: ENABLE_SCHEDULER
          value: "false"
        - name: DB_POOL_SIZE       # API 輕量，少連線即可
          value: "5"
        - name: DB_MAX_OVERFLOW
          value: "10"
        # --- 以下與 .env.production 相同，改用 ConfigMap/Secret 管理 ---
        envFrom:
        - configMapRef:
            name: netora-config
        - secretRef:
            name: netora-secrets
        resources:
          requests:
            cpu: "200m"
            memory: "256Mi"
          limits:
            cpu: "1000m"
            memory: "512Mi"
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 15
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 30
```

#### Scheduler Deployment（固定 1 replica）

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: netora-scheduler
  labels:
    app: netora
    role: scheduler
spec:
  replicas: 1                    # ⚠️ 必須為 1，避免重複採集
  strategy:
    type: Recreate               # 不要 RollingUpdate，確保同時只有一個
  selector:
    matchLabels:
      app: netora
      role: scheduler
  template:
    metadata:
      labels:
        app: netora
        role: scheduler
    spec:
      containers:
      - name: app
        image: registry.company.com/netora/network-dashboard-base:v2.19.0
        ports:
        - containerPort: 8000
        env:
        - name: ENABLE_SCHEDULER
          value: "true"
        - name: DB_POOL_SIZE       # Scheduler 密集 DB 操作，需要多連線
          value: "15"
        - name: DB_MAX_OVERFLOW
          value: "30"
        envFrom:
        - configMapRef:
            name: netora-config
        - secretRef:
            name: netora-secrets
        resources:
          requests:
            cpu: "500m"
            memory: "1Gi"
          limits:
            cpu: "2000m"
            memory: "4Gi"       # v2.19.6: 並行 collector, 峰值 CONCURRENCY×8 subprocess
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 60
          periodSeconds: 30
```

#### Service（指向 API pods，Scheduler 也可收 API 但不必要）

```yaml
apiVersion: v1
kind: Service
metadata:
  name: netora-api
spec:
  selector:
    app: netora
    role: api
  ports:
  - port: 8000
    targetPort: 8000
```

#### MariaDB StatefulSet

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: mariadb
spec:
  serviceName: mariadb
  replicas: 1
  selector:
    matchLabels:
      app: mariadb
  template:
    metadata:
      labels:
        app: mariadb
    spec:
      containers:
      - name: mariadb
        image: registry.company.com/netora/netora-mariadb:10.11
        ports:
        - containerPort: 3306
        env:
        - name: MARIADB_ROOT_PASSWORD
          valueFrom:
            secretKeyRef:
              name: netora-secrets
              key: DB_ROOT_PASSWORD
        - name: MARIADB_DATABASE
          value: "netora"
        - name: MARIADB_USER
          value: "admin"
        - name: MARIADB_PASSWORD
          valueFrom:
            secretKeyRef:
              name: netora-secrets
              key: DB_PASSWORD
        resources:
          requests:
            cpu: "500m"
            memory: "512Mi"
          limits:
            cpu: "2000m"
            memory: "2Gi"
        volumeMounts:
        - name: data
          mountPath: /var/lib/mysql
        - name: config
          mountPath: /etc/mysql/conf.d
      volumes:
      - name: config
        configMap:
          name: mariadb-config
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: ssd        # 依環境替換（gp3, premium-rw 等）
      resources:
        requests:
          storage: 20Gi
```

#### SeaweedFS StatefulSet

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: seaweedfs
spec:
  serviceName: seaweedfs
  replicas: 1
  selector:
    matchLabels:
      app: seaweedfs
  template:
    metadata:
      labels:
        app: seaweedfs
    spec:
      containers:
      - name: seaweedfs
        image: registry.company.com/netora/netora-seaweedfs:4.13
        ports:
        - containerPort: 8333
        resources:
          requests:
            cpu: "100m"
            memory: "256Mi"
          limits:
            cpu: "500m"
            memory: "1Gi"
        volumeMounts:
        - name: data
          mountPath: /data
  volumeClaimTemplates:
  - metadata:
      name: data
    spec:
      accessModes: ["ReadWriteOnce"]
      resources:
        requests:
          storage: 10Gi
```

#### MariaDB ConfigMap（調整 max_connections）

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mariadb-config
data:
  custom.cnf: |
    [mysqld]
    max_connections = 300
```

> **連線數計算**：API ×3（每個 max 15）+ Scheduler ×1（max 45）= 90 連線，300 留有餘裕。

#### ConfigMap / Secret（將 .env.production 拆開）

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: netora-config
data:
  # ── DB ──
  DB_HOST: "mariadb"
  DB_PORT: "3306"
  DB_NAME: "netora"
  DB_USER: "admin"
  DB_POOL_SIZE: "10"
  DB_MAX_OVERFLOW: "20"

  # ── 採集模式 ──
  COLLECTION_MODE: "snmp"
  APP_DEBUG: "false"
  ENABLE_SCHEDULER: "true"

  # ── SNMP（v2.19.1 device-centric rounds） ──
  # v2.19.1 架構：2 個 SNMP rounds + ACL legacy jobs
  #   fast_round (300s): mac_table + interface_status（每台設備 probe 1 次 + walk 2 次）
  #   full_round (1800s): fan, power, version, gbic, error_count, channel_group, lldp, cdp
  #   ACL (300s): get_static_acl + get_dynamic_acl（REST API passthrough, sem=10）
  #
  # 超時層級（由內到外）：
  #   1. Per-PDU:    timeout×(retries+1)+2 = 3×2+2 = 8s（硬上限 _MAX_PDU_WAIT=30s）
  #   2. Walk:       60s deadline（正常 5-15s 完成）
  #   3. Collector:  walk × (collector_retries+1) ≈ 120s
  #   4. Device:     _DEVICE_HARD_TIMEOUT = 90s（整台設備 SNMP 階段上限）
  #   5. Negative:   probe 失敗 → 5 分鐘不再嘗試
  SNMP_TIMEOUT: "3"                 # 單一 PDU timeout (秒)。3×(1+1)+2=8s per-PDU
  SNMP_RETRIES: "1"                 # PDU 層 retry（pysnmp transport）
  SNMP_CONCURRENCY: "20"            # 全域 semaphore，一個 slot = 一台設備正在被採集
  SNMP_WALK_TIMEOUT: "60"           # 單次 walk deadline (秒)。大型 table 5-15s，60s 已很寬裕
  SNMP_COLLECTOR_RETRIES: "1"       # walk timeout 後 collector 層 retry。1 次 = 最多 2 輪 walk
  SNMP_MAX_REPETITIONS: "25"        # GETBULK 每 PDU 回傳 OID 數

  # ── Ping（13 個 tenant）──
  GNMSPING__TIMEOUT: "15"
  GNMSPING__ENDPOINT: "/api/v1/ping"
  GNMSPING__BASE_URLS__Infra: "http://public-gnmspingsvc.netsre.icsd.tsmc.com/"
  GNMSPING__BASE_URLS__Fab200mm: "http://public-gnmspingsvc.netsre.edg.200mm.tsmc.com/"
  GNMSPING__BASE_URLS__AP: "http://public-gnmspingsvc.netsre.edg.ap.tsmc.com/"
  GNMSPING__BASE_URLS__F6: "http://public-gnmspingsvc.netsre.edg.f6.tsmc.com/"
  GNMSPING__BASE_URLS__F12: "http://public-gnmspingsvc.netsre.edg.f12.tsmc.com/"
  GNMSPING__BASE_URLS__F14: "http://public-gnmspingsvc.netsre.edg.f14.tsmc.com/"
  GNMSPING__BASE_URLS__F15: "http://public-gnmspingsvc.netsre.edg.f15.tsmc.com/"
  GNMSPING__BASE_URLS__F16: "http://public-gnmspingsvc.netsre.edg.f16.tsmc.com/"
  GNMSPING__BASE_URLS__F18: "http://public-gnmspingsvc.netsre.edg.f18.tsmc.com/"
  GNMSPING__BASE_URLS__F20: "http://public-gnmspingsvc.netsre.edg.f12.tsmc.com/"
  GNMSPING__BASE_URLS__F21: "http://public-gnmspingsvc.netsre.edg.f21.tsmc.com/"
  GNMSPING__BASE_URLS__F22: "http://public-gnmspingsvc.netsre.edg.f22.tsmc.com/"
  GNMSPING__BASE_URLS__F23: "http://public-gnmspingsvc.netsre.edg.f23tsmc.com/"

  # ── GNMS MacARP（v2.21.0 Client 自動匯入）──
  GNMS_MACARP__BASE_URL: "http://netinv.netsre.icsd.tsmc.com"
  GNMS_MACARP__TIMEOUT: "60"
  GNMS_MACARP__BATCH_SIZE: "100"

---
apiVersion: v1
kind: Secret
metadata:
  name: netora-secrets
type: Opaque
stringData:
  DB_PASSWORD: "<強密碼>"
  DB_ROOT_PASSWORD: "<強密碼>"
  JWT_SECRET: "<隨機字串>"
  FETCHER_SOURCE__FNA__TOKEN: "<FNA token>"
  GNMSPING__TOKEN: "<Ping token>"
  GNMS_MACARP__TOKEN: "<GNMS MacARP token>"
```

### E.3 驗證部署

```bash
# 確認所有 Pod 正常
kubectl get pods -l app=netora

# 確認 API 可用
kubectl port-forward svc/netora-api 8000:8000
curl http://localhost:8000/health

# 確認 Scheduler 有啟動排程（看 log）
kubectl logs -l role=scheduler --tail=20
# 應看到 "Started X scheduled jobs"

# 確認 API Pod 沒有排程（看 log）
kubectl logs -l role=api --tail=20
# 應看到 "Scheduler disabled (ENABLE_SCHEDULER=false), running as API-only"
```

### E.4 注意事項

1. **Scheduler 必須只有 1 個 replica**，否則排程任務會重複執行
2. **Scheduler strategy 用 `Recreate`**，避免滾動更新時短暫出現 2 個 scheduler
3. **DB PVC 用 SSD storageClass**，MEDIUMTEXT 欄位的讀寫效能差異明顯
4. **不設 `ENABLE_SCHEDULER` 時預設為 `true`**，與現有 Docker Compose 部署行為完全相同
5. **.env 遷移到 ConfigMap/Secret**：機敏資料（密碼、token）放 Secret，其餘放 ConfigMap
