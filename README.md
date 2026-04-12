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
docker run \
  --ulimit nofile=100000:100000 \
  -p 8080:8080 \
  -v ./endee-data:/data \
  --name endee-server \
  --restart unless-stopped \
  endeeio/endee-server:latest
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
