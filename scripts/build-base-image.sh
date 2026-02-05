#!/bin/bash
# =============================================================================
# 建構 x86_64 基礎映像檔腳本
# 用於 MacBook (ARM) 上建構 x86_64 映像檔
# =============================================================================

set -euo pipefail

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 預設值
VERSION="${VERSION:-v1.0.0}"
DOCKERHUB_USER="${DOCKERHUB_USER:-}"
SKIP_CVE_SCAN="${SKIP_CVE_SCAN:-false}"
PUSH_IMAGE="${PUSH_IMAGE:-false}"

# 使用說明
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -v, --version VERSION    映像檔版本 (預設: v1.0.0)"
    echo "  -u, --user USERNAME      DockerHub 帳號 (必填，用於推送)"
    echo "  -p, --push               建構後推送至 DockerHub"
    echo "  --skip-cve               跳過 CVE 掃描"
    echo "  -h, --help               顯示此說明"
    echo ""
    echo "Examples:"
    echo "  $0 -v v1.0.0                     # 僅建構本地映像檔"
    echo "  $0 -v v1.0.0 -u myuser -p        # 建構並推送至 DockerHub"
    echo "  $0 -v v1.0.0 --skip-cve          # 建構但跳過 CVE 掃描"
}

# 解析參數
while [[ $# -gt 0 ]]; do
    case $1 in
        -v|--version)
            VERSION="$2"
            shift 2
            ;;
        -u|--user)
            DOCKERHUB_USER="$2"
            shift 2
            ;;
        -p|--push)
            PUSH_IMAGE="true"
            shift
            ;;
        --skip-cve)
            SKIP_CVE_SCAN="true"
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

# 檢查 Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}錯誤: 請先安裝 Docker${NC}"
    exit 1
fi

# 檢查 buildx
if ! docker buildx version &> /dev/null; then
    echo -e "${RED}錯誤: 請確認 Docker Buildx 已安裝${NC}"
    exit 1
fi

# 切換到專案根目錄
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Network Dashboard 基礎映像檔建構${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "版本: $VERSION"
echo "推送: $PUSH_IMAGE"
echo "CVE 掃描: $([ "$SKIP_CVE_SCAN" = "true" ] && echo "跳過" || echo "啟用")"
echo ""

# Step 1: 設定 buildx
echo -e "${YELLOW}[Step 1/5] 設定 Docker Buildx...${NC}"
if ! docker buildx inspect multiarch-builder &> /dev/null; then
    docker buildx create --name multiarch-builder --driver docker-container --use
fi
docker buildx use multiarch-builder
docker buildx inspect --bootstrap

# Step 2: 建構映像檔
echo -e "${YELLOW}[Step 2/5] 建構 x86_64 映像檔...${NC}"
LOCAL_TAG="network-dashboard-base:${VERSION}-local"

docker buildx build \
    --platform linux/amd64 \
    --file docker/base/Dockerfile \
    --tag "$LOCAL_TAG" \
    --load \
    .

echo -e "${GREEN}映像檔建構完成: $LOCAL_TAG${NC}"

# Step 3: 驗證架構
echo -e "${YELLOW}[Step 3/5] 驗證映像檔架構...${NC}"
ARCH=$(docker inspect "$LOCAL_TAG" | grep -o '"Architecture": "[^"]*"' | head -1)
echo "映像檔架構: $ARCH"

if [[ "$ARCH" != *"amd64"* ]]; then
    echo -e "${RED}錯誤: 映像檔架構不正確，預期為 amd64${NC}"
    exit 1
fi

# Step 4: CVE 掃描
if [ "$SKIP_CVE_SCAN" = "false" ]; then
    echo -e "${YELLOW}[Step 4/5] 執行 CVE 掃描...${NC}"

    if ! command -v trivy &> /dev/null; then
        echo -e "${RED}警告: Trivy 未安裝，跳過 CVE 掃描${NC}"
        echo "安裝指令: brew install trivy"
    else
        echo "掃描 CRITICAL 等級漏洞..."
        trivy image --severity CRITICAL "$LOCAL_TAG"

        # 檢查是否有 CRITICAL 漏洞
        CRITICAL_COUNT=$(trivy image --severity CRITICAL --format json "$LOCAL_TAG" 2>/dev/null | \
            python3 -c "import sys,json; data=json.load(sys.stdin); print(sum(len(r.get('Vulnerabilities', []) or []) for r in data.get('Results', [])))" 2>/dev/null || echo "0")

        if [ "$CRITICAL_COUNT" != "0" ] && [ -n "$CRITICAL_COUNT" ]; then
            echo -e "${RED}警告: 發現 $CRITICAL_COUNT 個 CRITICAL 等級漏洞${NC}"
            echo "請修復漏洞後再推送至 DockerHub"

            if [ "$PUSH_IMAGE" = "true" ]; then
                echo -e "${RED}因存在 CRITICAL 漏洞，中止推送${NC}"
                exit 1
            fi
        else
            echo -e "${GREEN}無 CRITICAL 等級漏洞${NC}"
        fi
    fi
else
    echo -e "${YELLOW}[Step 4/5] 跳過 CVE 掃描${NC}"
fi

# Step 5: 推送至 DockerHub
if [ "$PUSH_IMAGE" = "true" ]; then
    echo -e "${YELLOW}[Step 5/5] 推送至 DockerHub...${NC}"

    if [ -z "$DOCKERHUB_USER" ]; then
        echo -e "${RED}錯誤: 請指定 DockerHub 帳號 (-u USERNAME)${NC}"
        exit 1
    fi

    REMOTE_TAG="${DOCKERHUB_USER}/network-dashboard-base:${VERSION}"
    LATEST_TAG="${DOCKERHUB_USER}/network-dashboard-base:latest"

    # 標記映像檔
    docker tag "$LOCAL_TAG" "$REMOTE_TAG"
    docker tag "$LOCAL_TAG" "$LATEST_TAG"

    # 推送
    echo "推送 $REMOTE_TAG..."
    docker push "$REMOTE_TAG"

    echo "推送 $LATEST_TAG..."
    docker push "$LATEST_TAG"

    echo -e "${GREEN}推送完成！${NC}"
    echo "映像檔位址: docker.io/$REMOTE_TAG"
else
    echo -e "${YELLOW}[Step 5/5] 跳過推送（使用 -p 參數啟用推送）${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  建構完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "本地映像檔: $LOCAL_TAG"
if [ "$PUSH_IMAGE" = "true" ] && [ -n "$DOCKERHUB_USER" ]; then
    echo "遠端映像檔: docker.io/${DOCKERHUB_USER}/network-dashboard-base:${VERSION}"
fi
