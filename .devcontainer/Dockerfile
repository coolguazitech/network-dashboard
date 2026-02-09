# =============================================================================
# Dev Container for Network Dashboard
# 支援 AMD64 (Intel/Windows) 和 ARM64 (Apple Silicon)
# =============================================================================

FROM mcr.microsoft.com/devcontainers/python:1-3.11-bookworm

# 移除 base image 中過期的 Yarn GPG key
RUN rm -f /etc/apt/sources.list.d/yarn.list

# 安裝其他開發工具（Node.js 由 devcontainer feature 安裝）
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Database clients
    default-mysql-client \
    # 開發工具
    make \
    curl \
    jq \
    && rm -rf /var/lib/apt/lists/*

# 設定工作目錄
WORKDIR /workspace

# 預設使用 vscode 用戶
USER vscode
