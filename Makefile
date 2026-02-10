.PHONY: help test-apis gen-parsers test-parsers all clean docker-test-apis docker-gen-parsers docker-test-parsers docker-all

# Default target
help:
	@echo "========================================"
	@echo "  Parser Development Toolchain"
	@echo "========================================"
	@echo ""
	@echo "Local Python Execution (Option A):"
	@echo "  make test-apis      - Batch test all APIs"
	@echo "  make gen-parsers    - Generate parser skeletons"
	@echo "  make test-parsers   - Validate parsers"
	@echo "  make all            - Run all steps"
	@echo ""
	@echo "Container Execution (Option B):"
	@echo "  make docker-test-apis      - Test APIs inside container"
	@echo "  make docker-gen-parsers    - Generate parsers inside container"
	@echo "  make docker-test-parsers   - Test parsers inside container"
	@echo "  make docker-all            - Run all steps inside container"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean          - Clean generated reports"
	@echo ""

# ============================================================================
# Local Python Execution (Option A)
# ============================================================================

# Batch test all APIs
test-apis:
	@echo "🚀 Testing all APIs from config/api_test.yaml..."
	@python scripts/batch_test_apis.py

# Generate parser skeletons
gen-parsers:
	@echo "📝 Generating parser skeletons..."
	@python scripts/generate_parsers.py

# Test parsers
test-parsers:
	@echo "🧪 Testing parsers with raw data..."
	@python scripts/test_parsers.py

# Run all steps
all: test-apis gen-parsers test-parsers
	@echo "🎉 All steps completed!"

# ============================================================================
# Container Execution (Option B)
# ============================================================================

# Test APIs inside container
docker-test-apis:
	@echo "🚀 Testing all APIs inside container..."
	@docker-compose exec app python scripts/batch_test_apis.py

# Generate parsers inside container
docker-gen-parsers:
	@echo "📝 Generating parser skeletons inside container..."
	@docker-compose exec app python scripts/generate_parsers.py

# Test parsers inside container
docker-test-parsers:
	@echo "🧪 Testing parsers inside container..."
	@docker-compose exec app python scripts/test_parsers.py

# Run all steps inside container
docker-all:
	@echo "🚀 Running full toolchain inside container..."
	@docker-compose exec app make test-apis
	@docker-compose exec app make gen-parsers
	@docker-compose exec app make test-parsers
	@echo "🎉 All steps completed!"

# ============================================================================
# Utilities
# ============================================================================

# Clean reports
clean:
	@echo "🧹 Cleaning reports..."
	@rm -f reports/api_test_*.json
	@rm -f reports/parser_test_*.json
	@echo "✅ Reports cleaned"
