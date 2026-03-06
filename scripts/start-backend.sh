#!/usr/bin/env bash
# Start SmartForm backend services (API + Celery OCR worker)
# Usage: ./scripts/start-backend.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

cd "$BACKEND_DIR"

# Activate venv
PYTHON="$BACKEND_DIR/.venv/bin/python"
UVICORN="$BACKEND_DIR/.venv/bin/uvicorn"
CELERY="$BACKEND_DIR/.venv/bin/celery"

if [[ ! -f "$PYTHON" ]]; then
    echo "❌ Virtual environment not found at $BACKEND_DIR/.venv"
    echo "   Run: python -m venv .venv && pip install -r requirements.txt"
    exit 1
fi

cleanup() {
    echo ""
    echo "🛑 Shutting down services..."
    kill $API_PID $WORKER_PID 2>/dev/null
    wait $API_PID $WORKER_PID 2>/dev/null
    echo "✅ All services stopped."
}
trap cleanup EXIT INT TERM

echo "🚀 Starting SmartForm Backend Services"
echo "======================================="

# Start API server
echo "📡 Starting API server on http://localhost:8000 ..."
$UVICORN app.main:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!

# Start Celery OCR worker
echo "⚙️  Starting Celery OCR worker..."
$CELERY -A app.celery_app worker -Q ocr,celery -l info &
WORKER_PID=$!

echo ""
echo "✅ Services running:"
echo "   API:    http://localhost:8000  (PID: $API_PID)"
echo "   Docs:   http://localhost:8000/docs"
echo "   Worker: Celery OCR queue      (PID: $WORKER_PID)"
echo ""
echo "Press Ctrl+C to stop all services."
echo ""

# Wait for either process to exit
wait -n $API_PID $WORKER_PID
