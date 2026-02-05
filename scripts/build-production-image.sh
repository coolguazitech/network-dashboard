#!/bin/bash
# =============================================================================
# 建構生產映像檔腳本
# 用於公司端將 Fetcher/Parser 加入基礎映像檔
# =============================================================================

set -euo pipefail

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 預設值
VERSION="${VERSION:-v1.0.0}"
BASE_VERSION="${BASE_VERSION:-v1.0.0}"
DOCKERHUB_USER="${DOCKERHUB_USER:-}"
COMPANY_REGISTRY="${COMPANY_REGISTRY:-}"
PUSH_IMAGE="${PUSH_IMAGE:-false}"

# 使用說明
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -v, --version VERSION        生產映像檔版本 (預設: v1.0.0)"
    echo "  -b, --base-version VERSION   基礎映像檔版本 (預設: v1.0.0)"
    echo "  -u, --dockerhub-user USER    DockerHub 帳號 (必填)"
    echo "  -r, --registry REGISTRY      公司 Registry 位址 (必填，用於推送)"
    echo "  -p, --push                   建構後推送至公司 Registry"
    echo "  -h, --help                   顯示此說明"
    echo ""
    echo "Examples:"
    echo "  $0 -u myuser -b v1.0.0                         # 僅建構本地映像檔"
    echo "  $0 -u myuser -b v1.0.0 -r registry.company.com -p  # 建構並推送"
}

# 解析參數
while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--version)
            VERSION="$2"
            shift 2
            ;;
        -b|--base-version)
            BASE_VERSION="$2"
            shift 2
            ;;
        -u|--dockerhub-user)
            DOCKERHUB_USER="$2"
            shift 2
            ;;
        -r|--registry)
            COMPANY_REGISTRY="$2"
            shift 2
            ;;
        -p|--push)
            PUSH_IMAGE="true"
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}未知參數: $1${NC}"
            usage
            exit 1
            ;;
    esac
done

# 參數檢查
if [ -z "$DOCKERHUB_USER" ]; then
    echo -e "${RED}錯誤: 請指定 DockerHub 帳號 (-u USERNAME)${NC}"
    usage
    exit 1
fi

# 切換到專案根目錄
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Network Dashboard 生產映像檔建構${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "生產版本: $VERSION"
echo "基礎版本: $BASE_VERSION"
echo "DockerHub 帳號: $DOCKERHUB_USER"
echo "公司 Registry: ${COMPANY_REGISTRY:-未指定}"
echo "推送: $PUSH_IMAGE"
echo ""

# Step 1: 拉取基礎映像檔
echo -e "${YELLOW}[Step 1/4] 拉取基礎映像檔...${NC}"
BASE_IMAGE="${DOCKERHUB_USER}/network-dashboard-base:${BASE_VERSION}"

docker pull "$BASE_IMAGE"
echo -e "${GREEN}基礎映像檔拉取完成: $BASE_IMAGE${NC}"

# Step 2: 驗證架構
echo -e "${YELLOW}[Step 2/4] 驗證映像檔架構...${NC}"
ARCH=$(docker inspect "$BASE_IMAGE" | grep -o '"Architecture": "[^"]*"' | head -1)
echo "基礎映像檔架構: $ARCH"

# Step 3: 建構生產映像檔
echo -e "${YELLOW}[Step 3/4] 建構生產映像檔...${NC}"
LOCAL_TAG="network-dashboard:${VERSION}-local"

docker build \
    --build-arg DOCKERHUB_USER="$DOCKERHUB_USER" \
    --build-arg BASE_VERSION="$BASE_VERSION" \
    --file docker/production/Dockerfile \
    --tag "$LOCAL_TAG" \
    .

echo -e "${GREEN}生產映像檔建構完成: $LOCAL_TAG${NC}"

# 驗證模組載入
echo "驗證模組載入..."
docker run --rm "$LOCAL_TAG" python -c "
from app.fetchers.registry import FetcherRegistry
from app.parsers.registry import get_parser
print('All modules loaded successfully')
"

# Step 4: 推送至公司 Registry
if [ "$PUSH_IMAGE" = "true" ]; then
    echo -e "${YELLOW}[Step 4/4] 推送至公司 Registry...${NC}"

    if [ -z "$COMPANY_REGISTRY" ]; then
        echo -e "${RED}錯誤: 請指定公司 Registry 位址 (-r REGISTRY)${NC}"
        exit 1
    fi

    REMOTE_TAG="${COMPANY_REGISTRY}/network-dashboard:${VERSION}"
    LATEST_TAG="${COMPANY_REGISTRY}/network-dashboard:latest"

    # 標記映像檔
    docker tag "$LOCAL_TAG" "$REMOTE_TAG"
    docker tag "$LOCAL_TAG" "$LATEST_TAG"

    # 推送
    echo "推送 $REMOTE_TAG..."
    docker push "$REMOTE_TAG"

    echo "推送 $LATEST_TAG..."
    docker push "$LATEST_TAG"

    echo -e "${GREEN}推送完成！${NC}"
else
    echo -e "${YELLOW}[Step 4/4] 跳過推送（使用 -p 參數啟用推送）${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  建構完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "本地映像檔: $LOCAL_TAG"
if [ "$PUSH_IMAGE" = "true" ] && [ -n "$COMPANY_REGISTRY" ]; then
    echo "遠端映像檔: ${COMPANY_REGISTRY}/network-dashboard:${VERSION}"
fi
