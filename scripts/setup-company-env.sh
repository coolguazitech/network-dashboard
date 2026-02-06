#!/bin/bash
# =============================================================================
# Network Dashboard 公司端環境設定腳本
#
# 使用方式：
#   chmod +x setup-company-env.sh
#   ./setup-company-env.sh
#
# 此腳本會：
#   1. 建立目錄結構
#   2. 建立 docker-compose.yaml
#   3. 建立 .env
#   4. 建立 Dockerfile.prod
#   5. 拉取 Base Image
#   6. 啟動服務
# =============================================================================

set -e

# 顏色定義
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Network Dashboard 環境設定${NC}"
echo -e "${GREEN}========================================${NC}"

# 設定變數
WORK_DIR="${1:-network_dashboard}"
BASE_IMAGE="coolguazi/network-dashboard-base:v1.0.2"

# 1. 建立目錄結構
echo -e "\n${YELLOW}[1/6] 建立目錄結構...${NC}"
mkdir -p "${WORK_DIR}/app/fetchers"
mkdir -p "${WORK_DIR}/app/parsers"
cd "${WORK_DIR}"
echo -e "${GREEN}✓ 目錄建立完成${NC}"

# 2. 建立 docker-compose.yaml
echo -e "\n${YELLOW}[2/6] 建立 docker-compose.yaml...${NC}"
cat > docker-compose.yaml << 'EOF'
services:
  # MariaDB 資料庫
  db:
    image: mariadb:10.11
    container_name: network_dashboard_db
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_ROOT_PASSWORD:-admin}
      MYSQL_DATABASE: ${DB_NAME:-network_dashboard}
      MYSQL_USER: ${DB_USER:-admin}
      MYSQL_PASSWORD: ${DB_PASSWORD:-admin}
    ports:
      - "${DB_PORT:-3306}:3306"
    volumes:
      - db_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    networks:
      - dashboard_net

  # phpMyAdmin
  phpmyadmin:
    image: phpmyadmin:5.2
    container_name: network_dashboard_pma
    restart: unless-stopped
    environment:
      PMA_HOST: db
      PMA_PORT: 3306
      UPLOAD_LIMIT: 64M
    ports:
      - "${PMA_PORT:-8080}:80"
    depends_on:
      db:
        condition: service_healthy
    networks:
      - dashboard_net

  # 主應用程式
  app:
    image: ${APP_IMAGE:-network-dashboard-base:alpine}
    container_name: network_dashboard_app
    restart: unless-stopped
    environment:
      DB_HOST: db
      DB_PORT: 3306
      DB_NAME: ${DB_NAME:-network_dashboard}
      DB_USER: ${DB_USER:-admin}
      DB_PASSWORD: ${DB_PASSWORD:-admin}
      APP_DEBUG: "true"
      APP_ENV: development
      USE_MOCK_API: ${USE_MOCK_API:-true}
      JWT_SECRET: ${JWT_SECRET:-dev-secret-change-in-production}
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 15s
    networks:
      - dashboard_net
    volumes:
      # 開發模式：掛載 fetcher 目錄
      - ./app/fetchers:/app/app/fetchers:ro

volumes:
  db_data:
    name: network_dashboard_db_data

networks:
  dashboard_net:
    name: network_dashboard_net
    driver: bridge
EOF
echo -e "${GREEN}✓ docker-compose.yaml 建立完成${NC}"

# 3. 建立 .env
echo -e "\n${YELLOW}[3/6] 建立 .env...${NC}"
cat > .env << 'EOF'
# 資料庫設定
DB_ROOT_PASSWORD=admin
DB_NAME=network_dashboard
DB_USER=admin
DB_PASSWORD=admin

# 應用程式設定
USE_MOCK_API=true
JWT_SECRET=dev-secret-change-in-production

# 映像檔設定（預設使用 base image）
# 建構 production image 後改成：
# APP_IMAGE=network-dashboard-prod:v1.0.0
EOF
echo -e "${GREEN}✓ .env 建立完成${NC}"

