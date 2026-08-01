#!/usr/bin/env bash
# Start the Replay Backtest UI. This is the ONLY server -- it serves both the data API and the
# web page. Open http://127.0.0.1:8000/ in your browser once it's up.
#
#   ./run.sh            # start on port 8000
#   PORT=8080 ./run.sh  # start on a different port
set -euo pipefail

cd "$(dirname "$0")"                 # run from replay_tool/ regardless of where you invoke it
PORT="${PORT:-8000}"
VENV_PY=".venv/bin/uvicorn"

if [ ! -x "$VENV_PY" ]; then
  echo "error: $VENV_PY not found. Create the venv first:" >&2
  echo "  /Users/maheshk81/.local/bin/python3.12 -m venv .venv" >&2
  echo "  .venv/bin/pip install fastapi 'uvicorn[standard]' pyarrow" >&2
  exit 1
fi

echo "Replay Backtest  ->  http://127.0.0.1:${PORT}/"
echo "(Ctrl-C to stop)"
exec "$VENV_PY" backend:app --port "$PORT" --reload --log-level warning
