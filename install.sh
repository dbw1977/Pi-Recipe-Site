#!/usr/bin/env bash
# Pi Recipe Site installer — sets the app up as a service on a Raspberry Pi (or any Debian/Ubuntu
# machine with systemd). Run it from the app folder, as a normal user (it asks for your password
# when it needs administrator rights):
#
#     ./install.sh
#
# Safe to run again: it repairs a broken install and never overwrites your .env, your recipes
# database, or an existing service file (unless you pass --force-service). Your data lives in
# /var/lib/recipes; the app code stays where you put it.
#
# Options:
#   --port N          port to serve on (default 80, so the address is just http://<name>.local)
#   --with-video      also install ffmpeg (needed to import recipes from videos)
#   --hostname NAME   rename this machine so the app is at http://NAME.local (e.g. recipes)
#   --skip-packages   don't run apt (you've installed python3-venv/curl/avahi-daemon yourself)
#   --no-service      set everything up but don't install or start the systemd service
#   --force-service   replace an existing /etc/systemd/system/recipes.service
#   --print-unit      print the service file that would be installed, then exit
#   --uninstall       stop and remove the service (your recipes and photos are kept)
#   --dry-run         show what would happen without changing anything
#   -h, --help        this text
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE="recipes"
UNIT_PATH="/etc/systemd/system/${SERVICE}.service"
STATE_DIR="/var/lib/recipes"
PORT=80
WITH_VIDEO=0
SET_HOSTNAME=""
SKIP_PACKAGES=0
NO_SERVICE=0
FORCE_SERVICE=0
PRINT_UNIT=0
UNINSTALL=0
DRY_RUN=0

# ---------------------------------------------------------------- output helpers
if [[ -t 1 ]]; then B=$'\e[1m'; G=$'\e[32m'; Y=$'\e[33m'; R=$'\e[31m'; N=$'\e[0m'; else B=""; G=""; Y=""; R=""; N=""; fi
step() { echo; echo "${B}==> $*${N}"; }
ok()   { echo "${G}✓${N} $*"; }
note() { echo "  $*"; }
warn() { echo "${Y}!${N} $*" >&2; }
die()  { echo "${R}✗ $*${N}" >&2; exit 1; }
# Run a command, or just show it under --dry-run.
run()  { if (( DRY_RUN )); then echo "  + $*"; else "$@"; fi; }
usage() { sed -n '2,/^set -euo/p' "${BASH_SOURCE[0]}" | sed '$d' | sed 's/^# \{0,1\}//'; }

# ---------------------------------------------------------------- arguments
while (( $# )); do
  case "$1" in
    --port)           PORT="${2:?--port needs a number}"; shift ;;
    --with-video)     WITH_VIDEO=1 ;;
    --hostname)       SET_HOSTNAME="${2:?--hostname needs a name}"; shift ;;
    --skip-packages)  SKIP_PACKAGES=1 ;;
    --no-service)     NO_SERVICE=1 ;;
    --force-service)  FORCE_SERVICE=1 ;;
    --print-unit)     PRINT_UNIT=1 ;;
    --uninstall)      UNINSTALL=1 ;;
    --dry-run)        DRY_RUN=1 ;;
    -h|--help)        usage; exit 0 ;;
    *)                die "Unknown option: $1 (try --help)" ;;
  esac
  shift
done

if ! [[ "$PORT" =~ ^[0-9]+$ ]] || (( PORT < 1 || PORT > 65535 )); then die "--port must be a number from 1 to 65535"; fi
[[ -z "$SET_HOSTNAME" || "$SET_HOSTNAME" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]] \
  || die "--hostname should be lowercase letters, digits and dashes (like: recipes)"
[[ "$APP_DIR" != *[[:space:]]* ]] || die "This folder's path contains a space ($APP_DIR). Move the app to a path without spaces, like ~/pi-recipe-site."

RUN_USER="${USER:-$(id -un)}"

render_unit() {
  sed -e "s|@USER@|$RUN_USER|g" -e "s|@APP_DIR@|$APP_DIR|g" -e "s|@PORT@|$PORT|g" "$APP_DIR/deploy/recipes.service"
}

if (( PRINT_UNIT )); then render_unit; exit 0; fi

# ---------------------------------------------------------------- uninstall
if (( UNINSTALL )); then
  step "Removing the $SERVICE service"
  [[ -f "$UNIT_PATH" ]] || { ok "No service file at $UNIT_PATH — nothing to remove."; }
  run sudo systemctl disable --now "$SERVICE" 2>/dev/null || true
  run sudo rm -f "$UNIT_PATH"
  run sudo systemctl daemon-reload
  ok "Service removed. Your recipes and photos are still in $STATE_DIR, and the app in $APP_DIR."
  note "To delete everything: sudo rm -rf $STATE_DIR  and remove the $APP_DIR folder."
  exit 0
