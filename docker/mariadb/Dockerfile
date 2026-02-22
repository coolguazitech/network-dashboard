# =============================================================================
# MariaDB 10.11 with patched gosu (Go 1.24.13)
# Fixes CVE-2025-68121 (crypto/tls session resumption)
# =============================================================================

# Stage 1: Rebuild gosu with Go 1.24.13
FROM golang:1.24.13-bookworm AS gosu-builder

ARG GOSU_VERSION=1.19

RUN set -eux; \
    git clone --branch "${GOSU_VERSION}" --depth 1 \
      https://github.com/tianon/gosu.git /build/gosu; \
    cd /build/gosu; \
    CGO_ENABLED=0 GOARCH=amd64 GOOS=linux \
      go build -v -trimpath -ldflags '-d -w -s' -o /usr/local/bin/gosu .; \
    /usr/local/bin/gosu --version

# Stage 2: Drop-in replace gosu in MariaDB
FROM mariadb:10.11

COPY --from=gosu-builder /usr/local/bin/gosu /usr/local/bin/gosu
RUN chmod +x /usr/local/bin/gosu && gosu nobody true
