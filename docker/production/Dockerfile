# =============================================================================
# 生產映像檔：基礎映像檔 + Fetcher/Parser 實作
#
# 此 Dockerfile 用於公司端，將 fetcher 和 parser 實作加入基礎映像檔
#
# 建構指令：
#   docker build \
#       --build-arg DOCKERHUB_USER=your-username \
#       --build-arg BASE_VERSION=v1.0.0 \
#       -f docker/production/Dockerfile \
#       -t your-registry/network-dashboard:v1.0.0 \
#       .
# =============================================================================

# 參數定義
ARG DOCKERHUB_USER=coolguazi
ARG BASE_VERSION=v1.0.0

# 使用從 DockerHub 拉取的基礎映像檔
FROM ${DOCKERHUB_USER}/network-dashboard-base:${BASE_VERSION}

# 標籤資訊
LABEL maintainer="your-email@company.com" \
      version="1.0.0" \
      description="Network Dashboard Production Image with Fetchers/Parsers"

# 切換到 root 以複製檔案
USER root

# 複製 Fetcher 實作
# 這些檔案在公司環境中存在，包含連接真實 API 的程式碼
COPY --chown=appuser:appgroup app/fetchers/api_functions.py /app/app/fetchers/
COPY --chown=appuser:appgroup app/fetchers/implementations.py /app/app/fetchers/
COPY --chown=appuser:appgroup app/fetchers/mock.py /app/app/fetchers/

# 複製 Parser 實作
COPY --chown=appuser:appgroup app/parsers/client_parsers.py /app/app/parsers/
COPY --chown=appuser:appgroup app/parsers/plugins/ /app/app/parsers/plugins/

# 複製測試資料（若需要 Mock 模式）
COPY --chown=appuser:appgroup test_data/ /app/test_data/

# 確保權限正確
RUN chown -R appuser:appgroup /app

# 切換回非 root 使用者
USER appuser

# 驗證模組可正常載入
RUN python -c "from app.fetchers.registry import FetcherRegistry; from app.parsers.registry import get_parser; print('All modules loaded successfully')"

# 繼承基礎映像檔的 ENTRYPOINT 和 CMD
