# Network Dashboard 部署 SOP

## 目錄
- [公司端快速開始](#公司端快速開始)
- [MacBook 端：建構並推送 Image](#macbook-端建構並推送-image)
- [附錄：必要檔案內容](#附錄必要檔案內容)

---

# 公司端快速開始

從開發 Fetcher 到看到前端畫面的完整流程。

## Step 1：建立 Python 開發環境

在開發機器（只有 Python 3.11）：

```bash
mkdir -p fetcher_dev/app/fetchers
cd fetcher_dev
python3.11 -m venv venv
source venv/bin/activate
pip install requests
```

## Step 2：開發 Fetcher

建立 `app/fetchers/api_functions.py`：

```python
"""你的 API 連接函式"""
import requests

def fetch_ap_list():
    response = requests.get("http://your-api/ap/list")
    return response.json()

def fetch_switch_list():
    response = requests.get("http://your-api/switch/list")
    return response.json()
```

建立 `app/fetchers/implementations.py`：

```python
"""你的 Fetcher 實作"""
from .api_functions import fetch_ap_list, fetch_switch_list

class RealAPFetcher:
    async def fetch(self):
        return fetch_ap_list()

class RealSwitchFetcher:
    async def fetch(self):
        return fetch_switch_list()
```

## Step 3：測試 Fetcher

```bash
python -c "from app.fetchers.api_functions import fetch_ap_list; print(fetch_ap_list())"
```

## Step 4：部署到有 Docker 的機器

把 `app/fetchers/` 目錄帶到有 Docker 的機器，建立以下結構：

```
network_dashboard/
├── app/fetchers/
│   ├── api_functions.py
│   └── implementations.py
├── docker-compose.yaml    # 從附錄複製
└── Dockerfile.prod        # 從附錄複製
```

## Step 5：建構並啟動

```bash
cd network_dashboard

# 建構 Production Image
docker build -f Dockerfile.prod -t network-dashboard-prod:v1.0.0 .

# 啟動
docker compose up -d

# 等待約 30 秒
```

## Step 6：開啟瀏覽器

- 網址：http://localhost:8000
- 帳號：`root`
- 密碼：`admin123`

---

# MacBook 端：建構並推送 Image

## 前置需求

- Docker Desktop（已安裝 buildx）
- Node.js 18+

## 建構

```bash
cd network_dashboard

docker buildx build --platform linux/amd64 \
  -f docker/base/Dockerfile.alpine \
  -t network-dashboard-base:v1.0.2 \
  --load .
```

## 推送到 DockerHub

```bash
docker login
docker tag network-dashboard-base:v1.0.2 coolguazi/network-dashboard-base:v1.0.2
docker push coolguazi/network-dashboard-base:v1.0.2
```

---

# 附錄：必要檔案內容

## docker-compose.yaml

```yaml
services:
  db:
    image: mariadb:10.11
    environment:
      MYSQL_ROOT_PASSWORD: admin
      MYSQL_DATABASE: network_dashboard
      MYSQL_USER: admin
      MYSQL_PASSWORD: admin
    volumes:
      - db_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  app:
    image: network-dashboard-prod:v1.0.0
    environment:
      DB_HOST: db
      DB_PORT: 3306
      DB_NAME: network_dashboard
      DB_USER: admin
      DB_PASSWORD: admin
      USE_MOCK_API: "false"
      JWT_SECRET: your-secret-key-change-this
    ports:
      - "8000:8000"
    depends_on:
      db:
        condition: service_healthy

volumes:
  db_data:
```

## Dockerfile.prod

```dockerfile
FROM coolguazi/network-dashboard-base:v1.0.2
USER root
COPY app/fetchers/api_functions.py /app/app/fetchers/
COPY app/fetchers/implementations.py /app/app/fetchers/
RUN chown -R appuser:appgroup /app
USER appuser
```

---

# 疑難排解

| 問題 | 解決方法 |
|------|----------|
| 前端打不開 | 確認 `docker compose ps` 顯示 app 為 healthy |
| 資料庫連線失敗 | 等待 30 秒讓 MariaDB 初始化完成 |
| Container 一直重啟 | 執行 `docker compose logs app` 查看錯誤 |
| 模組找不到 | 確認使用最新的 base image `v1.0.2` |

---

# 環境變數說明

| 變數 | 說明 | 預設值 |
|------|------|--------|
| `USE_MOCK_API` | true=假資料，false=真實 API | true |
| `JWT_SECRET` | JWT 密鑰（可自訂） | - |
| `DB_PASSWORD` | 資料庫密碼（可自訂） | admin |
