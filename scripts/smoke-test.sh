#!/usr/bin/env bash
# Boot the app from a folder and check the basics, using a throwaway database:
#     scripts/smoke-test.sh <app-folder>
# <app-folder> is a checkout with frontend/dist built, or an unpacked release package.
# Needs the backend's Python packages in the Python it runs (set PYTHON to pick one).
# Used by CI, the weekly fresh-install check, and the release workflow — and handy locally.
set -euo pipefail

APP="${1:?usage: scripts/smoke-test.sh <app-folder>}"
PY="${PYTHON:-python}"
PORT="${PORT:-$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1])')}"
TMP="$(mktemp -d)"
LOG="$TMP/server.log"
PID=""
cleanup() { [[ -n "$PID" ]] && kill "$PID" 2>/dev/null || true; rm -rf "$TMP"; }
trap cleanup EXIT

fail() {
  echo "SMOKE TEST FAILED: $1" >&2
  echo "--- server log (last 30 lines) ---" >&2
  tail -30 "$LOG" >&2 || true
  exit 1
}

cd "$APP/backend"
RECIPE_DB_PATH="$TMP/data/recipes.db" MEDIA_ROOT="$TMP/media" \
  "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" >"$LOG" 2>&1 &
PID=$!
base="http://127.0.0.1:$PORT"

for _ in $(seq 1 60); do
  curl -fsS "$base/api/health" >/dev/null 2>&1 && break
  kill -0 "$PID" 2>/dev/null || fail "the app exited during startup"
  sleep 0.5
done

curl -fsS "$base/api/health" | grep -q '"status":"ok"'                      || fail "health check"
curl -fsS "$base/" | grep -q 'id="root"'                                    || fail "the web app (frontend/dist) isn't being served"
curl -fsS "$base/api/tags" | python3 -c "
import json, sys
cats = json.load(sys.stdin)
assert cats and sum(len(c['tags']) for c in cats) > 20, 'tag vocabulary not seeded'
"                                                                           || fail "database migrations / tag seed didn't run"
[[ "$(curl -fsS "$base/api/recipes")" == "[]" ]]                            || fail "a fresh library should be empty"
[[ "$(curl -fsS -o /dev/null -w '%{http_code}' "$base/api/backups/status")" == "200" ]] || fail "backups status"
echo "smoke test passed: $APP"
