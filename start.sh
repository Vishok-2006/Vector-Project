#!/bin/bash

echo "🚀 Starting Vector Project..."

PROJECT_ROOT="$HOME/Placement/Projects/Vector-Project"

# -----------------------------
# 1. Start Endee DB
# -----------------------------
echo "📦 Starting Endee DB..."
if ! docker ps | grep -q 8080; then
  docker run -d -p 8080:8080 -v /tmp/endee_data:/data --name endee_server endeeio/endee-server:latest
else
  echo "Endee DB is already running."
fi

sleep 3

# -----------------------------
# 2. Start Backend (Konsole)
# -----------------------------
echo "⚙️ Starting Backend..."

konsole --hold -e bash -c "
cd $PROJECT_ROOT/backend;
source venv/bin/activate;
echo '🔥 Backend running at http://localhost:8000';
PYTHONPATH=. uvicorn main:app --reload --port 8000
" &

sleep 2

# -----------------------------
# 3. Start Frontend (Konsole)
# -----------------------------
echo "🌐 Starting Frontend..."

konsole --hold -e bash -c "
cd $PROJECT_ROOT/frontend;
echo '🌐 Frontend running at http://localhost:3000';
npm run dev
" &

# -----------------------------
# Done
# -----------------------------
echo ""
echo "✅ Project Started!"
echo "🌍 Frontend: http://localhost:3000"
echo "🔧 Backend: http://localhost:8000"
echo "📦 Endee DB: http://localhost:8080"