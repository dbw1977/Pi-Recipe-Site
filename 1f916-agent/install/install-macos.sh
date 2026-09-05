#!/bin/sh
# Install (or reinstall) the 1f916-agent launchd agent on macOS.
#
# Renders the plist template with your real paths, drops it in
# ~/Library/LaunchAgents/, and loads it so the agent runs daily at 09:00.
#
# Usage:
#   sh install/install-macos.sh              # uses ./.venv/bin/python3 if present, else python3
#   PYTHON=/opt/homebrew/bin/python3 sh install/install-macos.sh   # force a specific python
#
# Re-run it any time paths change; it reloads cleanly.
set -eu

REPO="$(cd "$(dirname "$0")/.." && pwd)"
LABEL="com.1f916.agent"
TEMPLATE="$REPO/install/$LABEL.plist"
DEST="$HOME/Library/LaunchAgents/$LABEL.plist"

# Pick a Python: explicit $PYTHON, else the repo venv, else system python3.
if [ "${PYTHON:-}" = "" ]; then
    if [ -x "$REPO/.venv/bin/python3" ]; then
        PYTHON="$REPO/.venv/bin/python3"
    else
        PYTHON="$(command -v python3 || true)"
    fi
fi
if [ "$PYTHON" = "" ] || [ ! -x "$PYTHON" ]; then
    echo "error: no usable python3 found (set PYTHON=/path/to/python3)" >&2
    exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

sed -e "s|__PYTHON__|$PYTHON|g" \
    -e "s|__REPO__|$REPO|g" \
    -e "s|__HOME__|$HOME|g" \
    "$TEMPLATE" > "$DEST"

# Reload cleanly (bootout may not exist on older macOS; fall back to unload).
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || launchctl unload "$DEST" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST" 2>/dev/null || launchctl load "$DEST"

echo "Installed $DEST"
echo "  python : $PYTHON"
echo "  repo   : $REPO"
echo "  schedule: daily at 09:00"
echo "  logs   : ~/Library/Logs/1f916-agent.{out,err}.log"
echo
echo "Run it once right now to test:  launchctl start $LABEL"
echo "Stop scheduling:                launchctl bootout gui/$(id -u)/$LABEL"
