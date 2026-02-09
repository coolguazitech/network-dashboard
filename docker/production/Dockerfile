# =============================================================================
# 生產映像檔：基礎映像檔 + 公司專屬 Fetcher & Parser 實作
#
# 此 Dockerfile 用於公司端，將連接真實 API 的 fetcher/parser 實作加入基礎映像檔
#
# 建構指令：
#   docker build \
#       --build-arg DOCKERHUB_USER=coolguazi \
#       --build-arg BASE_VERSION=v1.1.0 \
#       -f docker/production/Dockerfile \
#       -t your-registry/network-dashboard:v1.1.0 \
#       .
#
# 注意：
#   - Base image 已包含：完整框架 + mock fetcher + parsers + 前端
#   - Production 覆蓋：公司專屬的 fetcher 實作 + parser plugins（配合真實 raw data 格式）
# =============================================================================

# 參數定義
ARG DOCKERHUB_USER=coolguazi
ARG BASE_VERSION=v1.1.0

# 使用從 DockerHub 拉取的基礎映像檔
FROM ${DOCKERHUB_USER}/network-dashboard-base:${BASE_VERSION}

# 標籤資訊
LABEL maintainer="your-email@company.com" \
      version="1.1.0" \
      description="Network Dashboard Production Image with Real Fetchers & Parsers"

# 切換到 root 以複製檔案
USER root

# 覆蓋 Fetcher 實作（連接 FNA/DNA/GNMS API）
COPY --chown=appuser:appgroup app/fetchers/api_functions.py /app/app/fetchers/
COPY --chown=appuser:appgroup app/fetchers/implementations.py /app/app/fetchers/

# 覆蓋 Parser plugins（配合真實設備 raw data 格式）
COPY --chown=appuser:appgroup app/parsers/plugins/ /app/app/parsers/plugins/

# 覆蓋測試資料（若需要）
COPY --chown=appuser:appgroup test_data/ /app/test_data/

# 確保權限正確
RUN chown -R appuser:appgroup /app

# 切換回非 root 使用者
USER appuser

# 驗證模組可正常載入
RUN python -c "\
from app.fetchers.registry import FetcherRegistry; \
from app.parsers.registry import get_parser; \
print('All modules loaded successfully')"

# 繼承基礎映像檔的 ENTRYPOINT 和 CMD