fi

# ---------------------------------------------------------------- pre-flight checks
step "Checking this machine"
(( EUID != 0 )) || die "Run this as your normal user, not root or with sudo — it asks for your password when needed. Just:  ./install.sh"

if [[ -r /etc/os-release ]]; then . /etc/os-release; fi
case "${ID:-}:${ID_LIKE:-}" in
  *debian*|*ubuntu*|*raspbian*) ok "${PRETTY_NAME:-Debian-based Linux}" ;;
  *) (( SKIP_PACKAGES )) || die "This installer is for Raspberry Pi OS / Debian / Ubuntu (found: ${PRETTY_NAME:-unknown}). On another system install Python 3.11+, then use --skip-packages."
     warn "Not a Debian-based system — continuing because of --skip-packages." ;;
esac

command -v python3 >/dev/null || die "python3 isn't installed."
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || die "Python 3.11 or newer is needed (found $(python3 -V 2>&1)). Raspberry Pi OS 'Bookworm' or newer has it."
ok "$(python3 -V 2>&1)"

if (( ! NO_SERVICE )); then
  [[ -d /run/systemd/system ]] || die "This machine isn't running systemd, so the app can't be installed as a service. Use --no-service to set it up anyway and start it by hand."
  command -v sudo >/dev/null || die "sudo isn't available, and it's needed to install the service."
fi
if (( ! SKIP_PACKAGES )); then command -v sudo >/dev/null || die "sudo isn't available, and it's needed to install packages."; fi

free_mb=$(df -Pm "$APP_DIR" | awk 'NR==2 {print $4}')
(( free_mb >= 800 )) || die "Only ${free_mb} MB free here; about 800 MB is needed."
ok "${free_mb} MB free"

# Is something else already using the port? (Our own service from an earlier install is fine.)
if (( ! NO_SERVICE )) && ! systemctl is-active --quiet "$SERVICE" 2>/dev/null; then
  if command -v ss >/dev/null && ss -ltnH "sport = :$PORT" 2>/dev/null | grep -q .; then
    who=$(sudo ss -ltnpH "sport = :$PORT" 2>/dev/null | sed -n 's/.*users:(("\([^"]*\)".*/\1/p' | head -1)
    by=""; [[ -z "$who" ]] || by=" by $who"
    die "Port $PORT is already in use$by. Stop that program (for example: sudo systemctl disable --now ${who:-lighttpd}) or pick another port with:  ./install.sh --port 8080"
  fi
fi

# ---------------------------------------------------------------- system packages
if (( SKIP_PACKAGES )); then
  step "System packages"; note "Skipped (--skip-packages)."
else
  step "Installing system packages"
  pkgs=(python3-venv python3-pip curl avahi-daemon)
  (( WITH_VIDEO )) && pkgs+=(ffmpeg)
  note "${pkgs[*]}"
  run sudo env DEBIAN_FRONTEND=noninteractive apt-get update -qq
  run sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${pkgs[@]}"
  ok "Packages ready"
fi

# ---------------------------------------------------------------- the web app (frontend)
step "Checking the web app files"
if [[ -f "$APP_DIR/frontend/dist/index.html" ]]; then
  ok "Prebuilt web app found — no Node.js needed"
elif [[ -f "$APP_DIR/frontend/package.json" ]]; then
  note "No prebuilt web app here, so it has to be built (needs Node.js 18+; takes a few minutes on a Pi)."
  note "Tip: a release package from GitHub already includes it and skips this step."
  node_ok() { command -v node >/dev/null && node -e 'process.exit(+process.versions.node.split(".")[0] >= 18 ? 0 : 1)'; }
  if ! node_ok; then
    (( SKIP_PACKAGES )) && die "Node.js 18+ is needed to build the web app. Install it, or use a release package."
    run sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nodejs npm
    (( DRY_RUN )) || node_ok || die "The Node.js available here is too old (need 18+). Use a release package from GitHub instead — it needs no Node.js."
  fi
  if (( DRY_RUN )); then echo "  + (cd frontend && npm ci && npm run build)"; else
    (cd "$APP_DIR/frontend" && npm ci --no-audit --no-fund && npm run build)
  fi
  ok "Web app built"
else
  die "Can't find the web app (frontend/dist or frontend/package.json) in $APP_DIR."
fi

# ---------------------------------------------------------------- Python environment
step "Setting up Python"
VENV="$APP_DIR/backend/.venv"
if [[ ! -x "$VENV/bin/python" ]]; then run python3 -m venv "$VENV"; fi
run "$VENV/bin/python" -m pip install -q --disable-pip-version-check -r "$APP_DIR/backend/requirements.txt"
ok "Python packages installed in $VENV"

