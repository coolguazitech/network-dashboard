#!/bin/bash
# =============================================================================
# 部署至 Kubernetes 腳本
# =============================================================================

set -euo pipefail

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 預設值
NAMESPACE="${NAMESPACE:-network-dashboard}"
IMAGE_TAG="${IMAGE_TAG:-v1.0.0}"
COMPANY_REGISTRY="${COMPANY_REGISTRY:-}"
DRY_RUN="${DRY_RUN:-false}"

# 使用說明
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -n, --namespace NAMESPACE    Kubernetes Namespace (預設: network-dashboard)"
    echo "  -t, --tag TAG                映像檔版本標籤 (預設: v1.0.0)"
    echo "  -r, --registry REGISTRY      公司 Registry 位址 (必填)"
    echo "  --dry-run                    僅顯示將執行的操作，不實際執行"
    echo "  -h, --help                   顯示此說明"
    echo ""
    echo "Examples:"
    echo "  $0 -r registry.company.com -t v1.0.0"
    echo "  $0 -r registry.company.com -t v1.0.0 --dry-run"
}

# 解析參數
while [[ $# -gt 0 ]]; do
    case $1 in
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -t|--tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        -r|--registry)
            COMPANY_REGISTRY="$2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="true"
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
if [ -z "$COMPANY_REGISTRY" ]; then
    echo -e "${RED}錯誤: 請指定公司 Registry 位址 (-r REGISTRY)${NC}"
    usage
    exit 1
fi

# 檢查 kubectl
if ! command -v kubectl &> /dev/null; then
    echo -e "${RED}錯誤: 請先安裝 kubectl${NC}"
    exit 1
fi

# 切換到專案根目錄
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Network Dashboard Kubernetes 部署${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Namespace: $NAMESPACE"
echo "映像檔: ${COMPANY_REGISTRY}/network-dashboard:${IMAGE_TAG}"
echo "Dry Run: $DRY_RUN"
echo ""

# kubectl 參數
KUBECTL_ARGS=""
if [ "$DRY_RUN" = "true" ]; then
    KUBECTL_ARGS="--dry-run=client"
    echo -e "${YELLOW}[DRY RUN 模式] 以下操作不會實際執行${NC}"
    echo ""
fi

# Step 1: 建立 Namespace
echo -e "${YELLOW}[Step 1/5] 建立 Namespace...${NC}"
kubectl apply -f k8s/namespace.yaml $KUBECTL_ARGS

# Step 2: 建立 ServiceAccount
echo -e "${YELLOW}[Step 2/5] 建立 ServiceAccount...${NC}"
kubectl apply -f k8s/serviceaccount.yaml $KUBECTL_ARGS

# Step 3: 建立 ConfigMap
echo -e "${YELLOW}[Step 3/5] 建立 ConfigMap...${NC}"
kubectl apply -f k8s/configmap.yaml $KUBECTL_ARGS

# Step 4: 更新 Deployment 中的映像檔標籤並部署
echo -e "${YELLOW}[Step 4/5] 部署 Deployment...${NC}"

# 使用 sed 替換映像檔位址（臨時檔案）
TEMP_DEPLOYMENT=$(mktemp)
sed "s|your-company-registry.com/network-dashboard:v1.0.0|${COMPANY_REGISTRY}/network-dashboard:${IMAGE_TAG}|g" \
    k8s/deployment.yaml > "$TEMP_DEPLOYMENT"

kubectl apply -f "$TEMP_DEPLOYMENT" $KUBECTL_ARGS
rm -f "$TEMP_DEPLOYMENT"

# Step 5: 建立 Service
echo -e "${YELLOW}[Step 5/5] 建立 Service...${NC}"
kubectl apply -f k8s/service.yaml $KUBECTL_ARGS

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  部署完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

if [ "$DRY_RUN" = "false" ]; then
    echo "檢查部署狀態："
    echo ""
    kubectl get pods -n "$NAMESPACE"
    echo ""
    kubectl get svc -n "$NAMESPACE"
    echo ""
    echo "監控部署進度："
    echo "  kubectl get pods -n $NAMESPACE -w"
    echo ""
    echo "查看日誌："
    echo "  kubectl logs -f deployment/network-dashboard -n $NAMESPACE"
fi
