#!/usr/bin/env bash
# One-command update for the Pi. Run from anywhere:
#
#   ~/pi-recipe-site/scripts/update.sh          # app only: pull, deps, build, restart
#   ~/pi-recipe-site/scripts/update.sh --apt    # ...after first upgrading system packages
#
# `apt upgrade` on its own only updates Debian packages (ffmpeg, avahi, …). It does NOT pull
# our code, rebuild the frontend, or restart the service — this script does all of that, so
# new features (and their DB migrations, applied at startup) go live in a single step.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE="${RECIPES_SERVICE:-recipes}"

if [[ "${1:-}" == "--apt" ]]; then
  echo "==> System packages (apt)"
  sudo apt update
  sudo apt upgrade -y
fi

echo "==> Pulling latest code"
cd "$REPO"
git pull --ff-only origin main

echo "==> Backend dependencies"
# shellcheck disable=SC1091
. backend/.venv/bin/activate
pip install -q -r backend/requirements.txt

echo "==> Building frontend"
(cd frontend && npm install --no-audit --no-fund && npm run build)

echo "==> Restarting $SERVICE (applies any new DB migrations)"
sudo systemctl restart "$SERVICE"

# Don't report success until the app actually answers.
for _ in 1 2 3 4 5 6 7 8 9 10; do
  if curl -fsS http://localhost/api/health >/dev/null 2>&1; then
    echo "==> Up: $(curl -fsS http://localhost/api/health)"
    exit 0
  fi
  sleep 2
done
echo "!! $SERVICE did not answer /api/health — check: sudo journalctl -u $SERVICE -n 40 --no-pager" >&2
exit 1
