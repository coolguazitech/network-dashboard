# Network Dashboard 部署 SOP

本文件詳述如何在 MacBook 上建構 x86_64 Docker Image，並部署到公司 K8s 環境。

## 目錄
1. [前置需求](#1-前置需求)
2. [MacBook 端：建構 Base Image](#2-macbook-端建構-base-image)
3. [本地測試驗證](#3-本地測試驗證)
4. [推送到 DockerHub](#4-推送到-dockerhub)
5. [公司端：建構 Production Image](#5-公司端建構-production-image)
6. [K8s 部署](#6-k8s-部署)
7. [疑難排解](#7-疑難排解)

---

## 1. 前置需求

### MacBook 端
- Docker Desktop（已安裝 buildx）
- Node.js 18+（用於建構前端）
- Trivy（CVE 掃描工具）：`brew install trivy`

### 公司端
- Docker
- Python 3.11（用於本地開發/測試）
- K8s 叢集存取權限
- Vault 存取權限（用於 secrets）

---

## 2. MacBook 端：建構 Base Image

### 2.1 使用 Alpine Base（推薦，無 Critical CVE）

```bash
cd network_dashboard

# 建構 x86_64 Alpine 映像檔
docker buildx build --platform linux/amd64 \
  -f docker/base/Dockerfile.alpine \
  -t network-dashboard-base:v1.0.0 \
  --load .
```

### 2.2 CVE 掃描驗證

```bash
# 掃描 Critical 和 High 漏洞
trivy image --severity CRITICAL,HIGH network-dashboard-base:v1.0.0

# 預期結果：0 CRITICAL，僅少量 HIGH（build-time dependencies）
```

### 2.3 映像檔標籤說明

| 標籤 | 說明 |
|------|------|
| `v1.0.0` | 正式版本號（推 DockerHub 用）|
| `dev` | 本地開發測試用 |
| `alpine` | Alpine-based（無 Critical CVE）|

---

## 3. 本地測試驗證

### 3.1 啟動本地環境

```bash
# 確保映像檔已建構為 :alpine 標籤
docker tag network-dashboard-base:v1.0.0 network-dashboard-base:alpine

# 啟動服務
docker compose -f docker-compose.dev.yaml up -d

# 查看狀態
docker compose -f docker-compose.dev.yaml ps
```

### 3.2 驗證功能

```bash
# 健康檢查
curl http://localhost:8000/health
# 預期：{"status":"ok","version":"0.3.0","scheduler_running":true,...}

# 前端頁面
open http://localhost:8000
# 預期：看到登入頁面
```

### 3.3 測試登入

預設帳號密碼：
- 帳號：`root`
- 密碼：`admin123`

### 3.4 停止服務

```bash
docker compose -f docker-compose.dev.yaml down
```

---

## 4. 推送到 DockerHub

### 4.1 登入 DockerHub

```bash
docker login
# 輸入帳號密碼
```

### 4.2 標籤並推送

```bash
DOCKERHUB_USER=coolguazi  # 改成你的帳號
VERSION=v1.0.0

# 標籤
docker tag network-dashboard-base:v1.0.0 \
  ${DOCKERHUB_USER}/network-dashboard-base:${VERSION}

docker tag network-dashboard-base:v1.0.0 \
  ${DOCKERHUB_USER}/network-dashboard-base:latest

# 推送
docker push ${DOCKERHUB_USER}/network-dashboard-base:${VERSION}
docker push ${DOCKERHUB_USER}/network-dashboard-base:latest
```

### 4.3 設定 Repository 為公開

1. 登入 https://hub.docker.com
2. 進入 `network-dashboard-base` repository
3. Settings → Visibility → 設為 Public

---

## 5. 公司端：建構 Production Image

### 5.1 拉取 Base Image

```bash
docker pull coolguazi/network-dashboard-base:v1.0.0
```

### 5.2 準備 Fetcher/Parser 檔案

確保以下檔案已準備好：
```
app/fetchers/
├── api_functions.py      # 連接 FNA/DNA/GNMS API 的實作
└── implementations.py    # Real Fetcher 實作

app/parsers/
├── client_parsers.py     # Client 資料解析器
└── plugins/              # 各廠牌 parser（已包含在 base image）
```

### 5.3 建構 Production Image

```bash
# 使用 production Dockerfile
docker build \
  --build-arg DOCKERHUB_USER=coolguazi \
  --build-arg BASE_VERSION=v1.0.0 \
  -f docker/production/Dockerfile \
  -t your-registry/network-dashboard:v1.0.0 \
  .
```

### 5.4 推送到公司 Registry

```bash
docker push your-registry/network-dashboard:v1.0.0
```

---

## 6. K8s 部署

### 6.1 建立 Namespace

```bash
kubectl create namespace network-dashboard
```

### 6.2 建立 Secrets（從 Vault）

```yaml
# secrets.yaml
apiVersion: v1
kind: Secret
metadata:
  name: network-dashboard-secrets
  namespace: network-dashboard
type: Opaque
stringData:
  DB_HOST: "your-db-host"
  DB_PORT: "3306"
  DB_NAME: "network_dashboard"
  DB_USER: "app_user"
  DB_PASSWORD: "from-vault"
  JWT_SECRET: "from-vault"
  EXTERNAL_API_SERVER: "http://your-api-server:8001"
```

### 6.3 部署設定參考

將 `docker-compose.dev.yaml` 轉換為 K8s manifests：

```yaml
# deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: network-dashboard
  namespace: network-dashboard
spec:
  replicas: 2
  selector:
    matchLabels:
      app: network-dashboard
  template:
    metadata:
      labels:
        app: network-dashboard
    spec:
      containers:
      - name: app
        image: your-registry/network-dashboard:v1.0.0
        ports:
        - containerPort: 8000
        envFrom:
        - secretRef:
            name: network-dashboard-secrets
        env:
        - name: USE_MOCK_API
          value: "false"
        - name: APP_ENV
          value: "production"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 30
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 10
```

---

## 7. 疑難排解

### 7.1 bcrypt / jwt 模組找不到

**原因**：Dockerfile 未正確安裝 Python 依賴

**解決**：
- 確認使用最新的 `docker/base/Dockerfile.alpine`
- 檢查 build log 是否有 `bcrypt and jwt OK` 訊息

### 7.2 前端無法存取（只看到 API）

**原因**：靜態檔案未正確複製到 `/app/static`

**檢查方式**：
```bash
docker run --rm network-dashboard-base:alpine ls -la /app/static/
# 應該看到 index.html 和 assets/ 目錄
```

### 7.3 資料庫連線失敗

**原因**：環境變數未正確設定

**檢查方式**：
```bash
docker compose -f docker-compose.dev.yaml logs app | grep -i error
```

**解決**：確認 `.env` 中的 `DB_HOST` 設定正確（Docker 內應為 `db`）

### 7.4 CVE 掃描問題

**Alpine (推薦)**：
- 0 CRITICAL CVE
- 3 HIGH CVE（build-time dependencies，可忽略）

**Debian**：
- 2 CRITICAL CVE（OS-level，無法修復）
- 建議使用 Alpine 版本

---

## 附錄：環境變數說明

| 變數名稱 | 說明 | 預設值 |
|----------|------|--------|
| `DB_HOST` | 資料庫主機 | localhost |
| `DB_PORT` | 資料庫埠號 | 3306 |
| `DB_NAME` | 資料庫名稱 | network_dashboard |
| `DB_USER` | 資料庫使用者 | admin |
| `DB_PASSWORD` | 資料庫密碼 | admin |
| `USE_MOCK_API` | 是否使用 Mock API | true |
| `EXTERNAL_API_SERVER` | 外部 API 伺服器 | http://localhost:8001 |
| `JWT_SECRET` | JWT 簽章密鑰 | (需設定強密碼) |
| `COLLECTION_INTERVAL_SECONDS` | 資料採集間隔 | 600 |
| `CHECKPOINT_INTERVAL_MINUTES` | Checkpoint 間隔 | 60 |

---

## 快速指令參考

```bash
# === MacBook 端 ===
# 建構 Alpine image（推薦）
docker buildx build --platform linux/amd64 -f docker/base/Dockerfile.alpine -t network-dashboard-base:v1.0.0 --load .

# CVE 掃描
trivy image --severity CRITICAL network-dashboard-base:v1.0.0

# 本地測試
docker tag network-dashboard-base:v1.0.0 network-dashboard-base:alpine
docker compose -f docker-compose.dev.yaml up -d
curl http://localhost:8000/health

# 推送 DockerHub
docker tag network-dashboard-base:v1.0.0 coolguazi/network-dashboard-base:v1.0.0
docker push coolguazi/network-dashboard-base:v1.0.0

# === 公司端 ===
# 拉取 base image
docker pull coolguazi/network-dashboard-base:v1.0.0

# 建構 production image
docker build --build-arg DOCKERHUB_USER=coolguazi --build-arg BASE_VERSION=v1.0.0 -f docker/production/Dockerfile -t your-registry/network-dashboard:v1.0.0 .
```
