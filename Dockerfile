# syntax=docker/dockerfile:1.7

FROM node:22.22.0-alpine AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM debian:bookworm-slim AS sevenzip-build
ARG TARGETARCH
ARG SEVENZIP_VERSION=26.03
ARG SEVENZIP_X64_SHA256=dc99eff5008f1ab79bd7084c68513701547a808a89502bf4133683535ab3c695
ARG SEVENZIP_ARM64_SHA256=2389ba20e4d8295e8709c20b6263b69bd1ec4972fe38a04ad7a1badbf595b996
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl xz-utils \
    && rm -rf /var/lib/apt/lists/* \
    && case "${TARGETARCH}" in \
         amd64) archive="7z2603-linux-x64.tar.xz"; checksum="${SEVENZIP_X64_SHA256}" ;; \
         arm64) archive="7z2603-linux-arm64.tar.xz"; checksum="${SEVENZIP_ARM64_SHA256}" ;; \
         *) echo "Unsupported Docker architecture: ${TARGETARCH}" >&2; exit 1 ;; \
       esac \
    && curl --fail --location --proto '=https' --tlsv1.2 \
      "https://github.com/ip7z/7zip/releases/download/${SEVENZIP_VERSION}/${archive}" -o /tmp/7zip.tar.xz \
    && echo "${checksum}  /tmp/7zip.tar.xz" | sha256sum --check --strict \
    && mkdir /tmp/7zip \
    && tar -xJf /tmp/7zip.tar.xz -C /tmp/7zip \
    && install -m 0755 /tmp/7zip/7zz /out-7zz

FROM python:3.14.4-slim AS sqlite-build
ARG SQLITE_AUTOCONF=3530400
ARG SQLITE_SHA3=454e45f61c6bd75b7420e7190732dea03ce6639c63ada47bbc592f67fc340338
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /tmp/sqlite
RUN curl --fail --location --proto '=https' --tlsv1.2 \
      "https://sqlite.org/2026/sqlite-autoconf-${SQLITE_AUTOCONF}.tar.gz" -o sqlite.tar.gz \
    && python -c "import hashlib; p='sqlite.tar.gz'; actual=hashlib.sha3_256(open(p,'rb').read()).hexdigest(); expected='${SQLITE_SHA3}'; assert actual == expected, (actual, expected)" \
    && tar -xzf sqlite.tar.gz --strip-components=1 \
    && ./configure --prefix=/usr/local --disable-static --enable-shared \
    && make -j"$(nproc)" \
    && make install

FROM python:3.14.4-slim AS runtime
LABEL org.opencontainers.image.title="Feature Control Center" \
      org.opencontainers.image.version="2.1.2"

ENV TZ=UTC

COPY --from=sqlite-build /usr/local/lib/libsqlite3.so* /usr/local/lib/
COPY --from=sqlite-build /usr/local/bin/sqlite3 /usr/local/bin/sqlite3
COPY --from=sevenzip-build /out-7zz /usr/local/bin/7zz
COPY docs/third-party/7zip-license.txt /usr/share/doc/7zip/LICENSE.txt
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && ldconfig \
    && python -c "import sqlite3; assert tuple(map(int, sqlite3.sqlite_version.split('.'))) >= (3, 51, 3), sqlite3.sqlite_version" \
    && 7zz i >/dev/null \
    && groupadd --gid 10001 fcc \
    && useradd --uid 10001 --gid fcc --create-home --shell /usr/sbin/nologin fcc \
    && groupadd --gid 10002 fcc-script \
    && useradd --uid 10002 --gid fcc-script --create-home --shell /usr/sbin/nologin fcc-script \
    && install -d -o fcc -g fcc -m 0700 /data

WORKDIR /opt/fcc
COPY backend/ ./backend/
COPY --from=frontend-build /build/frontend/dist/ ./backend/app/web/static/
RUN python -m pip install --no-cache-dir ./backend \
    && find /opt/fcc -type d -name __pycache__ -prune -exec rm -rf {} +

USER root
EXPOSE 8080
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health/live', timeout=3).read()"
CMD ["fcc-launcher", "--data-dir", "/data", "--host", "0.0.0.0", "--port", "8080", "--public-url", "http://localhost:8080"]