# 4. 建立 Dockerfile.prod
echo -e "\n${YELLOW}[4/6] 建立 Dockerfile.prod...${NC}"
cat > Dockerfile.prod << 'EOF'
# Production Image：Base Image + 你的 Fetcher 實作
FROM coolguazi/network-dashboard-base:v1.0.2

USER root

# 複製你的 Fetcher 實作
COPY app/fetchers/api_functions.py /app/app/fetchers/
COPY app/fetchers/implementations.py /app/app/fetchers/

# 選用：複製你的 Parser
# COPY app/parsers/your_parser.py /app/app/parsers/plugins/

RUN chown -R appuser:appgroup /app

USER appuser

RUN python -c "from app.fetchers.registry import FetcherRegistry; print('OK')"
EOF
echo -e "${GREEN}✓ Dockerfile.prod 建立完成${NC}"

# 5. 建立 fetcher 範本檔案
echo -e "\n${YELLOW}[5/6] 建立 Fetcher 範本...${NC}"

# api_functions.py 範本
cat > app/fetchers/api_functions.py << 'EOF'
"""
API 連接函式範本
請依照你的 API 修改此檔案
"""
import requests
from typing import Any, Dict

def fetch_from_api(url: str, params: Dict = None) -> Any:
    """通用 API 呼叫函式"""
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"API 呼叫失敗: {e}")
        return None

# 範例：FNA API
def fetch_ap_list() -> list:
    """取得 AP 列表"""
    # TODO: 修改成你的 API endpoint
    # data = fetch_from_api("http://your-fna-server/api/ap/list")
    # return data.get("items", [])
    return []

# 範例：DNA API
def fetch_switch_list() -> list:
    """取得 Switch 列表"""
    # TODO: 修改成你的 API endpoint
    # data = fetch_from_api("http://your-dna-server/api/switch/list")
    # return data.get("items", [])
    return []
EOF

# implementations.py 範本
cat > app/fetchers/implementations.py << 'EOF'
"""
Real Fetcher 實作範本
請依照你的需求修改此檔案
"""
from typing import List, Any

# TODO: 導入你的 base class 和 api functions
# from app.fetchers.base import BaseFetcher
# from app.fetchers.api_functions import fetch_ap_list, fetch_switch_list

# 範例 Fetcher 實作
# class RealAPFetcher(BaseFetcher):
#     """真實 AP Fetcher"""
#
#     async def fetch(self) -> List[Any]:
#         return fetch_ap_list()

print("implementations.py 已載入（範本模式）")
EOF

echo -e "${GREEN}✓ Fetcher 範本建立完成${NC}"
echo -e "  - app/fetchers/api_functions.py"
echo -e "  - app/fetchers/implementations.py"

# 6. 拉取並啟動
echo -e "\n${YELLOW}[6/6] 拉取映像檔並啟動服務...${NC}"
docker pull ${BASE_IMAGE}
docker tag ${BASE_IMAGE} network-dashboard-base:alpine

echo -e "\n${YELLOW}啟動服務...${NC}"
docker compose up -d

# 等待服務就緒
echo -e "\n${YELLOW}等待服務就緒...${NC}"
sleep 10

# 檢查狀態
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}設定完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e ""
echo -e "服務狀態："
docker compose ps
echo -e ""
echo -e "存取方式："
echo -e "  前端網頁：  ${GREEN}http://localhost:8000${NC}"
echo -e "  phpMyAdmin：${GREEN}http://localhost:8080${NC}"
echo -e "  帳號密碼：  ${GREEN}root / admin123${NC}"
echo -e ""
echo -e "開發流程："
echo -e "  1. 編輯 app/fetchers/api_functions.py"
echo -e "  2. 編輯 app/fetchers/implementations.py"
echo -e "  3. 重啟生效：docker compose restart app"
echo -e "  4. 查看 logs：docker compose logs -f app"
echo -e ""
echo -e "建構 Production Image："
echo -e "  docker build -f Dockerfile.prod -t network-dashboard-prod:v1.0.0 ."
echo -e ""
echo -e "切換到非 Mock 模式："
echo -e "  APP_IMAGE=network-dashboard-prod:v1.0.0 USE_MOCK_API=false docker compose up -d"
