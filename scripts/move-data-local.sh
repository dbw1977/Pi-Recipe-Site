#!/usr/bin/env bash
# Copies your recipe photos and your Google sign-in from wherever they are now (often a folder inside
# the app, on a USB/NAS drive) to /var/lib/recipes on the Pi's own memory card, then points the app
# at the new copies. Afterwards the app's data survives that drive dropping out.
#
#   ~/pi-recipe-site/scripts/move-data-local.sh            # do it
#   ~/pi-recipe-site/scripts/move-data-local.sh --check    # only show what it would do
#
# Safe: it COPIES (never moves or deletes), checks the copy is complete before switching over, backs up
# your .env first, and leaves the originals where they are. Run it again any time; it won't redo work.
# The database and thumbnails already live in /var/lib/recipes, so they aren't touched.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE="${RECIPES_SERVICE:-recipes}"
STATE_DIR="${RECIPES_STATE_DIR:-/var/lib/recipes}"
ENV_FILE="$APP_DIR/.env"
CHECK=0; [[ "${1:-}" == "--check" ]] && CHECK=1
[[ -z "${1:-}" || "${1:-}" == "--check" ]] || { echo "Usage: $0 [--check]" >&2; exit 2; }

say()  { printf '%s\n' "$*"; }
die()  { printf '✗ %s\n' "$*" >&2; exit 1; }
(( EUID != 0 )) || die "Run this as your normal user (not with sudo); it asks for your password when needed."
[[ -f "$ENV_FILE" ]] || die "No .env in $APP_DIR — run ./install.sh first."

# Value of KEY in .env (last one wins; ignores commented lines). Empty if unset.
env_get() { { grep -E "^[[:space:]]*$1=" "$ENV_FILE" || true; } | tail -n1 | sed -E "s/^[[:space:]]*$1=//; s/^[\"']//; s/[\"']\$//"; }
expand()  { case "$1" in "~"|"~/"*) printf '%s\n' "${HOME}${1#\~}" ;; *) printf '%s\n' "$1" ;; esac; }

MEDIA_NOW="$(expand "$(env_get MEDIA_ROOT)")";           MEDIA_NOW="${MEDIA_NOW:-$APP_DIR/backend/media}"
TOKEN_NOW="$(expand "$(env_get GOOGLE_TOKEN_PATH)")";    TOKEN_NOW="${TOKEN_NOW:-$APP_DIR/backend/data/google_token.json}"
MEDIA_NEW="$STATE_DIR/media"
TOKEN_NEW="$STATE_DIR/google_token.json"

say "Photos:        $MEDIA_NOW"; say "   → will live in $MEDIA_NEW"
say "Google sign-in: $TOKEN_NOW"; say "   → will live in $TOKEN_NEW"

media_done=0; token_done=0
[[ "$(readlink -f "$MEDIA_NOW" 2>/dev/null || echo "$MEDIA_NOW")" == "$(readlink -f "$MEDIA_NEW" 2>/dev/null || echo "$MEDIA_NEW")" ]] && media_done=1
[[ "$(readlink -f "$TOKEN_NOW" 2>/dev/null || echo "$TOKEN_NOW")" == "$(readlink -f "$TOKEN_NEW" 2>/dev/null || echo "$TOKEN_NEW")" ]] && token_done=1
(( media_done && token_done )) && { say "✓ Already on the memory card — nothing to do."; exit 0; }

[[ -d "$STATE_DIR" ]] || die "$STATE_DIR doesn't exist — run ./install.sh first."
if (( ! media_done )); then
  [[ -d "$MEDIA_NOW" ]] || die "Can't read the photo folder $MEDIA_NOW. Is the drive mounted?"
  # Our own backup folders live inside the photo folder; they stay where they are.
  need_kb=$(du -sk --exclude=backups --exclude='recipes-backup*' "$MEDIA_NOW" | cut -f1)
  have_kb=$(df -Pk "$STATE_DIR" | awk 'NR==2 {print $4}')
  say "Photos use $(( need_kb / 1024 )) MB; $(( have_kb / 1024 )) MB free on the memory card."
  (( have_kb > need_kb * 2 + 1048576 )) || die "Not enough free space on the memory card (need the photos' size plus about 1 GB spare)."
fi
(( CHECK )) && { say "(--check: nothing was changed.)"; exit 0; }

count() { find "$1" -type f -not -path "$1/backups/*" -not -name 'recipes-backup*' 2>/dev/null | wc -l; }

say; say "==> Stopping the app while photos are copied"
sudo systemctl stop "$SERVICE" 2>/dev/null || true
trap 'echo; echo "Restarting the app…"; sudo systemctl start "$SERVICE" 2>/dev/null || true' EXIT

if (( ! media_done )); then
  say "==> Copying photos"
  mkdir -p "$MEDIA_NEW"
  if command -v rsync >/dev/null; then
    rsync -a --exclude=/backups --exclude='recipes-backup*' "$MEDIA_NOW"/ "$MEDIA_NEW"/
  else
    ( cd "$MEDIA_NOW" && find . -type f -not -path './backups/*' -not -name 'recipes-backup*' -print0 ) \
      | while IFS= read -r -d '' f; do mkdir -p "$MEDIA_NEW/$(dirname "$f")"; [[ -e "$MEDIA_NEW/$f" ]] || cp -a "$MEDIA_NOW/$f" "$MEDIA_NEW/$f"; done
  fi
  a=$(count "$MEDIA_NOW"); b=$(count "$MEDIA_NEW")
  (( b >= a )) || die "Copy incomplete ($b of $a files). Nothing was switched over; your original photos are untouched."
  say "    ✓ $b files copied and counted"
fi

if (( ! token_done )) && [[ -f "$TOKEN_NOW" ]]; then
  say "==> Copying the Google sign-in"
  install -m 600 "$TOKEN_NOW" "$TOKEN_NEW"
  cmp -s "$TOKEN_NOW" "$TOKEN_NEW" || die "Google sign-in copy didn't match; not switching it over."
elif (( ! token_done )); then
  say "    (no Google sign-in saved yet — only the setting will change)"
fi

say "==> Updating .env (a copy is kept as .env.before-move)"
cp -p "$ENV_FILE" "$ENV_FILE.before-move"
set_env() { # KEY VALUE: replace an existing line (even commented) or append
  if grep -qE "^[#[:space:]]*$1=" "$ENV_FILE"; then
    sed -i -E "0,/^[#[:space:]]*$1=.*/s||$1=$2|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$1" "$2" >> "$ENV_FILE"
  fi
}
(( media_done )) || set_env MEDIA_ROOT "$MEDIA_NEW"
(( token_done )) || set_env GOOGLE_TOKEN_PATH "$TOKEN_NEW"

trap - EXIT
say "==> Starting the app"
sudo systemctl start "$SERVICE"
for _ in $(seq 1 30); do
  if curl -fsS http://localhost/api/health >/dev/null 2>&1; then
    say "✓ Up: $(curl -fsS http://localhost/api/health)"
    say
    say "Your photos and Google sign-in now live in $STATE_DIR. Open a recipe with a photo to confirm."
    say "The old copies are still in $MEDIA_NOW and $TOKEN_NOW. Once you're happy, you can delete them"
    say "to free space on that drive (leave any 'backups' folder alone)."
    exit 0
  fi
  sleep 2
done
say "!! The app didn't answer. To undo:  cp $ENV_FILE.before-move $ENV_FILE && sudo systemctl restart $SERVICE" >&2
exit 1
