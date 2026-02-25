# =============================================================================
# 基礎映像檔：Python 3.11 + Node.js 18 + 依賴套件
# 平台：linux/amd64 (x86_64)
#
# 建構指令：
#   docker buildx build --platform linux/amd64 \
#       -f docker/base/Dockerfile \
#       -t coolguazi/network-dashboard-base:v2.2.2 \
#       --load .
# =============================================================================

# 目標平台參數
ARG TARGETPLATFORM=linux/amd64

# -----------------------------------------------------------------------------
# Stage 1: Node.js 建構前端
# -----------------------------------------------------------------------------
FROM --platform=$TARGETPLATFORM node:18-bookworm-slim AS frontend-builder

WORKDIR /app/frontend

# 複製 package.json 先安裝依賴（利用 Docker 快取）
COPY frontend/package*.json ./

# 安裝所有 npm 依賴（包含 devDependencies，vite 是建構工具）
RUN npm ci && \
    npm cache clean --force

# 複製前端原始碼並建構
COPY frontend/ ./
RUN npm run build

# -----------------------------------------------------------------------------
# Stage 2: Python 依賴安裝
# -----------------------------------------------------------------------------
FROM --platform=$TARGETPLATFORM python:3.11-slim-trixie AS python-deps

# 設定環境變數
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安裝編譯依賴（包含 bcrypt 需要的 libffi）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-libmysqlclient-dev \
    libpq-dev \
    libffi-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 複製依賴定義檔
COPY pyproject.toml ./

# 建立虛擬環境並安裝依賴
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip && \
    # 升級 setuptools 到最新版本以修復 vendored 依賴的 CVE
    pip install --upgrade "setuptools>=75.0.0" "wheel>=0.46.2" && \
    pip install . && \
    # 再次確保 wheel 和 jaraco.context 是最新版本
    pip install --upgrade "jaraco.context>=6.1.0" "wheel>=0.46.2" && \
    # 驗證關鍵模組安裝成功
    python -c "import bcrypt; import jwt; print('bcrypt and jwt OK')"

# -----------------------------------------------------------------------------
# Stage 3: 最終基礎映像檔
# -----------------------------------------------------------------------------
FROM --platform=$TARGETPLATFORM python:3.11-slim-trixie AS final

# 標籤資訊
LABEL maintainer="network-dashboard@example.com" \
      version="2.2.2" \
      description="Network Dashboard Base Image - Python 3.11 + Dependencies"

# 設定環境變數
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    APP_HOME=/app \
    USE_MOCK=false \
    PATH="/opt/venv/bin:$PATH"

# 安裝執行時期必要的系統函式庫（僅 runtime，不含 dev）
RUN apt-get update && \
    # 升級所有套件以修復 CVE（Debian trixie 有更新的安全補丁）
    apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    # MySQL/MariaDB client runtime library
    libmariadb3 \
    # PostgreSQL client runtime library
    libpq5 \
    # 其他必要工具
    curl \
    tini \
    make \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    # 建立非 root 使用者
    && groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# 從 python-deps 階段複製虛擬環境
COPY --from=python-deps /opt/venv /opt/venv

WORKDIR $APP_HOME

# 複製應用程式核心檔案
COPY --chown=appuser:appgroup app/__init__.py app/
COPY --chown=appuser:appgroup app/core/ app/core/
COPY --chown=appuser:appgroup app/db/ app/db/
COPY --chown=appuser:appgroup app/api/ app/api/
COPY --chown=appuser:appgroup app/repositories/ app/repositories/
COPY --chown=appuser:appgroup app/services/ app/services/
COPY --chown=appuser:appgroup app/indicators/ app/indicators/
COPY --chown=appuser:appgroup app/main.py app/

# 複製 fetchers（含 configured.py，支援 mock + 真實 API 模式）
COPY --chown=appuser:appgroup app/fetchers/ app/fetchers/

# 複製 parsers（含所有 plugins，base image 可獨立運行 mock 模式）
COPY --chown=appuser:appgroup app/parsers/ app/parsers/

# 複製設定檔
COPY --chown=appuser:appgroup config/ config/

# 複製 Alembic 遷移檔
COPY --chown=appuser:appgroup alembic.ini ./
COPY --chown=appuser:appgroup alembic/ alembic/

# 複製測試資料（Mock 模式 & CSV 匯入範本）
COPY --chown=appuser:appgroup test_data/ test_data/

# 複製 Parser 驗證腳本 + Makefile（容器內 make fetch / parse）
COPY --chown=appuser:appgroup scripts/ scripts/
COPY --chown=appuser:appgroup Makefile ./

# 從前端建構階段複製靜態檔案
COPY --from=frontend-builder --chown=appuser:appgroup /app/frontend/dist /app/static

# 建立必要目錄
RUN mkdir -p /app/logs /app/data && \
    chown -R appuser:appgroup /app

# 複製啟動腳本
COPY --chown=appuser:appgroup docker/base/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# 切換到非 root 使用者
USER appuser

# 驗證關鍵模組可正常載入
RUN python -c "\
from app.core.config import settings; \
from app.fetchers.registry import FetcherRegistry; \
from app.parsers.registry import parser_registry; \
print('All modules loaded successfully')"

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 暴露埠號
EXPOSE 8000

# 使用 tini 作為 init 程序，透過 entrypoint.sh 自動跑 alembic migrate
ENTRYPOINT ["/usr/bin/tini", "--", "/app/entrypoint.sh"]

# 啟動指令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
