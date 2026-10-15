# Vectora

**Chat with your PDFs.** Upload documents, and Vectora answers questions grounded in them, with
page-level sources. Retrieval-Augmented Generation on **NVIDIA NIM** (answers + embeddings) and
**Qdrant** (vector search), shipped as **one Docker image that runs in one container**.

```
Browser ─► nginx :$PORT ─┬─► Next.js UI        (127.0.0.1:3000)
 (public)                └─► FastAPI  /api/*   (127.0.0.1:8000) ─► NVIDIA NIM (external API)
                                      │
                                      └────────► Qdrant         (127.0.0.1:6333)  data: /qdrant/storage
```

Only nginx listens on a public interface. supervisord (under tini) starts and supervises
Qdrant → API → UI → nginx, restarts crashed services, and shuts them down in reverse order on SIGTERM.

## Features

- Multi-PDF upload, chunking, embedding, indexing (Qdrant, cosine similarity)
- Semantic search + source-cited answers, chat history with auto-titles, RAG on/off toggle
- Per-user isolation of documents, vectors and chats (signed session cookie, see *Security*)
- Delete a single document, or wipe all of *your* indexed data
- Health endpoint (`/healthz`) that reports real readiness (API + Qdrant + config)

## Configuration

All settings are environment variables; see [`.env.example`](.env.example) for the full annotated list.

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `NVIDIA_API_KEY` | **yes** | – | NVIDIA NIM key ([build.nvidia.com](https://build.nvidia.com)). Never committed or logged. |
| `NVIDIA_BASE_URL` | no | `https://integrate.api.nvidia.com/v1` | OpenAI-compatible NIM endpoint (also works for a self-hosted NIM). |
| `NVIDIA_MODEL` | no | `meta/llama-3.3-70b-instruct` | Chat model that writes answers. |
| `EMBEDDING_PROVIDER` | no | `nvidia` | `nvidia` (NIM `/embeddings`) or `local` (needs the `EMBEDDINGS=local` build). |
| `EMBEDDING_MODEL` | no | `nvidia/nemotron-3-embed-1b` | Embedding model (2048 dims). Unknown models also need `EMBEDDING_DIMENSION`. |
| `QDRANT_COLLECTION` | no | `vectora_chunks` | Use a **new** name if you change the embedding model. |
| `PORT` | no | `10000` | Public port (Render sets it). |
| `MAX_UPLOAD_MB` | no | `25` | Per-request upload limit. |
| `SESSION_SECRET` | no | generated + persisted | Signs session cookies. |
| `BASIC_AUTH_USER` / `BASIC_AUTH_PASSWORD` | no | off | Password-protect the whole site. **Recommended for public URLs.** |

### Why embeddings are configured separately
A NIM *chat* model cannot produce embeddings. Vectora therefore uses a dedicated embedding model
(`nvidia/nemotron-3-embed-1b`, 2048-d, asymmetric: documents are embedded as `passage`, questions as
`query`). Chunk size is capped to the model's context window (1500 words by default) so a whole chunk
is embedded, and the Settings slider is limited accordingly.

**NVIDIA retires hosted models** (the original default, `nv-embedqa-e5-v5`, now returns HTTP 410).
If uploads fail with HTTP 404/410, call `GET /api/test-embeddings`, list what your key can use with
`curl -H "Authorization: Bearer $NVIDIA_API_KEY" https://integrate.api.nvidia.com/v1/models`, then set
`EMBEDDING_MODEL` (and `EMBEDDING_DIMENSION` if the model is not one Vectora knows). A collection that
is incompatible with the new model is rebuilt automatically **only if it is empty**; if it already holds
documents, use a new `QDRANT_COLLECTION` name and re-upload.

## Run with Docker (one container)

```bash
# 1. configure
cp .env.example .env          # then put your NVIDIA_API_KEY in .env

# 2. build the image
docker build -t vectora .

# 3. run it, with a named volume so documents/vectors/chats survive restarts and upgrades
docker run -d --name vectora \
  -p 10000:10000 \
  -v vectora_data:/qdrant \
  --env-file .env \
  --restart unless-stopped \
  vectora

# 4. check it
docker logs -f vectora                    # [entrypoint] / [backend] / [nginx] / qdrant lines
curl http://localhost:10000/healthz        # 200 + JSON when everything is ready
open http://localhost:10000                # the app
./scripts/smoke-test.sh http://localhost:10000
```

Stop gracefully with `docker stop vectora` (SIGTERM → nginx, API, then Qdrant flush and exit).
The volume mounted at **`/qdrant`** holds `/qdrant/storage` (Qdrant vectors), `/qdrant/snapshots`,
and `/qdrant/app-data` (SQLite chats/document list + session key). A bind mount also works:
`-v "$PWD/vectora-data:/qdrant"` (the container fixes ownership on start).

Variants: `docker build --build-arg EMBEDDINGS=local -t vectora:local .` bundles the optional
local sentence-transformers embedder (~1 GB larger, needs ≥ 2 GB RAM).
Apple Silicon / ARM: the same Dockerfile builds natively (a checksum-pinned arm64 Qdrant is used).

### Build a portable image archive
```bash
./scripts/build-image.sh                      # -> vectora-image.tar.gz
gunzip -c vectora-image.tar.gz | docker load # on any other machine
```

## Deploy on Render

**Blueprint (recommended)**
1. Push this project to a GitHub/GitLab repository (the `.gitignore` keeps secrets out).
2. Render Dashboard → **New → Blueprint** → select the repository. Render reads [`render.yaml`](render.yaml).
3. When prompted, enter `NVIDIA_API_KEY`. Also set `BASIC_AUTH_USER` / `BASIC_AUTH_PASSWORD`
   (recommended so strangers cannot spend your NVIDIA quota) or leave them empty.
4. Click **Apply**. First build takes several minutes. Render then polls `/healthz`;
   the service goes live once it returns 200.

**Manual setup** (equivalent): New → **Web Service** → Runtime **Docker** → plan **Standard** (a
disk requires a paid plan; 2 GB RAM recommended) → *Health Check Path* `/healthz` → *Advanced*:
add a **Disk** with mount path **`/qdrant`** (10 GB) → set env vars below → *Max shutdown delay* 60 s.

| Render env var | Value |
|---|---|
| `NVIDIA_API_KEY` | your key (**secret**) |
| `NVIDIA_MODEL` | `meta/llama-3.3-70b-instruct` (or any NIM chat model) |
| `EMBEDDING_PROVIDER` | `nvidia` |
| `SESSION_SECRET` | any long random string (Blueprint generates it) |
| `BASIC_AUTH_USER`, `BASIC_AUTH_PASSWORD` | optional, recommended |

Do **not** set `PORT` (Render injects it; the container binds to it). Render terminates TLS; the app
issues `Secure` cookies automatically from `X-Forwarded-Proto`. Single instance only: Qdrant's data
lives on the instance's disk, so do not scale horizontally.

## Operations

- **Logs**: one stream. `[entrypoint]` config summary, `[backend:*]` API, `[nginx]` access lines, plain
  lines from Qdrant and the UI. `LOG_LEVEL=DEBUG` for more.
- **Health**: `/healthz` → 200 only when API + Qdrant + `NVIDIA_API_KEY` are OK, else 503 with a reason.
  `/livez` is nginx-only liveness.
- **Crash recovery**: a crashed service restarts automatically; if one fails repeatedly the container
  exits so the platform restarts it.
- **Changing the embedding model**: vectors from different models are not comparable. Vectora
  **refuses to start indexing** against a collection whose dimension or embedding model differs (health
  turns 503 with instructions) and never deletes it. Set a new `QDRANT_COLLECTION` and re-upload.
- **Backups**: copy the `/qdrant` volume (stop the container first for a consistent copy).

## Security model (read this)

- **Isolation, not accounts.** The browser gets a random user id in a signed, HttpOnly cookie; every SQLite
  row and every Qdrant query is filtered by it, and forged/tampered cookies are rejected. There are no
  logins: whoever holds the cookie owns that data, and clearing cookies orphans it.
- **Gate the site** with `BASIC_AUTH_USER/PASSWORD` for anything public: otherwise anyone who finds the
  URL can create sessions and use your NVIDIA quota. There is no per-user rate limiting.
- Qdrant, the API and the UI bind to loopback inside the container; services run as an unprivileged user.
- Secrets exist only as environment variables; none are in the image, repo, or logs.

## Local development (hot reload)

```bash
cp .env.example .env && $EDITOR .env      # NVIDIA_API_KEY
./start.sh                                # Qdrant (docker) + FastAPI :8000 + Next.js :3000
```

## Tests

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
# integration tests need a Qdrant binary: https://github.com/qdrant/qdrant/releases
QDRANT_BIN=/path/to/qdrant python -m pytest tests -q
cd ../frontend && npm ci && npx tsc --noEmit && npm run build
```
Without `QDRANT_BIN`, integration tests are skipped and only unit tests run. The suite uses a local fake
of the NIM API (`backend/tests/fake_nim.py`), so it needs no key and no network.

## API (all under `/api`)

`POST /upload` · `GET /documents` · `DELETE /documents/{id}` · `POST /chat` · `GET /chats` ·
`GET|DELETE /chat/{id}` · `GET /test-llm` · `GET /test-embeddings` · `GET /vector-store/stats|samples` · `POST /vector-store/clear` ·
`GET /health` · `GET /session`. Interactive API docs are available at `http://localhost:8000/docs` in local development only (not routed through the proxy).

## Changes from the original project

See [`CHANGES.md`](CHANGES.md).
