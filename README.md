# Agentic Multi-PDF RAG System (Next.js + Gemini + Endee)

A production-ready full-stack Retrieval-Augmented Generation application. It allows you to upload multiple PDFs into the Endee vector database via FastAPI, and perform intelligent agentic reasoning over them using Google's Gemini 1.5 Pro AI and a beautiful Next.js + Framer Motion UI that mimics a modern developer portfolio.

## Tech Stack
-   **Frontend**: Next.js 14 (App Router), Tailwind CSS, Framer Motion, React Markdown
-   **Backend**: FastAPI, `google-generativeai`, `pymupdf`, `sentence-transformers`
-   **Database**: Endee Vector Database via Docker

---

## 1. Setup Instructions

### Environment Variables

**Backend (`backend/.env`)**
Create the `.env` file in the `backend/` :
```
GEMINI_API_KEY="your_google_ai_studio_api_key_here"
ENDEE_HOST="localhost"
ENDEE_PORT="8080"
```

### Endee Integration (Docker)
Ensure you have docker installed. You can run Endee locally with Docker Compose:
```bash
docker run -p 8080:8080 -v /tmp/endee_data:/data endeedb/endee:latest
```
*(If you have an `endee/docker-compose.yml` locally, you can `docker compose up -d` in that folder instead)*

### Backend Initialization
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```
This starts the backend on `http://localhost:8000`.

### Frontend Initialization
```bash
cd frontend
npm install
npm run dev
```
Open your browser to `http://localhost:3000`. The frontend will pipe `/api/*` proxies to FastAPI automatically via Next.js rewrites.

---

## 2. API Routes

### `POST /api/upload`
Accepts `multipart/form-data` with one or more `files`.
Extracts content via PyMuPDF, chunks the text, creates `MiniLM-L6-v2` embeddings, and upserts them to the Endee local database.

### `POST /api/query`
Accepts a JSON body with `query` and conversational `history`.
Returns the `answer` directly from Gemini, along with the `sources` metadata denoting filenames and pages of context chunks retrieved for grounded results.

---

## 3. Sample Prompts

1.  **Extract Specifics**: "Find all mentions of performance metrics across the uploaded logs."
2.  **Compare Documents**: "Compare the introductory thesis in Document A against the conclusion detailed in Document B."
3.  **Out-of-Scope Fallback Validation**: "What is the molecular weight of Water?" -> (Assistant will cleanly reject this as "Not found in documents" due to strict boundary prompting).
4.  **Follow-up Context**: "Summarize that last point again but format it as a markdown table."

---

## 4. Deployment Steps

**Backend (Production)**
1. Dockerize the FastAPI app using `tiangolo/uvicorn-gunicorn-fastapi:python3.10`.
2. Configure persistent volumes for the Endee database to prevent data deletion.
3. For deployment platforms like Google Cloud Run or AWS App Runner, inject `GEMINI_API_KEY` into secrets management natively.

**Frontend (Vercel)**
Deploy via Vercel for native App Router capabilities:
1. `npm i -g vercel`
2. Run `vercel` in the `/frontend` directory.
3. Configure your production rewrites inside `next.config.mjs` to target your deployed FastAPI URL.
