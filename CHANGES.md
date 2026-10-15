# Changes from the original "Vector Project" (v1) to Vectora v2

## Requested migrations
| Area | Before | After |
|---|---|---|
| LLM | Google Gemini | **NVIDIA NIM** via env vars `NVIDIA_API_KEY`, `NVIDIA_MODEL`, `NVIDIA_BASE_URL`; retries with backoff on 429/5xx/timeouts; actionable messages for 401/403/404/429/5xx; key never logged or returned |
| Embeddings | local `all-MiniLM-L6-v2` (384-d, torch) | Audited separately. Default **NIM `nvidia/nemotron-3-embed-1b`** (2048-d, passage/query input types; the originally chosen `nv-embedqa-e5-v5` was retired by NVIDIA on 2026-08-25). Local MiniLM kept as an optional build variant. Every vector's length is validated |
| Vector DB | Endee | **Qdrant** (cosine, payload `user_id`/`filename`/`page`/`text`, tenant index on `user_id`). Existing collections are never deleted or recreated; dimension/distance/model mismatches are refused with instructions |
| Packaging | none (README described an unrelated Node/Mongo stack) | One multi-stage Dockerfile, one container: nginx + Next.js + FastAPI + Qdrant under supervisord/tini, Render blueprint |

## Problems found in the original and fixed
1. **Frontend did not build**: `ChatInterface.tsx` imported a non-existent `./Message` component.
2. **Hard-coded `http://localhost:8000`** in 8 places: unusable outside one dev machine. Now same-origin `/api/*`.
3. **No authentication and no user isolation existed**, although the README claimed JWT auth. Everyone shared one
   global document list, vector index, and chat history, and "Clear" wiped everybody's data. Added signed
   per-browser sessions, scoped every SQLite and Qdrant operation, and optional site-wide Basic auth.
4. **Embedding truncation**: 500-word chunks were embedded with MiniLM (256-token limit), so most of each
   chunk was never searchable. Chunk size is now capped to the embedding model's window.
5. **Chunk-size setting was ignored** (never sent to the backend). Now wired through.
6. **Delete-document button did nothing.** Added `DELETE /api/documents/{id}` (removes vectors too).
7. **"Clear vector store" left the document list populated.** Registry and vectors now stay consistent.
8. `INSERT OR REPLACE` reset every chat's `created_at` on each message; replaced with a proper upsert.
9. `Access-Control-Allow-Origin: *` together with credentials; now same-origin, opt-in allow-list only.
10. Re-uploading the same filename duplicated vectors; it now replaces them (new version written before the old one is removed).
11. Upload hardening: case-insensitive `.pdf`, `%PDF` header check, encrypted-PDF message, size limit (app + nginx), filename sanitising.
12. Chat history was never sent to the model ("future improvement"); recent turns are now included.
13. Deprecated APIs: `import fitz`, `@app.on_event`, `asyncio.get_event_loop`; blocking calls moved off the event loop.
14. Hard-coded UI labels ("Endee Node Active", "Gemini 1.5 Pro", "Healthy", index name) now reflect real state.
15. Dependencies: removed unused `pdfplumber`/`pydantic-settings`/`google-generativeai`; pinned exact tested versions;
    Next.js 14.2.4 → **16.4.0** / React 19.3 (the 14.x line has unpatched advisories): `npm audit --omit=dev` = 0.
16. Dev artefacts removed from the project: `chats.db` (chat history), `.next` cache, `.deps_installed`, stray root lockfile.
17. `start.sh` hard-coded `$HOME/Placement/...` and `konsole`; rewritten as a portable dev launcher.

## API change
All endpoints now live under `/api` (previously a mix of `/chat`, `/chats`, `/vector-store/*`, `/api/upload`).
The bundled UI is updated; external scripts calling the old paths must add the `/api` prefix.

## Data migration
Old SQLite databases are upgraded in place; legacy rows are kept but invisible to every user (they predate
isolation). Vectors in Endee are **not** migrated (different embedding model and store): re-upload documents.

## Embedding model retirement (HTTP 410)
`nvidia/nv-embedqa-e5-v5` was retired by NVIDIA, so default is now `nvidia/nemotron-3-embed-1b` (2048-d, 4096-token window).
New: retired/missing models produce an explicit error naming `EMBEDDING_MODEL`; `GET /api/test-embeddings` probes the
configured model; an incompatible Qdrant collection is rebuilt automatically only when it contains zero vectors.
