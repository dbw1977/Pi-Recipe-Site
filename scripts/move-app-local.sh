#!/usr/bin/env bash
# Moves the APP itself (code, Python environment, service) from where it is now — typically a folder on a
# USB/NAS drive — to the Pi's own memory card, so the site keeps running if that drive drops out.
#
#   ~/pi-recipe-site/scripts/move-app-local.sh            # do it
#   ~/pi-recipe-site/scripts/move-app-local.sh --check    # only show what it would do
#
# Run scripts/move-data-local.sh FIRST (it moves photos and the Google sign-in off the drive).
# This one refuses to run until the database, photos and sign-in are all outside the app folder.
#
# What it does: copies the code to /opt/pi-recipe-site (no photos, no node_modules, no old Python
# environment), builds a fresh Python environment there, rewrites the service to run from the new place,
# and adds a `recipes-update` command that works even when the drive is missing. It COPIES: your old
# folder is left exactly as it was, so you can go back. Safe to run again after a failure.
set -euo pipefail

APP_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
DEST="${RECIPES_DEST:-/opt/pi-recipe-site}"
BIN_DIR="${RECIPES_BIN_DIR:-/usr/local/bin}"
SERVICE="${RECIPES_SERVICE:-recipes}"
ENV_FILE="$APP_DIR/.env"
CHECK=0; [[ "${1:-}" == "--check" ]] && CHECK=1
[[ -z "${1:-}" || "${1:-}" == "--check" ]] || { echo "Usage: $0 [--check]" >&2; exit 2; }

say() { printf '%s\n' "$*"; }
die() { printf '✗ %s\n' "$*" >&2; exit 1; }
(( EUID != 0 )) || die "Run this as your normal user (not with sudo); it asks for your password when needed."
[[ -f "$ENV_FILE" ]] || die "No .env in $APP_DIR — run ./install.sh first."
[[ -x "$APP_DIR/install.sh" ]] || die "$APP_DIR/install.sh is missing."
[[ "$DEST" != *[[:space:]]* ]] || die "The destination path can't contain spaces."
real() { readlink -m -- "$1"; }
[[ "$(real "$APP_DIR")" != "$(real "$DEST")" ]] || { say "✓ The app already runs from $DEST — nothing to do."; exit 0; }

