# syntax=docker/dockerfile:1.7
#
# Vectora - ONE image, ONE container: nginx (reverse proxy) + Next.js UI + FastAPI API + Qdrant,
# supervised by supervisord under tini. NVIDIA NIM stays an external API.
#
#   docker build -t vectora .
#   docker run -p 10000:10000 -v vectora_data:/qdrant -e NVIDIA_API_KEY=... vectora
#
# Build args:
#   EMBEDDINGS=nvidia (default) | local   local bundles sentence-transformers (+~1 GB, needs >=2 GB RAM)
#   QDRANT_VERSION                         Qdrant server release to bundle

ARG NODE_VERSION=22
ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------------------------------------
# Stage 1: build the Next.js frontend (standalone server bundle)
# ---------------------------------------------------------------------------------------------
FROM node:${NODE_VERSION}-bookworm-slim AS frontend-build
WORKDIR /build
ENV NEXT_TELEMETRY_DISABLED=1
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build \
 && test -f .next/standalone/server.js

# ---------------------------------------------------------------------------------------------
# Stage 2: fetch a pinned, checksum-verified Qdrant binary (static musl build: no glibc coupling)
# ---------------------------------------------------------------------------------------------
FROM debian:bookworm-slim AS qdrant-fetch
ARG QDRANT_VERSION=1.19.2
ARG QDRANT_SHA256_AMD64=50b253243309ed0ae50a19f678f0d0adcc4f0b567b3bd2c5c0c7e02fa8404bb6
ARG QDRANT_SHA256_ARM64=6970b93b56fa1203f0cea47d2f330fdb654988fd56617aa77e8478cffd3c0ccb
ARG TARGETARCH
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*
RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
      amd64) arch=x86_64;  sha="$QDRANT_SHA256_AMD64" ;; \
      arm64) arch=aarch64; sha="$QDRANT_SHA256_ARM64" ;; \
      *) echo "unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    curl -fsSL --retry 5 -o /tmp/qdrant.tgz \
      "https://github.com/qdrant/qdrant/releases/download/v${QDRANT_VERSION}/qdrant-${arch}-unknown-linux-musl.tar.gz"; \
    echo "${sha}  /tmp/qdrant.tgz" | sha256sum -c -; \
    tar -xzf /tmp/qdrant.tgz -C /usr/local/bin qdrant; \
    chmod 0755 /usr/local/bin/qdrant; \
    /usr/local/bin/qdrant --version

# ---------------------------------------------------------------------------------------------
# Stage 3: runtime image
# ---------------------------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime
ARG EMBEDDINGS=nvidia

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=10000 \
    APP_DATA_DIR=/qdrant/app-data \
    QDRANT_URL=http://127.0.0.1:6333 \
    HF_HOME=/opt/hf-cache

RUN apt-get update \
 && apt-get install -y --no-install-recommends nginx tini curl openssl gettext-base ca-certificates libstdc++6 \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10001 --user-group --create-home --home-dir /home/app --shell /usr/sbin/nologin app \
 && mkdir -p /app /qdrant/storage /qdrant/snapshots /qdrant/app-data /tmp/vectora-run \
 && chown -R app:app /qdrant

# Node runtime for the Next.js standalone server (a single self-contained binary).
COPY --from=frontend-build /usr/local/bin/node /usr/local/bin/node
COPY --from=qdrant-fetch /usr/local/bin/qdrant /usr/local/bin/qdrant

# Python dependencies (cached unless requirements change)
WORKDIR /app/backend
COPY backend/requirements.txt backend/requirements-local.txt ./
RUN pip install -r requirements.txt "supervisor==4.3.0"
RUN if [ "$EMBEDDINGS" = "local" ]; then \
      pip install --index-url https://download.pytorch.org/whl/cpu torch \
   && pip install -r requirements-local.txt \
   && python -c "from sentence_transformers import SentenceTransformer as S; S('sentence-transformers/all-MiniLM-L6-v2')" \
   && chmod -R a+rX /opt/hf-cache; \
    fi

# Application code
COPY backend/ /app/backend/
RUN rm -rf /app/backend/tests /app/backend/requirements-dev.txt /app/backend/data /app/backend/.env
COPY --from=frontend-build /build/.next/standalone /app/frontend
COPY --from=frontend-build /build/.next/static /app/frontend/.next/static
COPY --from=frontend-build /build/public /app/frontend/public
COPY deploy/ /app/deploy/
RUN chmod +x /app/deploy/*.sh /app/deploy/fatal_listener.py

# The build variant decides the default embedding provider ("nvidia" | "local").
ENV EMBEDDING_PROVIDER=${EMBEDDINGS}

# /qdrant holds the Qdrant storage (/qdrant/storage), snapshots, and the app's SQLite/session key.
VOLUME ["/qdrant"]
EXPOSE 10000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD sh -c 'curl -fsS "http://127.0.0.1:${PORT:-10000}/healthz" >/dev/null || exit 1'

STOPSIGNAL SIGTERM
ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/app/deploy/entrypoint.sh"]
