Here’s your **updated README.md with architecture included and clean structure (single copy-ready format)**:

---

# Vecta – Agentic Multi-PDF RAG System (Next.js + Gemini + Endee)

A production-ready full-stack Retrieval-Augmented Generation (RAG) application that enables users to upload multiple PDFs, store embeddings in a vector database, and perform intelligent agentic reasoning using Google Gemini AI through a modern, interactive UI.

---

## 🚀 Tech Stack

* **Frontend**: Next.js 14 (App Router), Tailwind CSS, Framer Motion, React Markdown
* **Backend**: FastAPI, `google-generativeai`, `pymupdf`, `sentence-transformers`
* **Database**: Endee Vector Database (Docker)

---

## 🏗️ Architecture

```
                ┌──────────────────────────────┐
                │          Frontend            │
                │  Next.js + Tailwind + FM     │
                │  (Chat UI + Upload UI)       │
                └──────────────┬───────────────┘
                               │
                               │ API Calls (/api/*)
                               ▼
                ┌──────────────────────────────┐
                │        FastAPI Backend       │
                │                              │
                │  • PDF Processing (PyMuPDF)  │
                │  • Chunking                  │
                │  • Embeddings (MiniLM)       │
                │  • Query Orchestration       │
                └──────────────┬───────────────┘
                               │
             ┌─────────────────┴─────────────────┐
             │                                   │
             ▼                                   ▼
┌──────────────────────────┐        ┌──────────────────────────┐
│   Endee Vector DB        │        │     Gemini 1.5 Pro AI     │
│  (Embeddings Storage)    │        │  (Reasoning + Response)   │
└──────────────────────────┘        └──────────────────────────┘
             │
             ▼
   Retrieved Context Chunks
             │
             ▼
     Final Answer + Sources
             │
             ▼
         Frontend UI
```

---

## ⚙️ Setup Instructions

### 🔑 Environment Variables

**Backend (`backend/.env`)**

```
GEMINI_API_KEY="your_google_ai_studio_api_key_here"
ENDEE_HOST="localhost"
ENDEE_PORT="8080"
```

---

### 🐳 Endee Setup (Docker)

```bash
docker run \
  --ulimit nofile=100000:100000 \
  -p 8080:8080 \
  -v ./endee-data:/data \
  --name endee-server \
  --restart unless-stopped \
  endeeio/endee-server:latest
```

---

### ⚡ Backend Initialization

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Backend runs on:
👉 [http://localhost:8000](http://localhost:8000)

---

### 💻 Frontend Initialization

```bash
cd frontend
npm install
npm run dev
```

Frontend runs on:
👉 [http://localhost:3000](http://localhost:3000)

> Note: `/api/*` routes are proxied to FastAPI via Next.js rewrites.

---

## 🔌 API Routes

### 📂 `POST /api/upload`

* Accepts: `multipart/form-data` with one or more PDF files
* Process:

  * Extract text using PyMuPDF
  * Chunk content
  * Generate embeddings (`MiniLM-L6-v2`)
  * Store in Endee vector database

---

### 💬 `POST /api/query`

* Accepts:

```json
{
  "query": "your question",
  "history": []
}
```

* Returns:

  * AI-generated answer (Gemini)
  * Source metadata (file name + page references)

---

## 🧠 Core Workflow

1. User uploads PDFs
2. Backend extracts & chunks text
3. Embeddings are generated and stored in Endee
4. User asks a query
5. Relevant chunks are retrieved from Endee
6. Context + query sent to Gemini
7. Gemini generates grounded response
8. Answer + sources displayed in UI

---

## ✨ Features

* Multi-PDF upload and semantic search
* Agentic reasoning with Gemini AI
* Context-aware conversational memory
* Source citation for transparency
* Smooth animated UI (Framer Motion)
* Fully local vector database (Endee)

---
