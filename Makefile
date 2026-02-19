# =============================================================================
# Makefile — Parser 驗證框架
# =============================================================================
#
# 使用流程：
#   1. 編輯 config/api_test.yaml 填入真實 API URL 和交換機 IP
#   2. make fetch          → 撈取所有 API raw data
#   3. make parse          → 把 raw data 餵進 parser 看結果
#
# 其他常用指令：
#   make fetch-dry         → 只印 URL 不實際呼叫
#   make test-parsers      → fetch + parse 一次跑完
#   make clean-raw         → 清除 raw data 和報告
# =============================================================================

.PHONY: fetch fetch-dry parse parse-verbose parse-debug parse-ok parse-reset test-parsers clean-raw help mock-server fetch-mock fetch-sample verify collect-once mock-timeseries

# 預設目標
help:
	@echo ""
	@echo "Parser 驗證框架"
	@echo "==============="
	@echo ""
	@echo "  make fetch            撈取所有 API raw data (存到 test_data/raw/)"
	@echo "  make fetch-dry        只印 URL 不實際呼叫"
	@echo "  make parse            Parse 所有已存的 raw data"
	@echo "  make parse-verbose    Parse 並印完整 JSON"
	@echo "  make parse-debug      為所有 parser 產生 AI 評估 bundle"
	@echo "  P=xxx make parse-ok   標記 parser 已收斂 (AI 回 OK)"
	@echo "  make parse-reset      重置所有收斂標記"
	@echo "  make test-parsers     fetch + parse 一次跑完"
	@echo "  make clean-raw        清除 raw data、報告、收斂標記"
	@echo ""
	@echo "過濾選項 (透過環境變數)："
	@echo "  API=get_fan make fetch        只撈特定 API"
	@echo "  TARGET=10.1.1.1 make fetch    只撈特定交換機"
	@echo "  API=get_fan make parse        只測特定 API"
	@echo ""
	@echo "隨機取樣（從大量設備清單）："
	@echo "  make fetch-sample             從 inventory 隨機挑 20 台 (預設)"
	@echo "  N=50 make fetch-sample        從 inventory 隨機挑 50 台"
	@echo ""
	@echo "採集驗證："
	@echo "  make verify                   端到端 pipeline 驗證 (in-memory, 秒級)"
	@echo "  make collect-once             對真實 DB 跑一輪採集 (mock fetcher)"
	@echo "  MID=xxx make collect-once     指定歲修 ID"
	@echo "  API=get_fan make collect-once 只跑特定 API"
	@echo ""
	@echo "時間序列測試："
	@echo "  make mock-timeseries          模擬多輪採集 (預設 10 輪, 2s 間隔)"
	@echo "  N=30 INTERVAL=1 make mock-timeseries  自訂輪數和間隔"
	@echo ""
	@echo "Mock 測試："
	@echo "  make mock-server              啟動 Mock API server (port 9999)"
	@echo "  make fetch-mock               用 Mock config 撈取 (需先啟動 mock-server)"
	@echo ""
	@echo "Timeout 選項："
	@echo "  TIMEOUT=60 make fetch                     覆蓋 read timeout (秒)"
	@echo "  CONNECT_TIMEOUT=5 make fetch              設定 connect timeout (秒)"
	@echo "  TIMEOUT=60 CONNECT_TIMEOUT=5 make fetch   同時設定兩者"
	@echo ""
	@echo "注意: make fetch 預設會先清空 test_data/raw/ (NO_CLEAN=1 可跳過)"
	@echo ""

# ── Fetch raw data from real APIs (auto-cleans test_data/raw/ by default) ──
fetch:
	python scripts/fetch_raw.py $(if $(API),--api $(API)) $(if $(TARGET),--target $(TARGET)) $(if $(TIMEOUT),--timeout $(TIMEOUT)) $(if $(CONNECT_TIMEOUT),--connect-timeout $(CONNECT_TIMEOUT)) $(if $(NO_CLEAN),--no-clean)

# ── Dry run — print URLs only ──
fetch-dry:
	python scripts/fetch_raw.py --dry-run $(if $(API),--api $(API)) $(if $(TARGET),--target $(TARGET)) $(if $(TIMEOUT),--timeout $(TIMEOUT)) $(if $(CONNECT_TIMEOUT),--connect-timeout $(CONNECT_TIMEOUT))

# ── Parse saved raw data ──
parse:
	python scripts/parse_test.py $(if $(API),--api $(API))

# ── Parse with full JSON output ──
parse-verbose:
	python scripts/parse_test.py --verbose --save-report $(if $(API),--api $(API))

# ── Generate debug bundles for failing parsers ──
parse-debug:
	python scripts/generate_debug.py $(if $(API),--api $(API))

# ── Mark parser(s) as converged (AI confirmed OK) ──
parse-ok:
	python scripts/generate_debug.py --ok $(P)

# ── Reset all converged marks ──
parse-reset:
	python scripts/generate_debug.py --reset

# ── Full pipeline: fetch + parse ──
test-parsers: fetch parse

# ── Mock API server for local testing ──
mock-server:
	python scripts/mock_api_server.py

# ── Fetch using mock config (requires mock-server running) ──
fetch-mock:
	python scripts/fetch_raw.py --config config/api_test_mock.yaml $(if $(API),--api $(API)) $(if $(TARGET),--target $(TARGET)) $(if $(TIMEOUT),--timeout $(TIMEOUT)) $(if $(CONNECT_TIMEOUT),--connect-timeout $(CONNECT_TIMEOUT))

# ── Fetch with random sampling from device inventory ──
fetch-sample:
	python scripts/fetch_raw.py --inventory config/device_inventory.csv --sample $(or $(N),20) $(if $(API),--api $(API)) $(if $(TIMEOUT),--timeout $(TIMEOUT)) $(if $(CONNECT_TIMEOUT),--connect-timeout $(CONNECT_TIMEOUT))

# ── Pipeline verification (in-memory, no external dependency) ──
verify:
	python scripts/verify_pipeline.py

# ── Single collection cycle against real DB with mock fetchers ──
collect-once:
	python scripts/collect_once.py $(if $(MID),--mid $(MID)) $(if $(API),--api $(API))

# ── Mock timeseries test (multi-cycle collection with hash dedup) ──
mock-timeseries:
	python scripts/mock_timeseries.py --cycles $(or $(N),10) --interval $(or $(INTERVAL),2)

# ── Clean raw data, reports, and debug bundles ──
clean-raw:
	rm -rf test_data/raw/ test_data/reports/ test_data/debug/
	@echo "Cleaned test_data/raw/, test_data/reports/, and test_data/debug/"
