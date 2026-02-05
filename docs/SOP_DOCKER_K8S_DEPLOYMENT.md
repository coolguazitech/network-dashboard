# Network Dashboard Docker & Kubernetes 部署 SOP

## 目錄

1. [概述](#1-概述)
2. [環境需求與前置準備](#2-環境需求與前置準備)
3. [MacBook 端作業：建構 x86 基礎映像檔](#3-macbook-端作業建構-x86-基礎映像檔)
4. [CVE 漏洞掃描與修復](#4-cve-漏洞掃描與修復)
5. [推送至 DockerHub](#5-推送至-dockerhub)
6. [公司端作業：整合 Fetcher/Parser](#6-公司端作業整合-fetcherparser)
7. [Kubernetes 部署設定](#7-kubernetes-部署設定)
8. [Vault 秘密管理整合](#8-vault-秘密管理整合)
9. [驗證與除錯](#9-驗證與除錯)
10. [附錄：常見問題排解](#10-附錄常見問題排解)

---

## 1. 概述

### 1.1 部署流程圖

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            MacBook (ARM M1/M2/M3)                           │
├─────────────────────────────────────────────────────────────────────────────┤
│  1. 設定 Docker buildx (QEMU 模擬 x86_64)                                    │
│  2. 建構基礎映像檔 (Python 3.11 + Node.js 18 + 依賴套件)                       │
│  3. Trivy 掃描 CVE，修復 Critical 等級漏洞                                    │
│  4. 推送至 DockerHub (公開 Repository)                                       │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            公司電腦 (x86_64)                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  5. 從 DockerHub 拉取基礎映像檔                                              │
│  6. 新增 Fetcher/Parser .py 檔案至映像檔                                     │
│  7. 建構最終映像檔，推送至公司私有 Registry                                   │
└──────────────────────────────────┬──────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            公司 Kubernetes 叢集                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  8. 部署 Deployment / Service / ConfigMap                                   │
│  9. Vault 注入敏感資訊 (DB 密碼、API Key 等)                                  │
│  10. 驗證服務正常運作                                                        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 映像檔命名規範

| 用途 | 映像檔名稱 | 說明 |
|------|-----------|------|
| 基礎映像檔 | `coolguazi/network-dashboard-base:v1.0.0` | Python 3.11 Alpine + 所有 pip/npm 依賴 |
| 最終映像檔 | `<company-registry>/network-dashboard:v1.0.0` | 基礎映像檔 + Fetcher/Parser 程式碼 |

### 1.3 已發布映像檔資訊

**DockerHub 位址**: https://hub.docker.com/r/coolguazi/network-dashboard-base

```bash
# 拉取映像檔
docker pull coolguazi/network-dashboard-base:v1.0.0
docker pull coolguazi/network-dashboard-base:latest
```

| 版本 | 基礎系統 | 架構 | CVE 狀態 | 發布日期 |
|------|---------|------|----------|----------|
| v1.0.0 | Alpine 3.23 | linux/amd64 | 0 CRITICAL | 2026-02-05 |

---

## 2. 環境需求與前置準備

### 2.1 MacBook 端需求

```bash
# 確認 Docker Desktop 已安裝且啟用
docker --version
# Docker version 24.0.0 或更高

# 確認 buildx 可用
docker buildx version
# github.com/docker/buildx v0.11.0 或更高

# 安裝 Trivy (CVE 掃描工具)
brew install trivy

# 確認 Trivy 版本
trivy --version
# Version: 0.50.0 或更高
```

### 2.2 公司端需求

```bash
# 確認 Docker 已安裝
docker --version

# 確認 kubectl 可連線至 K8s 叢集
kubectl cluster-info

# 確認 Vault CLI 可用 (選用，也可透過 K8s 整合)
vault --version
```

### 2.3 DockerHub 帳號準備

1. 前往 https://hub.docker.com/ 註冊帳號（若尚未有）
2. 建立 Repository：`network-dashboard-base`
3. 設定為 **Public**

```bash
# MacBook 端登入 DockerHub
docker login
# 輸入帳號密碼
```

---

## 3. MacBook 端作業：建構 x86 基礎映像檔

### 3.1 設定 Docker Buildx 多平台建構

```bash
# 建立支援多平台的 builder
docker buildx create --name multiarch-builder --driver docker-container --use

# 啟動 builder 並驗證平台支援
docker buildx inspect --bootstrap

# 確認輸出包含:
# Platforms: linux/amd64, linux/arm64, ...
```

### 3.2 建立專案目錄結構

```bash
cd /Users/coolguazi/Project/ClineTest/network_dashboard

# 建立 docker 目錄
mkdir -p docker/base
mkdir -p docker/production
```

### 3.3 建立基礎映像檔 Dockerfile

建立檔案 `docker/base/Dockerfile`:

```dockerfile
# =============================================================================
# 基礎映像檔：Python 3.11 + Node.js 18 + 依賴套件
# 平台：linux/amd64 (x86_64)
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Node.js 建構前端
# -----------------------------------------------------------------------------
FROM --platform=linux/amd64 node:18-bookworm-slim AS frontend-builder

WORKDIR /app/frontend

# 複製 package.json 先安裝依賴（利用 Docker 快取）
COPY frontend/package*.json ./

# 安裝 npm 依賴
RUN npm ci --only=production && \
    npm cache clean --force

# 複製前端原始碼並建構
COPY frontend/ ./
RUN npm run build

# -----------------------------------------------------------------------------
# Stage 2: Python 基礎環境
# -----------------------------------------------------------------------------
FROM --platform=linux/amd64 python:3.11-slim-bookworm AS python-base

# 設定環境變數
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安裝系統依賴並清理
RUN apt-get update && apt-get install -y --no-install-recommends \
    # 資料庫連線所需
    default-libmysqlclient-dev \
    libpq-dev \
    # 編譯所需
    build-essential \
    # 網路工具 (除錯用)
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# -----------------------------------------------------------------------------
# Stage 3: Python 依賴安裝
# -----------------------------------------------------------------------------
FROM python-base AS python-deps

WORKDIR /app

# 複製依賴定義檔
COPY pyproject.toml ./

# 安裝 pip 工具和專案依賴
RUN pip install --upgrade pip setuptools wheel && \
    pip install . && \
    pip cache purge

# -----------------------------------------------------------------------------
# Stage 4: 最終基礎映像檔
# -----------------------------------------------------------------------------
FROM --platform=linux/amd64 python:3.11-slim-bookworm AS final

# 標籤資訊
LABEL maintainer="your-email@example.com" \
      version="1.0.0" \
      description="Network Dashboard Base Image"

# 設定環境變數
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    APP_HOME=/app \
    # 預設為非 Mock 模式
    USE_MOCK=false

# 安裝執行時期必要的系統函式庫
RUN apt-get update && apt-get install -y --no-install-recommends \
    default-libmysqlclient-dev \
    libpq-dev \
    curl \
    tini \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean \
    # 建立非 root 使用者
    && groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# 從 python-deps 階段複製已安裝的 Python 套件
COPY --from=python-deps /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=python-deps /usr/local/bin /usr/local/bin

WORKDIR $APP_HOME

# 複製應用程式核心檔案（不含 fetchers/parsers 的實作）
# 注意：fetchers 和 parsers 的實作會在公司端加入
COPY --chown=appuser:appgroup app/__init__.py app/
COPY --chown=appuser:appgroup app/core/ app/core/
COPY --chown=appuser:appgroup app/db/ app/db/
COPY --chown=appuser:appgroup app/api/ app/api/
COPY --chown=appuser:appgroup app/schemas/ app/schemas/
COPY --chown=appuser:appgroup app/repositories/ app/repositories/
COPY --chown=appuser:appgroup app/services/ app/services/
COPY --chown=appuser:appgroup app/indicators/ app/indicators/
COPY --chown=appuser:appgroup app/main.py app/

# 複製設定檔
COPY --chown=appuser:appgroup config/ config/

# 從前端建構階段複製靜態檔案
COPY --from=frontend-builder --chown=appuser:appgroup /app/frontend/dist /app/static

# 建立必要目錄
RUN mkdir -p /app/logs /app/data && \
    chown -R appuser:appgroup /app

# 切換到非 root 使用者
USER appuser

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 暴露埠號
EXPOSE 8000

# 使用 tini 作為 init 程序
ENTRYPOINT ["/usr/bin/tini", "--"]

# 啟動指令
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### 3.4 建構 x86_64 映像檔

```bash
cd /Users/coolguazi/Project/ClineTest/network_dashboard

# 建構 x86_64 映像檔並載入本地
docker buildx build \
    --platform linux/amd64 \
    --file docker/base/Dockerfile \
    --tag network-dashboard-base:v1.0.0-local \
    --load \
    .

# 驗證映像檔架構
docker inspect network-dashboard-base:v1.0.0-local | grep Architecture
# 預期輸出: "Architecture": "amd64"
```

---

## 4. CVE 漏洞掃描與修復

### 4.1 執行 Trivy 掃描

```bash
# 完整掃描（包含 OS 套件和應用程式依賴）
trivy image \
    --severity CRITICAL,HIGH \
    --format table \
    network-dashboard-base:v1.0.0-local

# 只掃描 CRITICAL 等級
trivy image \
    --severity CRITICAL \
    --format table \
    network-dashboard-base:v1.0.0-local

# 輸出 JSON 格式（用於自動化處理）
trivy image \
    --severity CRITICAL \
    --format json \
    --output trivy-report.json \
    network-dashboard-base:v1.0.0-local
```

### 4.2 常見 CVE 修復策略

#### 4.2.1 作業系統套件 CVE

在 Dockerfile 中加入明確的套件版本升級:

```dockerfile
# 在安裝系統依賴後，升級有漏洞的套件
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    # 明確指定安全版本
    openssl=3.0.11-1~deb12u2 \
    libssl3=3.0.11-1~deb12u2 \
    && rm -rf /var/lib/apt/lists/*
```

#### 4.2.2 Python 套件 CVE

1. 更新 `pyproject.toml` 中的版本約束:

```toml
[project]
dependencies = [
    # 指定已修復 CVE 的版本
    "cryptography>=42.0.5",  # 修復 CVE-2024-XXXXX
    "httpx>=0.27.0",         # 修復 CVE-2024-XXXXX
    # ... 其他依賴
]
```

2. 或建立 `constraints.txt` 強制覆蓋:

```bash
# constraints.txt
cryptography==42.0.5
urllib3==2.2.0
certifi==2024.2.2
```

在 Dockerfile 中使用:

```dockerfile
COPY constraints.txt ./
RUN pip install -c constraints.txt .
```

#### 4.2.3 Node.js 套件 CVE

```bash
# 在前端目錄執行
cd frontend

# 檢查漏洞
npm audit

# 自動修復
npm audit fix

# 強制修復（可能有破壞性變更）
npm audit fix --force
```

### 4.3 迭代修復流程

```bash
# 1. 掃描 → 2. 修復 → 3. 重建 → 4. 再掃描

# Step 1: 初次掃描
trivy image --severity CRITICAL network-dashboard-base:v1.0.0-local > scan-result-1.txt

# Step 2: 根據報告修改 Dockerfile 或依賴版本
# (手動編輯)

# Step 3: 重新建構
docker buildx build \
    --platform linux/amd64 \
    --file docker/base/Dockerfile \
    --tag network-dashboard-base:v1.0.0-local \
    --load \
    --no-cache \
    .

# Step 4: 再次掃描確認
trivy image --severity CRITICAL network-dashboard-base:v1.0.0-local > scan-result-2.txt

# 比對結果
diff scan-result-1.txt scan-result-2.txt
```

### 4.4 驗證零 Critical CVE

```bash
# 確認無 CRITICAL 漏洞
CRITICAL_COUNT=$(trivy image --severity CRITICAL --format json network-dashboard-base:v1.0.0-local | jq '.Results[].Vulnerabilities | length' | awk '{sum+=$1} END {print sum}')

if [ "$CRITICAL_COUNT" -eq 0 ] || [ -z "$CRITICAL_COUNT" ]; then
    echo "✅ 無 CRITICAL 等級漏洞，可以推送"
else
    echo "❌ 仍有 $CRITICAL_COUNT 個 CRITICAL 漏洞需要修復"
    exit 1
fi
```

---

## 5. 推送至 DockerHub

### 5.1 標記映像檔

```bash
# 替換 <your-dockerhub-username> 為你的 DockerHub 帳號
export DOCKERHUB_USER="your-dockerhub-username"

# 標記映像檔
docker tag network-dashboard-base:v1.0.0-local $DOCKERHUB_USER/network-dashboard-base:v1.0.0
docker tag network-dashboard-base:v1.0.0-local $DOCKERHUB_USER/network-dashboard-base:latest
```

### 5.2 推送至 DockerHub

```bash
# 登入 DockerHub
docker login

# 推送映像檔
docker push $DOCKERHUB_USER/network-dashboard-base:v1.0.0
docker push $DOCKERHUB_USER/network-dashboard-base:latest

# 驗證推送成功
docker pull $DOCKERHUB_USER/network-dashboard-base:v1.0.0
```

### 5.3 設定 Repository 為公開

1. 登入 DockerHub 網頁介面
2. 進入 `network-dashboard-base` Repository
3. Settings → Visibility → **Public**
4. 確認儲存

---

## 6. 公司端作業：整合 Fetcher/Parser

### 6.1 拉取基礎映像檔

```bash
# 替換為實際的 DockerHub 帳號
export DOCKERHUB_USER="your-dockerhub-username"

# 拉取基礎映像檔
docker pull $DOCKERHUB_USER/network-dashboard-base:v1.0.0

# 驗證架構
docker inspect $DOCKERHUB_USER/network-dashboard-base:v1.0.0 | grep Architecture
# 預期輸出: "Architecture": "amd64"
```

### 6.2 準備 Fetcher/Parser 檔案

確保以下檔案結構存在於公司電腦:

```
company-code/
├── fetchers/
│   ├── __init__.py
│   ├── base.py              # 基礎類別
│   ├── registry.py          # Fetcher 註冊
│   ├── implementations.py   # 真實 Fetcher 實作
│   ├── api_functions.py     # API 呼叫函式
│   └── mock.py              # Mock Fetcher (選用)
├── parsers/
│   ├── __init__.py
│   ├── registry.py
│   ├── protocols.py
│   ├── client_parsers.py
│   └── plugins/
│       ├── __init__.py
│       ├── hpe_*.py
│       ├── cisco_ios_*.py
│       └── cisco_nxos_*.py
└── Dockerfile.production
```

### 6.3 建立生產映像檔 Dockerfile

建立檔案 `Dockerfile.production`:

```dockerfile
# =============================================================================
# 生產映像檔：基礎映像檔 + Fetcher/Parser 實作
# =============================================================================

# 使用從 DockerHub 拉取的基礎映像檔
ARG DOCKERHUB_USER=your-dockerhub-username
ARG BASE_VERSION=v1.0.0
FROM ${DOCKERHUB_USER}/network-dashboard-base:${BASE_VERSION}

# 標籤資訊
LABEL maintainer="your-email@company.com" \
      version="1.0.0" \
      description="Network Dashboard Production Image with Fetchers/Parsers"

# 切換到 root 以複製檔案
USER root

# 複製 Fetcher 實作
COPY --chown=appuser:appgroup fetchers/ /app/app/fetchers/

# 複製 Parser 實作
COPY --chown=appuser:appgroup parsers/ /app/app/parsers/

# 複製其他依賴檔案 (如有)
# COPY --chown=appuser:appgroup other_modules/ /app/app/other_modules/

# 確保權限正確
RUN chown -R appuser:appgroup /app

# 切換回非 root 使用者
USER appuser

# 驗證模組可正常載入
RUN python -c "from app.fetchers import registry; from app.parsers import registry; print('Modules loaded successfully')"

# 繼承基礎映像檔的 ENTRYPOINT 和 CMD
```

### 6.4 建構生產映像檔

```bash
# 設定變數
export DOCKERHUB_USER="your-dockerhub-username"
export COMPANY_REGISTRY="your-company-registry.com"
export APP_VERSION="1.0.0"

# 建構生產映像檔
docker build \
    --build-arg DOCKERHUB_USER=$DOCKERHUB_USER \
    --build-arg BASE_VERSION=v1.0.0 \
    --file Dockerfile.production \
    --tag $COMPANY_REGISTRY/network-dashboard:v$APP_VERSION \
    --tag $COMPANY_REGISTRY/network-dashboard:latest \
    .

# 驗證映像檔
docker run --rm $COMPANY_REGISTRY/network-dashboard:v$APP_VERSION python -c "
from app.fetchers.registry import get_fetcher
from app.parsers.registry import get_parser
print('Fetcher registry OK')
print('Parser registry OK')
"
```

### 6.5 推送至公司私有 Registry

```bash
# 登入公司 Registry
docker login $COMPANY_REGISTRY

# 推送映像檔
docker push $COMPANY_REGISTRY/network-dashboard:v$APP_VERSION
docker push $COMPANY_REGISTRY/network-dashboard:latest
```

---

## 7. Kubernetes 部署設定

### 7.1 建立 Namespace

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: network-dashboard
  labels:
    app: network-dashboard
    environment: production
```

```bash
kubectl apply -f k8s/namespace.yaml
```

### 7.2 ConfigMap（非敏感設定）

```yaml
# k8s/configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: network-dashboard-config
  namespace: network-dashboard
data:
  # 應用程式設定
  APP_ENV: "production"
  LOG_LEVEL: "INFO"
  USE_MOCK: "false"

  # 資料庫設定（非敏感）
  DB_HOST: "mariadb.database.svc.cluster.local"
  DB_PORT: "3306"
  DB_NAME: "network_dashboard"

  # API 設定
  API_TIMEOUT: "30"
  MOCK_PING_CONVERGE_TIME: "600"

  # 排程設定
  SCHEDULER_ENABLED: "true"
```

```bash
kubectl apply -f k8s/configmap.yaml
```

### 7.3 Deployment

```yaml
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: network-dashboard
  namespace: network-dashboard
  labels:
    app: network-dashboard
spec:
  replicas: 2
  selector:
    matchLabels:
      app: network-dashboard
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: network-dashboard
      annotations:
        # Vault Agent Injector 註解（見 Section 8）
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/role: "network-dashboard"
        vault.hashicorp.com/agent-inject-secret-db-creds: "secret/data/network-dashboard/db"
        vault.hashicorp.com/agent-inject-template-db-creds: |
          {{- with secret "secret/data/network-dashboard/db" -}}
          export DB_USER="{{ .Data.data.username }}"
          export DB_PASSWORD="{{ .Data.data.password }}"
          {{- end }}
    spec:
      serviceAccountName: network-dashboard
      securityContext:
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
      containers:
        - name: network-dashboard
          image: your-company-registry.com/network-dashboard:v1.0.0
          imagePullPolicy: Always
          ports:
            - containerPort: 8000
              protocol: TCP
          envFrom:
            - configMapRef:
                name: network-dashboard-config
          # Vault 注入的環境變數會透過 source 載入
          command:
            - /bin/bash
            - -c
            - |
              if [ -f /vault/secrets/db-creds ]; then
                source /vault/secrets/db-creds
              fi
              exec uvicorn app.main:app --host 0.0.0.0 --port 8000
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 30
            timeoutSeconds: 5
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
            timeoutSeconds: 3
            failureThreshold: 3
          volumeMounts:
            - name: config-volume
              mountPath: /app/config
              readOnly: true
      volumes:
        - name: config-volume
          configMap:
            name: network-dashboard-config
      imagePullSecrets:
        - name: company-registry-secret
```

### 7.4 Service

```yaml
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: network-dashboard
  namespace: network-dashboard
  labels:
    app: network-dashboard
spec:
  type: ClusterIP
  ports:
    - port: 80
      targetPort: 8000
      protocol: TCP
      name: http
  selector:
    app: network-dashboard
```

### 7.5 Ingress（選用）

```yaml
# k8s/ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: network-dashboard
  namespace: network-dashboard
  annotations:
    kubernetes.io/ingress.class: nginx
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
spec:
  tls:
    - hosts:
        - network-dashboard.your-company.com
      secretName: network-dashboard-tls
  rules:
    - host: network-dashboard.your-company.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: network-dashboard
                port:
                  number: 80
```

### 7.6 部署至 Kubernetes

```bash
# 建立 image pull secret（若需要）
kubectl create secret docker-registry company-registry-secret \
    --docker-server=your-company-registry.com \
    --docker-username=your-username \
    --docker-password=your-password \
    --namespace=network-dashboard

# 部署所有資源
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml

# 檢查部署狀態
kubectl get pods -n network-dashboard -w
kubectl get svc -n network-dashboard
```

---

## 8. Vault 秘密管理整合

### 8.1 Vault 設定概述

```
┌─────────────────────────────────────────────────────────────────┐
│                         HashiCorp Vault                         │
├─────────────────────────────────────────────────────────────────┤
│  secret/data/network-dashboard/                                 │
│  ├── db                                                         │
│  │   ├── username: "dashboard_user"                             │
│  │   └── password: "super-secret-password"                      │
│  ├── api                                                        │
│  │   ├── dna_api_key: "xxx"                                     │
│  │   ├── fna_api_key: "xxx"                                     │
│  │   └── gnms_api_key: "xxx"                                    │
│  └── jwt                                                        │
│      └── secret_key: "jwt-signing-key"                          │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 在 Vault 中建立 Secret

```bash
# 登入 Vault
vault login

# 啟用 KV secrets engine（若尚未啟用）
vault secrets enable -path=secret kv-v2

# 建立資料庫認證
vault kv put secret/network-dashboard/db \
    username="dashboard_user" \
    password="your-secure-password"

# 建立 API 金鑰
vault kv put secret/network-dashboard/api \
    dna_api_key="your-dna-api-key" \
    fna_api_key="your-fna-api-key" \
    gnms_api_key="your-gnms-api-key"

# 建立 JWT 秘鑰
vault kv put secret/network-dashboard/jwt \
    secret_key="your-jwt-secret-key"

# 驗證
vault kv get secret/network-dashboard/db
```

### 8.3 設定 Kubernetes 認證

```bash
# 啟用 Kubernetes 認證方法
vault auth enable kubernetes

# 設定 Kubernetes 認證
vault write auth/kubernetes/config \
    kubernetes_host="https://$KUBERNETES_PORT_443_TCP_ADDR:443" \
    token_reviewer_jwt="$(cat /var/run/secrets/kubernetes.io/serviceaccount/token)" \
    kubernetes_ca_cert=@/var/run/secrets/kubernetes.io/serviceaccount/ca.crt \
    issuer="https://kubernetes.default.svc.cluster.local"
```

### 8.4 建立 Vault Policy

```bash
# 建立 policy 檔案
cat <<EOF > network-dashboard-policy.hcl
path "secret/data/network-dashboard/*" {
  capabilities = ["read"]
}
EOF

# 寫入 Vault
vault policy write network-dashboard network-dashboard-policy.hcl
```

### 8.5 建立 Vault Role

```bash
vault write auth/kubernetes/role/network-dashboard \
    bound_service_account_names=network-dashboard \
    bound_service_account_namespaces=network-dashboard \
    policies=network-dashboard \
    ttl=24h
```

### 8.6 建立 Kubernetes ServiceAccount

```yaml
# k8s/serviceaccount.yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: network-dashboard
  namespace: network-dashboard
  labels:
    app: network-dashboard
```

```bash
kubectl apply -f k8s/serviceaccount.yaml
```

### 8.7 完整的 Deployment（含 Vault 整合）

```yaml
# k8s/deployment-with-vault.yaml
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
      annotations:
        # ===== Vault Agent Injector 設定 =====
        vault.hashicorp.com/agent-inject: "true"
        vault.hashicorp.com/agent-inject-status: "update"
        vault.hashicorp.com/role: "network-dashboard"

        # 資料庫認證
        vault.hashicorp.com/agent-inject-secret-db: "secret/data/network-dashboard/db"
        vault.hashicorp.com/agent-inject-template-db: |
          {{- with secret "secret/data/network-dashboard/db" -}}
          DB_USER={{ .Data.data.username }}
          DB_PASSWORD={{ .Data.data.password }}
          {{- end }}

        # API 金鑰
        vault.hashicorp.com/agent-inject-secret-api: "secret/data/network-dashboard/api"
        vault.hashicorp.com/agent-inject-template-api: |
          {{- with secret "secret/data/network-dashboard/api" -}}
          DNA_API_KEY={{ .Data.data.dna_api_key }}
          FNA_API_KEY={{ .Data.data.fna_api_key }}
          GNMS_API_KEY={{ .Data.data.gnms_api_key }}
          {{- end }}

        # JWT 秘鑰
        vault.hashicorp.com/agent-inject-secret-jwt: "secret/data/network-dashboard/jwt"
        vault.hashicorp.com/agent-inject-template-jwt: |
          {{- with secret "secret/data/network-dashboard/jwt" -}}
          JWT_SECRET_KEY={{ .Data.data.secret_key }}
          {{- end }}
    spec:
      serviceAccountName: network-dashboard
      securityContext:
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
      containers:
        - name: network-dashboard
          image: your-company-registry.com/network-dashboard:v1.0.0
          ports:
            - containerPort: 8000
          envFrom:
            - configMapRef:
                name: network-dashboard-config
          command:
            - /bin/bash
            - -c
            - |
              # 載入 Vault 注入的秘密
              if [ -f /vault/secrets/db ]; then
                export $(cat /vault/secrets/db | xargs)
              fi
              if [ -f /vault/secrets/api ]; then
                export $(cat /vault/secrets/api | xargs)
              fi
              if [ -f /vault/secrets/jwt ]; then
                export $(cat /vault/secrets/jwt | xargs)
              fi
              # 啟動應用程式
              exec uvicorn app.main:app --host 0.0.0.0 --port 8000
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 15
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 10
      imagePullSecrets:
        - name: company-registry-secret
```

---

## 9. 驗證與除錯

### 9.1 檢查 Pod 狀態

```bash
# 查看所有 Pod
kubectl get pods -n network-dashboard

# 查看 Pod 詳細資訊
kubectl describe pod <pod-name> -n network-dashboard

# 查看 Pod 日誌
kubectl logs <pod-name> -n network-dashboard

# 即時追蹤日誌
kubectl logs -f <pod-name> -n network-dashboard
```

### 9.2 驗證 Vault 注入

```bash
# 進入 Pod 檢查秘密檔案
kubectl exec -it <pod-name> -n network-dashboard -- /bin/bash

# 在 Pod 內執行
ls -la /vault/secrets/
cat /vault/secrets/db
cat /vault/secrets/api
```

### 9.3 測試 API 連通性

```bash
# Port forward 到本地
kubectl port-forward svc/network-dashboard 8080:80 -n network-dashboard

# 測試 health endpoint
curl http://localhost:8080/health

# 測試 API
curl http://localhost:8080/api/v1/maintenance
```

### 9.4 驗證資料庫連線

```bash
# 進入 Pod
kubectl exec -it <pod-name> -n network-dashboard -- /bin/bash

# 測試資料庫連線
python -c "
from app.db.base import engine
from sqlalchemy import text
with engine.connect() as conn:
    result = conn.execute(text('SELECT 1'))
    print('Database connection OK:', result.fetchone())
"
```

---

## 10. 附錄：常見問題排解

### 10.1 Docker Buildx 跨平台建構問題

**問題**: `exec format error` 或 QEMU 模擬失敗

**解決方案**:

```bash
# 重新安裝 QEMU 模擬器
docker run --rm --privileged multiarch/qemu-user-static --reset -p yes

# 重新建立 builder
docker buildx rm multiarch-builder
docker buildx create --name multiarch-builder --driver docker-container --use
docker buildx inspect --bootstrap
```

### 10.2 CVE 掃描結果不一致

**問題**: 本地掃描和 CI/CD 掃描結果不同

**解決方案**:

```bash
# 更新 Trivy 資料庫
trivy image --download-db-only

# 使用固定版本的資料庫
trivy image --skip-db-update --db-repository ghcr.io/aquasecurity/trivy-db:2
```

### 10.3 Vault Agent 無法注入秘密

**問題**: Pod 啟動但 `/vault/secrets/` 目錄是空的

**檢查步驟**:

```bash
# 1. 確認 Vault Agent Injector 已安裝
kubectl get pods -n vault

# 2. 檢查 ServiceAccount
kubectl get sa network-dashboard -n network-dashboard

# 3. 檢查 Vault Role 綁定
vault read auth/kubernetes/role/network-dashboard

# 4. 查看 Vault Agent Sidecar 日誌
kubectl logs <pod-name> -c vault-agent -n network-dashboard
```

### 10.4 映像檔拉取失敗

**問題**: `ImagePullBackOff` 或認證錯誤

**解決方案**:

```bash
# 檢查 secret 是否正確
kubectl get secret company-registry-secret -n network-dashboard -o yaml

# 重新建立 secret
kubectl delete secret company-registry-secret -n network-dashboard
kubectl create secret docker-registry company-registry-secret \
    --docker-server=your-company-registry.com \
    --docker-username=your-username \
    --docker-password=your-password \
    --namespace=network-dashboard
```

### 10.5 健康檢查失敗

**問題**: Pod 反覆重啟，`Liveness probe failed`

**檢查步驟**:

```bash
# 1. 確認 /health endpoint 存在
kubectl exec -it <pod-name> -n network-dashboard -- curl http://localhost:8000/health

# 2. 檢查應用程式日誌
kubectl logs <pod-name> -n network-dashboard --previous

# 3. 增加 initialDelaySeconds
# 編輯 deployment，將 initialDelaySeconds 從 10 增加到 30
```

---

## 快速參考卡

### MacBook 端指令

```bash
# 建構 x86 映像檔
docker buildx build --platform linux/amd64 -f docker/base/Dockerfile -t network-dashboard-base:v1.0.0-local --load .

# CVE 掃描
trivy image --severity CRITICAL network-dashboard-base:v1.0.0-local

# 推送到 DockerHub
docker tag network-dashboard-base:v1.0.0-local $DOCKERHUB_USER/network-dashboard-base:v1.0.0
docker push $DOCKERHUB_USER/network-dashboard-base:v1.0.0
```

### 公司端指令

```bash
# 拉取基礎映像檔
docker pull $DOCKERHUB_USER/network-dashboard-base:v1.0.0

# 建構生產映像檔
docker build -f Dockerfile.production -t $COMPANY_REGISTRY/network-dashboard:v1.0.0 .

# 推送到公司 Registry
docker push $COMPANY_REGISTRY/network-dashboard:v1.0.0

# 部署到 K8s
kubectl apply -f k8s/
```

### Vault 指令

```bash
# 建立秘密
vault kv put secret/network-dashboard/db username=xxx password=xxx

# 讀取秘密
vault kv get secret/network-dashboard/db

# 建立 Role
vault write auth/kubernetes/role/network-dashboard \
    bound_service_account_names=network-dashboard \
    bound_service_account_namespaces=network-dashboard \
    policies=network-dashboard \
    ttl=24h
```

---

**文件版本**: 1.0.0
**最後更新**: 2026-02-05
**維護者**: Network Dashboard Team
