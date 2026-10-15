#!/bin/sh
# Container entrypoint (runs under tini as PID 1's child; ends by exec'ing supervisord so
# SIGTERM from Docker/Render reaches the supervisor and triggers an orderly shutdown).
set -eu

log() { echo "[entrypoint] $*"; }

: "${PORT:=10000}"
: "${MAX_UPLOAD_MB:=25}"
: "${APP_DATA_DIR:=/qdrant/app-data}"
export PORT MAX_UPLOAD_MB APP_DATA_DIR

case "$PORT" in ''|*[!0-9]*) log "PORT must be a number, got '$PORT'"; exit 1 ;; esac
case "$MAX_UPLOAD_MB" in ''|*[!0-9]*) log "MAX_UPLOAD_MB must be a number, got '$MAX_UPLOAD_MB'"; exit 1 ;; esac
if [ "$PORT" = "8000" ] || [ "$PORT" = "3000" ] || [ "$PORT" = "6333" ] || [ "$PORT" = "6334" ]; then
  log "PORT=$PORT collides with an internal service port (3000, 6333, 6334, 8000); choose another."
  exit 1
fi

RUN_DIR=/tmp/vectora-run
mkdir -p "$RUN_DIR/nginx" /qdrant/storage /qdrant/snapshots "$APP_DATA_DIR"

# ---- persistence check -------------------------------------------------------------------
is_mounted() { command -v mountpoint >/dev/null 2>&1 && mountpoint -q "$1"; }
if is_mounted /qdrant || is_mounted /qdrant/storage; then
  log "persistent volume detected for Qdrant storage"
else
  log "WARNING: /qdrant is not a mounted volume. Indexed documents are lost when the container is removed."
  log "         Mount one with: -v vectora_data:/qdrant   (Render: add a Disk with mount path /qdrant)"
fi

# ---- privileges ----------------------------------------------------------------------------
SUPERVISOR_CONF="$RUN_DIR/supervisord.conf"
if [ "$(id -u)" = "0" ]; then
  # Volumes/disks are usually created root-owned; hand the data dirs to the service user.
  for dir in /qdrant/storage /qdrant/snapshots "$APP_DATA_DIR"; do
    [ "$(stat -c %U "$dir")" = "app" ] || chown -R app:app "$dir"
  done
  chown -R app:app "$RUN_DIR"
  cp /app/deploy/supervisord.conf "$SUPERVISOR_CONF"
else
  log "running as non-root uid $(id -u); services run as this user (volumes must be writable by it)"
  grep -v -E '^user=(app|root)$' /app/deploy/supervisord.conf > "$SUPERVISOR_CONF"
fi

# ---- optional HTTP Basic auth gate (protects UI + API; /healthz and /livez stay open) -----
AUTH_BASIC=""
if [ -n "${BASIC_AUTH_USER:-}" ] || [ -n "${BASIC_AUTH_PASSWORD:-}" ]; then
  if [ -z "${BASIC_AUTH_USER:-}" ] || [ -z "${BASIC_AUTH_PASSWORD:-}" ]; then
    log "Set BOTH BASIC_AUTH_USER and BASIC_AUTH_PASSWORD (or neither)."
    exit 1
  fi
  hash="$(printf '%s' "$BASIC_AUTH_PASSWORD" | openssl passwd -apr1 -stdin)"
  printf '%s:%s\n' "$BASIC_AUTH_USER" "$hash" > "$RUN_DIR/htpasswd"
  chmod 640 "$RUN_DIR/htpasswd"
  [ "$(id -u)" != "0" ] || chown root:app "$RUN_DIR/htpasswd"
  AUTH_BASIC='auth_basic "Vectora"; auth_basic_user_file /tmp/vectora-run/htpasswd;'
  log "HTTP Basic auth is ENABLED"
else
  log "HTTP Basic auth is disabled (set BASIC_AUTH_USER/BASIC_AUTH_PASSWORD to enable)"
fi
export AUTH_BASIC
MAX_BODY_MB=$((MAX_UPLOAD_MB + 2))
export MAX_BODY_MB

envsubst '${PORT} ${MAX_BODY_MB} ${AUTH_BASIC}' < /app/deploy/nginx.conf.template > "$RUN_DIR/nginx.conf"
# nginx ignores (and warns about) `user` when not started as root
[ "$(id -u)" = "0" ] || sed -i '/^user app;$/d' "$RUN_DIR/nginx.conf"
[ "$(id -u)" != "0" ] || chown app:app "$RUN_DIR/nginx.conf"

# ---- configuration summary (never prints secrets) ------------------------------------------
if [ -z "${NVIDIA_API_KEY:-}" ]; then
  log "WARNING: NVIDIA_API_KEY is not set - chat and uploads will fail and /healthz will report 503."
fi
log "public port=$PORT  max upload=${MAX_UPLOAD_MB}MB  data=$APP_DATA_DIR  qdrant=/qdrant/storage"
log "chat model=${NVIDIA_MODEL:-meta/llama-3.3-70b-instruct}  embeddings=${EMBEDDING_PROVIDER:-nvidia}/${EMBEDDING_MODEL:-${NVIDIA_EMBEDDING_MODEL:-default}}"
log "starting supervisor: qdrant -> backend -> frontend -> nginx"

exec supervisord -n -c "$SUPERVISOR_CONF"
