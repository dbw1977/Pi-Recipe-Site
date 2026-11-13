#!/usr/bin/env bash
# Build the installable release package:  scripts/build-release.sh v1.0.0
#
# Produces dist-release/pi-recipe-site-<version>.tar.gz (+ .sha256) containing the backend, the
# ALREADY-BUILT frontend (frontend/dist), scripts, .env.example, LICENSE and README — everything
# needed to run the app, and nothing that isn't (no tests, no node_modules, no source for the
# frontend, no local data). Someone installing from the package never needs Node.
#
# Set SKIP_FRONTEND_BUILD=1 to reuse an existing frontend/dist (CI builds it in a prior step).
set -euo pipefail

VERSION="${1:?usage: scripts/build-release.sh <version>   e.g. v1.0.0}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="pi-recipe-site-${VERSION}"
OUT="$ROOT/dist-release"

if [[ "${SKIP_FRONTEND_BUILD:-0}" != "1" ]]; then
  echo "==> Building the frontend"
  (cd "$ROOT/frontend" && npm ci && npm run build)
fi
[[ -f "$ROOT/frontend/dist/index.html" ]] || { echo "frontend/dist/index.html is missing — build the frontend first" >&2; exit 1; }

echo "==> Assembling $NAME"
rm -rf "$OUT"
mkdir -p "$OUT/$NAME"
tar -C "$ROOT" \
  --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' \
  --exclude='backend/tests' --exclude='backend/.venv' --exclude='backend/data' --exclude='backend/media' \
  -cf - backend scripts frontend/dist .env.example LICENSE README.md \
  | tar -C "$OUT/$NAME" -xf -
echo "$VERSION" > "$OUT/$NAME/VERSION"

echo "==> Packing"
tar -C "$OUT" -czf "$OUT/$NAME.tar.gz" "$NAME"
(cd "$OUT" && sha256sum "$NAME.tar.gz" > "$NAME.tar.gz.sha256")
rm -rf "$OUT/$NAME"

echo "==> Done:"
ls -lh "$OUT"