env_get() { { grep -E "^[[:space:]]*$1=" "$ENV_FILE" || true; } | tail -n1 | sed -E "s/^[[:space:]]*$1=//; s/^[\"']//; s/[\"']\$//"; }
inside() { case "$(real "$1")" in "$(real "$APP_DIR")"|"$(real "$APP_DIR")"/*) return 0 ;; *) return 1 ;; esac; }

# --- 1. Settings that an older install kept only in the service file would be lost when the service file is
#        replaced. Carry the path settings over into .env first (a copy of .env is kept).
unit_env="$(systemctl show "$SERVICE" -p Environment --value 2>/dev/null || true)"
PATH_KEYS=(RECIPE_DB_PATH MEDIA_ROOT GOOGLE_TOKEN_PATH THUMBS_DIR BACKUP_LOCAL_DIR GOOGLE_CLIENT_SECRETS)
carry=()
for k in "${PATH_KEYS[@]}"; do
  if [[ -z "$(env_get "$k")" ]]; then
    v="$(printf '%s\n' "$unit_env" | tr ' ' '\n' | sed -n "s/^$k=//p" | head -n1)"
    [[ -z "$v" ]] || carry+=("$k=$v")
  fi
done

# --- 2. Refuse unless everything that must survive is already outside the app folder.
db="$(env_get RECIPE_DB_PATH)"; [[ -n "$db" ]] || for kv in "${carry[@]:-}"; do [[ "$kv" == RECIPE_DB_PATH=* ]] && db="${kv#*=}"; done
media="$(env_get MEDIA_ROOT)";  [[ -n "$media" ]] || for kv in "${carry[@]:-}"; do [[ "$kv" == MEDIA_ROOT=* ]] && media="${kv#*=}"; done
tok="$(env_get GOOGLE_TOKEN_PATH)"; [[ -n "$tok" ]] || for kv in "${carry[@]:-}"; do [[ "$kv" == GOOGLE_TOKEN_PATH=* ]] && tok="${kv#*=}"; done
[[ -n "$db" ]]    || die "RECIPE_DB_PATH isn't set in .env or the service, so the database would be looked for inside the app folder. Add  RECIPE_DB_PATH=/var/lib/recipes/recipes.db  to $ENV_FILE and try again."
media="${media:-$APP_DIR/backend/media}"; tok="${tok:-$APP_DIR/backend/data/google_token.json}"
inside "$db"    && die "The database ($db) is inside the app folder. Stop and ask for help; don't continue."
inside "$media" && die "Your photos are still inside the app folder ($media). Run scripts/move-data-local.sh first."
if inside "$tok" && [[ -e "$tok" ]]; then die "Your Google sign-in is still inside the app folder ($tok). Run scripts/move-data-local.sh first."; fi

# --- 3. Space.
need_kb=$(du -sk --exclude=node_modules --exclude=.venv --exclude=media --exclude=data "$APP_DIR" | cut -f1)
parent="$DEST"; while [[ ! -e "$parent" ]]; do parent="$(dirname "$parent")"; done
have_kb=$(df -Pk "$parent" | awk 'NR==2 {print $4}')
say "App folder:  $APP_DIR"
say "   → will run from $DEST"
say "Code to copy: $(( need_kb / 1024 )) MB (plus about 1 GB for a fresh Python environment); $(( have_kb / 1024 )) MB free."
(( have_kb > need_kb * 2 + 2097152 )) || die "Not enough free space (need roughly 2.5 GB plus twice the code size)."
(( ${#carry[@]} == 0 )) || say "Settings found only in the service file, to be copied into .env: ${carry[*]}"
(( CHECK )) && { say "(--check: nothing was changed.)"; exit 0; }

# --- 4. Copy the code. The Python environment can't be copied (it has its own location baked in);
#        install.sh builds a fresh one. Photos and data are already elsewhere.
say; say "==> Copying the code to $DEST"
sudo install -d -o "$(id -un)" -g "$(id -gn)" "$DEST"
tar -C "$APP_DIR" --exclude=./frontend/node_modules --exclude=./backend/.venv --exclude=./backend/media \
    --exclude=./backend/data --exclude=__pycache__ -cf - . | tar -C "$DEST" -xf -
[[ -f "$DEST/install.sh" && -f "$DEST/.env" ]] || die "The copy looks incomplete; your old folder is untouched."

# --- 5. Settings: carry over service-file-only settings and repoint anything that referred to the old folder.
cp -p "$DEST/.env" "$DEST/.env.before-move-app"
for kv in "${carry[@]:-}"; do [[ -n "$kv" ]] && printf '%s\n' "$kv" >> "$DEST/.env"; done
for k in "${PATH_KEYS[@]}" FRONTEND_DIST; do
  v="$(env_get "$k")"
  if [[ -n "$v" ]] && inside "$v"; then
    nv="$DEST${v#"$APP_DIR"}"
    sed -i "s|^\([[:space:]]*$k=\).*|\1$nv|" "$DEST/.env"
    say "    $k now points at $nv"
  fi
done

# --- 6. Fresh Python environment + service pointing at the new place (waits until the app answers).
say "==> Setting up the app in $DEST (builds a Python environment — a few minutes)"
if ! ( cd "$DEST" && ./install.sh --force-service --skip-packages ); then
  die "Setting up the new copy failed (see above). Your old copy still exists: to go back run  cd $APP_DIR && ./install.sh --force-service"
fi

# --- 7. An update command that doesn't depend on the old drive (or on your home folder being there).
sudo ln -sf "$DEST/scripts/update.sh" "$BIN_DIR/recipes-update"

say
say "✓ The app now runs from $DEST on the memory card."
say "  • Update it from now on with:  recipes-update        (or recipes-update --apt)"
say "  • Your old folder $APP_DIR is untouched. Once you're happy, you can delete it to free space."
say "  • The weekly backup, photos, database and Google sign-in are unchanged."
