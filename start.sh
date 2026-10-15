#!/usr/bin/env bash
# Local DEVELOPMENT launcher (hot reload, no Docker image build).
# Starts Qdrant in Docker, the FastAPI backend, and the Next.js dev server.
# For the production single-container image see README.md ("Run with Docker").
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [[ ! -f backend/.env && -f .env ]]; then ln -sf "$ROOT/.env" backend/.env; fi
[[ -n "${NVIDIA_API_KEY:-}" || -f .env ]] || { echo "Set NVIDIA_API_KEY or create .env (see .env.example)"; exit 1; }

echo "==> Qdrant (docker, data in ./qdrant-data)"
if ! docker ps --format '{{.Names}}' | grep -q '^vectora_qdrant$'; then
  docker rm -f vectora_qdrant >/dev/null 2>&1 || true
  docker run -d --name vectora_qdrant -p 127.0.0.1:6333:6333 \
    -v "$ROOT/qdrant-data:/qdrant/storage" qdrant/qdrant:v1.19.2 >/dev/null
fi

echo "==> Backend deps"
[[ -d backend/.venv ]] || python3 -m venv backend/.venv
backend/.venv/bin/pip install -q -r backend/requirements.txt

echo "==> Frontend deps"
(cd frontend && [[ -d node_modules ]] || npm ci)

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "==> Backend  http://localhost:8000   (API docs: /docs)"
(cd backend && APP_DATA_DIR="$ROOT/backend/data" PYTHONPATH=. .venv/bin/python -m uvicorn main:app --reload --port 8000) &

echo "==> Frontend http://localhost:3000"
(cd frontend && npm run dev) &

wait
