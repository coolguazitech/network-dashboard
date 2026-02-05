#!/bin/bash
# =============================================================================
# Vault 秘密設定腳本
# 用於設定 Vault 中的秘密和 Kubernetes 認證
# =============================================================================

set -euo pipefail

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 預設值
NAMESPACE="${NAMESPACE:-network-dashboard}"
VAULT_ADDR="${VAULT_ADDR:-}"
DRY_RUN="${DRY_RUN:-false}"

# 使用說明
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -a, --vault-addr ADDRESS    Vault 伺服器位址 (預設: 使用 VAULT_ADDR 環境變數)"
    echo "  -n, --namespace NAMESPACE   Kubernetes Namespace (預設: network-dashboard)"
    echo "  --dry-run                   僅顯示將執行的操作，不實際執行"
    echo "  -h, --help                  顯示此說明"
    echo ""
    echo "此腳本會引導您設定："
    echo "  1. Vault 中的秘密路徑"
    echo "  2. Kubernetes 認證方法"
    echo "  3. Vault Policy 和 Role"
    echo ""
    echo "執行前請確保："
    echo "  - 已登入 Vault (vault login)"
    echo "  - 有權限建立秘密和設定認證"
}

# 解析參數
while [[ $# -gt 0 ]]; do
    case $1 in
        -a|--vault-addr)
            VAULT_ADDR="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
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

# 檢查 vault CLI
if ! command -v vault &> /dev/null; then
    echo -e "${RED}錯誤: 請先安裝 Vault CLI${NC}"
    echo "安裝指令: brew install vault"
    exit 1
fi

# 設定 VAULT_ADDR
if [ -n "$VAULT_ADDR" ]; then
    export VAULT_ADDR
fi

if [ -z "${VAULT_ADDR:-}" ]; then
    echo -e "${RED}錯誤: 請設定 VAULT_ADDR 環境變數或使用 -a 參數${NC}"
    exit 1
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Network Dashboard Vault 設定${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Vault Address: $VAULT_ADDR"
echo "Namespace: $NAMESPACE"
echo "Dry Run: $DRY_RUN"
echo ""

# 執行或顯示指令的函數
run_cmd() {
    local cmd="$1"
    if [ "$DRY_RUN" = "true" ]; then
        echo -e "${YELLOW}[DRY RUN]${NC} $cmd"
    else
        echo -e "${GREEN}執行:${NC} $cmd"
        eval "$cmd"
    fi
}

# Step 1: 啟用 KV secrets engine
echo -e "${YELLOW}[Step 1/6] 檢查/啟用 KV secrets engine...${NC}"
if vault secrets list | grep -q "^secret/"; then
    echo "KV secrets engine 已啟用"
else
    run_cmd "vault secrets enable -path=secret kv-v2"
fi

# Step 2: 建立資料庫秘密
echo ""
echo -e "${YELLOW}[Step 2/6] 建立資料庫認證秘密...${NC}"
if [ "$DRY_RUN" = "false" ]; then
    read -p "資料庫使用者名稱 [dashboard_user]: " DB_USER
    DB_USER="${DB_USER:-dashboard_user}"

    read -sp "資料庫密碼: " DB_PASSWORD
    echo ""

    if [ -z "$DB_PASSWORD" ]; then
        echo -e "${RED}錯誤: 密碼不能為空${NC}"
        exit 1
    fi

    vault kv put secret/network-dashboard/db \
        username="$DB_USER" \
        password="$DB_PASSWORD"

    echo -e "${GREEN}資料庫秘密已建立${NC}"
else
    echo -e "${YELLOW}[DRY RUN]${NC} vault kv put secret/network-dashboard/db username=<USER> password=<PASSWORD>"
fi

# Step 3: 建立 API 金鑰秘密
echo ""
echo -e "${YELLOW}[Step 3/6] 建立 API 金鑰秘密...${NC}"
if [ "$DRY_RUN" = "false" ]; then
    read -sp "DNA API Key (留空跳過): " DNA_KEY
    echo ""
    read -sp "FNA API Key (留空跳過): " FNA_KEY
    echo ""
    read -sp "GNMS API Key (留空跳過): " GNMS_KEY
    echo ""

    vault kv put secret/network-dashboard/api \
        dna_api_key="${DNA_KEY:-placeholder}" \
        fna_api_key="${FNA_KEY:-placeholder}" \
        gnms_api_key="${GNMS_KEY:-placeholder}"

    echo -e "${GREEN}API 金鑰秘密已建立${NC}"
else
    echo -e "${YELLOW}[DRY RUN]${NC} vault kv put secret/network-dashboard/api dna_api_key=<KEY> fna_api_key=<KEY> gnms_api_key=<KEY>"
fi

# Step 4: 建立 JWT 秘鑰
echo ""
echo -e "${YELLOW}[Step 4/6] 建立 JWT 秘鑰...${NC}"
if [ "$DRY_RUN" = "false" ]; then
    # 自動生成隨機秘鑰
    JWT_SECRET=$(openssl rand -base64 32)

    vault kv put secret/network-dashboard/jwt \
        secret_key="$JWT_SECRET"

    echo -e "${GREEN}JWT 秘鑰已建立（自動生成）${NC}"
else
    echo -e "${YELLOW}[DRY RUN]${NC} vault kv put secret/network-dashboard/jwt secret_key=<RANDOM_KEY>"
fi

# Step 5: 建立 Vault Policy
echo ""
echo -e "${YELLOW}[Step 5/6] 建立 Vault Policy...${NC}"

POLICY_CONTENT='path "secret/data/network-dashboard/*" {
  capabilities = ["read"]
}'

if [ "$DRY_RUN" = "false" ]; then
    echo "$POLICY_CONTENT" | vault policy write network-dashboard -
    echo -e "${GREEN}Policy 已建立${NC}"
else
    echo -e "${YELLOW}[DRY RUN]${NC} vault policy write network-dashboard - <<EOF"
    echo "$POLICY_CONTENT"
    echo "EOF"
fi

# Step 6: 設定 Kubernetes 認證
echo ""
echo -e "${YELLOW}[Step 6/6] 設定 Kubernetes 認證...${NC}"
echo ""
echo "請確認以下事項："
echo "  1. Kubernetes 叢集已啟用 Vault Agent Injector"
echo "  2. 已在 Vault 中啟用 Kubernetes auth method"
echo ""

if [ "$DRY_RUN" = "false" ]; then
    read -p "是否設定 Kubernetes Role? (y/n) [y]: " SETUP_K8S_ROLE
    SETUP_K8S_ROLE="${SETUP_K8S_ROLE:-y}"

    if [[ "$SETUP_K8S_ROLE" =~ ^[Yy]$ ]]; then
        # 檢查 Kubernetes auth 是否已啟用
        if ! vault auth list | grep -q "kubernetes/"; then
            echo "啟用 Kubernetes auth..."
            vault auth enable kubernetes
        fi

        # 建立 Role
        vault write auth/kubernetes/role/network-dashboard \
            bound_service_account_names=network-dashboard \
            bound_service_account_namespaces="$NAMESPACE" \
            policies=network-dashboard \
            ttl=24h

        echo -e "${GREEN}Kubernetes Role 已建立${NC}"
    fi
else
    echo -e "${YELLOW}[DRY RUN]${NC} vault auth enable kubernetes"
    echo -e "${YELLOW}[DRY RUN]${NC} vault write auth/kubernetes/role/network-dashboard \\"
    echo "    bound_service_account_names=network-dashboard \\"
    echo "    bound_service_account_namespaces=$NAMESPACE \\"
    echo "    policies=network-dashboard \\"
    echo "    ttl=24h"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Vault 設定完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "已設定的秘密路徑："
echo "  - secret/data/network-dashboard/db"
echo "  - secret/data/network-dashboard/api"
echo "  - secret/data/network-dashboard/jwt"
echo ""
echo "驗證秘密："
echo "  vault kv get secret/network-dashboard/db"
echo ""
