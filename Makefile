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

.PHONY: fetch fetch-dry parse parse-verbose test-parsers clean-raw help

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
	@echo "  make test-parsers     fetch + parse 一次跑完"
	@echo "  make clean-raw        清除 raw data 和報告"
	@echo ""
	@echo "過濾選項 (透過環境變數)："
	@echo "  API=get_fan make fetch        只撈特定 API"
	@echo "  TARGET=10.1.1.1 make fetch    只撈特定交換機"
	@echo "  API=get_fan make parse        只測特定 API"
	@echo ""

# ── Fetch raw data from real APIs ──
fetch:
	python scripts/fetch_raw.py $(if $(API),--api $(API)) $(if $(TARGET),--target $(TARGET))

# ── Dry run — print URLs only ──
fetch-dry:
	python scripts/fetch_raw.py --dry-run $(if $(API),--api $(API)) $(if $(TARGET),--target $(TARGET))

# ── Parse saved raw data ──
parse:
	python scripts/parse_test.py $(if $(API),--api $(API))

# ── Parse with full JSON output ──
parse-verbose:
	python scripts/parse_test.py --verbose --save-report $(if $(API),--api $(API))

# ── Full pipeline: fetch + parse ──
test-parsers: fetch parse

# ── Clean raw data and reports ──
clean-raw:
	rm -rf test_data/raw/ test_data/reports/
	@echo "Cleaned test_data/raw/ and test_data/reports/"
