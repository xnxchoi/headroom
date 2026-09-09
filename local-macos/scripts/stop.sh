#!/bin/zsh
# headroom-stop — terminate overlay Headroom at will, with safeguards.
#
# Pipeline:
#   1. List named signed clients (Grok / ChatGPT / Claude / Codex).
#   2. If any are running: notify, print them, exit 1. Do not kill Headroom.
#   3. SIGTERM the three overlay jobs (8787/8788/8789) and leftover overlay
#      mcp/proxy processes owned by this user.
#   4. SIGKILL only leftovers that are still ours.
#   5. Leave LaunchAgents registered so lifecycle can start them again.
set -euo pipefail
emulate -LR zsh

MATCH="$HOME/.headroom/overlay/match-clients.py"
HEADROOM="$HOME/.headroom/venv/bin/headroom"
PYTHON="$HOME/.headroom/venv/bin/python"

notify() {
    /usr/bin/osascript -e 'display notification "Quit listed Grok/ChatGPT/Claude/Codex processes first, then retry." with title "headroom-stop"' >/dev/null 2>&1 || true
}

if [[ -f "$MATCH" ]]; then
    clients="$(/usr/bin/python3 "$MATCH" --list || true)"
    if [[ -n "${clients}" ]]; then
        print -u2 "Quit these client processes first, then retry:"
        print -u2 -- "$clients"
        notify "Quit listed Grok/ChatGPT/Claude/Codex processes first, then retry."
        exit 1
    fi
fi

if [[ -x "$HEADROOM" ]]; then
    exec "$HEADROOM" overlay stop
fi

if [[ -x "$PYTHON" ]]; then
    exec "$PYTHON" -c 'from headroom_macos_overlay.control import stop
import sys
code, message, clients = stop()
if clients:
    print(message, file=sys.stderr)
    for row in clients:
        print("  " + row, file=sys.stderr)
    raise SystemExit(1)
print(message)
raise SystemExit(1 if code else 0)
'
fi

print -u2 "overlay venv missing; cannot stop via headroom overlay"
exit 1
