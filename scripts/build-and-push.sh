#!/usr/bin/env bash
# =============================================================================
# 一鍵 Build → CVE Scan → Tag → Push
#
# 使用方式：
#   bash scripts/build-and-push.sh          # 預設 v1.1.0
#   bash scripts/build-and-push.sh v1.2.0   # 指定版本
# =============================================================================
set -euo pipefail

VERSION="${1:-v1.1.0}"
DOCKERHUB_USER="coolguazi"
IMAGE_NAME="network-dashboard-base"
FULL_TAG="${DOCKERHUB_USER}/${IMAGE_NAME}:${VERSION}"

echo "=========================================="
echo "  Building ${FULL_TAG}"
echo "=========================================="

# ----- Step 1: Build -----
echo ""
echo "=== Step 1: Build base image ==="
docker buildx build --platform linux/amd64 \
    -f docker/base/Dockerfile \
    -t "${FULL_TAG}" \
    --load .

echo "Build completed: ${FULL_TAG}"

# ----- Step 2: CVE Scan -----
echo ""
echo "=== Step 2: CVE Scan (Trivy) ==="
REPORT_FILE="trivy-report-${VERSION}.txt"

# 使用 Docker 运行 Trivy（无需本地安装）
# --exit-code 0: 只扫描 CRITICAL，如果有则失败
docker run --rm \
    -v /var/run/docker.sock:/var/run/docker.sock \
    aquasec/trivy:latest image \
    --severity CRITICAL \
    --exit-code 1 \
    "${FULL_TAG}" > /dev/null

# 生成完整报告（包含 HIGH）
docker run --rm \
    -v /var/run/docker.sock:/var/run/docker.sock \
    aquasec/trivy:latest image \
    --severity HIGH,CRITICAL \
    --exit-code 0 \
    "${FULL_TAG}" | tee "${REPORT_FILE}"

echo ""
echo "CVE report saved to: ${REPORT_FILE}"
echo "✅ No CRITICAL vulnerabilities found!"

# ----- Step 3: Tag & Push -----
echo ""
echo "=== Step 3: Tag & Push ==="
docker push "${FULL_TAG}"

docker tag "${FULL_TAG}" "${DOCKERHUB_USER}/${IMAGE_NAME}:latest"
docker push "${DOCKERHUB_USER}/${IMAGE_NAME}:latest"

echo ""
echo "=========================================="
echo "  DONE"
echo "  Pushed: ${FULL_TAG}"
echo "  Pushed: ${DOCKERHUB_USER}/${IMAGE_NAME}:latest"
echo "=========================================="
