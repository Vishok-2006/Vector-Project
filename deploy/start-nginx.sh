#!/bin/sh
# Start nginx only once the API and the web server answer, so the public port never
# returns 502s during boot. (The API answers /api/health even while Qdrant is still starting.)
set -eu
CONF=/tmp/vectora-run/nginx.conf
deadline=$(( $(date +%s) + ${NGINX_WAIT_SECONDS:-120} ))

wait_for() {
  name="$1"; url="$2"
  until curl -s -o /dev/null --max-time 2 "$url"; do
    if [ "$(date +%s)" -ge "$deadline" ]; then
      echo "[nginx-start] $name not up after ${NGINX_WAIT_SECONDS:-120}s; starting nginx anyway"
      return 0
    fi
    sleep 0.5
  done
  echo "[nginx-start] $name is up"
}

wait_for "backend API" http://127.0.0.1:8000/api/health
wait_for "web frontend" http://127.0.0.1:3000/
echo "[nginx-start] listening on port ${PORT}"
exec nginx -g 'daemon off;' -c "$CONF"
