#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt
python scripts/generate_samples.py

uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000 &
API_PID=$!
(
  cd frontend
  npm install
  npm run dev
) &
UI_PID=$!

trap 'kill $API_PID $UI_PID 2>/dev/null || true' EXIT
echo "API: http://127.0.0.1:8000/health"
echo "UI:  http://localhost:5173"
wait