# ---------------------------------------------------------------- data folder + settings
step "Preparing your data folder and settings"
run sudo install -d -m 755 -o "$RUN_USER" -g "$(id -gn)" "$STATE_DIR"
ok "$STATE_DIR (your recipes database, photos and thumbnails live here)"

ENV_FILE="$APP_DIR/.env"
if [[ -f "$ENV_FILE" ]]; then
  ok ".env already exists — left exactly as it is"
  # An existing install may have set the database path only inside the service file. The command-line
  # tools (e.g. restoring a backup) read .env, not the service file, so they'd look in the wrong place.
  grep -qE '^[[:space:]]*RECIPE_DB_PATH=' "$ENV_FILE" || warn "Your .env doesn't set RECIPE_DB_PATH. If your service file sets it, add the same line to .env (RECIPE_DB_PATH=$STATE_DIR/recipes.db) so command-line tools like 'python -m app.backup restore' use the same database."
else
  if (( DRY_RUN )); then echo "  + write $ENV_FILE"; else
    {
      echo "# Written by install.sh on $(date +%F). Edit this file, then:  sudo systemctl restart $SERVICE"
      echo "# Paths below keep all your data in $STATE_DIR (on the Pi's own disk)."
      echo "RECIPE_DB_PATH=$STATE_DIR/recipes.db"
      echo "MEDIA_ROOT=$STATE_DIR/media"
      echo "GOOGLE_TOKEN_PATH=$STATE_DIR/google_token.json"
      echo
      cat "$APP_DIR/.env.example"
    } > "$ENV_FILE"
    chmod 600 "$ENV_FILE"
  fi
  ok "Created .env with sensible defaults (private to you)"
fi

# ---------------------------------------------------------------- network name
if [[ -n "$SET_HOSTNAME" ]]; then
  step "Naming this machine '$SET_HOSTNAME'"
  run sudo hostnamectl set-hostname "$SET_HOSTNAME"
  run sudo systemctl restart avahi-daemon
  ok "It will answer at http://$SET_HOSTNAME.local"
fi

# ---------------------------------------------------------------- the service
if (( NO_SERVICE )); then
  step "Service"; note "Skipped (--no-service). Start the app by hand with:"
  note "cd $APP_DIR/backend && .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT"
  exit 0
fi

step "Installing the service"
new_unit="$(render_unit)"
unit_changed=0
if [[ -f "$UNIT_PATH" ]] && [[ "$(cat "$UNIT_PATH")" == "$new_unit" ]]; then
  ok "Service file already up to date"
elif [[ -f "$UNIT_PATH" ]] && (( ! FORCE_SERVICE )); then
  warn "A different service file already exists at $UNIT_PATH — left alone."
  note "Compare with:  ./install.sh --print-unit | diff - $UNIT_PATH"
  note "Replace it with:  ./install.sh --force-service"
else
  if (( DRY_RUN )); then echo "  + write $UNIT_PATH"; else printf '%s\n' "$new_unit" | sudo tee "$UNIT_PATH" >/dev/null; fi
  unit_changed=1
  ok "Service file written"
fi
(( unit_changed )) && run sudo systemctl daemon-reload
run sudo systemctl enable "$SERVICE" >/dev/null 2>&1 || true
run sudo systemctl restart "$SERVICE"

# ---------------------------------------------------------------- wait until it answers
if (( DRY_RUN )); then echo; note "(dry run — nothing was changed)"; exit 0; fi
step "Waiting for the app to start"
healthy=0
for _ in $(seq 1 40); do
  if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then healthy=1; break; fi
  sleep 1
done
if (( ! healthy )); then
  echo "${R}✗ The app didn't answer on port $PORT. The last lines of its log:${N}" >&2
  sudo journalctl -u "$SERVICE" -n 25 --no-pager >&2 || true
  die "See above. Fix the problem, then run ./install.sh again."
fi
ok "The app is running"

# ---------------------------------------------------------------- done
host="$(hostname)"; ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
suffix=""; (( PORT == 80 )) || suffix=":$PORT"
echo
echo "${B}${G}All set.${N} Open this on your phone or computer (same wifi):"
echo
echo "    ${B}http://${host}.local${suffix}${N}"
[[ -z "$ip" ]] || echo "    http://${ip}${suffix}   (if the name above doesn't work)"
echo
echo "Next:"
echo "  • Open ⚙ Settings → Admin help to see what's set up and what to do next."
echo "  • Turn on backups: Settings → Backups. Pick a NAS/USB folder or Google Drive."
echo "  • AI features (screenshot/video import, recipe variations) need an Anthropic key —"
echo "    see Settings → Admin help → 'Something is greyed out'. Link imports work without one."
echo "  • Update later with:  $APP_DIR/scripts/update.sh"
