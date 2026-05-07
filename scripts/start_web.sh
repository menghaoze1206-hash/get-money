#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Build frontend if not yet built
if [ ! -d "$PROJECT_DIR/frontend/dist" ]; then
  echo "==> Building frontend..."
  cd "$PROJECT_DIR/frontend"
  npm install --registry=https://registry.npmmirror.com 2>/dev/null || npm install
  npm run build
  cd "$PROJECT_DIR"
fi

echo "==> Starting web server at http://localhost:8000"
echo "    Dashboard: http://localhost:8000"

export PYTHONPATH="$PROJECT_DIR"
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
