# =============================================================================
# 生產映像檔：基礎映像檔 + 公司端修改過的 Parser plugins
#
# 此 Dockerfile 用於公司端，在 Parser 開發完成後將修改過的 parser 疊加到 base image。
# Base image 已包含完整系統（前端 + 後端 + 依賴），此處只覆蓋 parser 和設定。
#
# 建構指令：
#   docker build \
#       --build-arg BASE_IMAGE=<公司registry>/network-dashboard-base:v2.2.2 \
#       -f docker/production/Dockerfile \
#       -t netora-production:v2.2.2 \
#       .
# =============================================================================

# 參數定義
# BASE_IMAGE: 公司 registry 掃描通過後的完整 image URL
# 例如: registry.company.com/netora/network-dashboard-base:v2.2.2
ARG BASE_IMAGE=coolguazi/network-dashboard-base:v2.2.2

# 使用基礎映像檔（公司 registry 或 DockerHub）
FROM ${BASE_IMAGE}

# 標籤資訊
LABEL maintainer="network-dashboard@company.com" \
      version="2.2.2" \
      description="Network Dashboard Production - Real Parser plugins"

# 切換到 root 以複製檔案
USER root

# 覆蓋 Parser plugins（配合真實設備 raw data 格式）
COPY --chown=appuser:appgroup app/parsers/plugins/ /app/app/parsers/plugins/

# 覆蓋設定檔（scheduler.yaml 等）
COPY --chown=appuser:appgroup config/ /app/config/

# 覆蓋 Alembic 遷移檔（確保新版 migration 被包含）
COPY --chown=appuser:appgroup alembic/ /app/alembic/

# 確保權限正確
RUN chown -R appuser:appgroup /app

# 切換回非 root 使用者
USER appuser

# 驗證模組可正常載入
RUN python -c "\
from app.core.config import settings; \
from app.fetchers.registry import FetcherRegistry; \
from app.parsers.registry import auto_discover_parsers, parser_registry; \
count = auto_discover_parsers(); \
print(f'All modules loaded successfully — {count} parser modules, {len(parser_registry._parsers)} registered')"

# 繼承基礎映像檔的 ENTRYPOINT 和 CMD
