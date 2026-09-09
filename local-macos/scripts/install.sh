#!/bin/zsh
set -euo pipefail
emulate -LR zsh

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="$HOME/.headroom/venv"
PYTHON="$VENV/bin/python"
HEADROOM="$VENV/bin/headroom"
UID_NUM="$(/usr/bin/id -u)"
DOMAIN="gui/${UID_NUM}"

mkdir -p "$HOME/.headroom" "$HOME/Library/Logs/headroom" "$HOME/.local/libexec"

echo "==> creating venv at $VENV"
if [[ ! -x "$PYTHON" ]]; then
    uv venv "$VENV" --python 3.13
fi

echo "==> installing editable headroom extras (proxy,code,relevance,mcp,reports)"
export PATH="$HOME/.cargo/bin:/opt/homebrew/bin:$PATH"
uv pip install --python "$PYTHON" -e "${REPO}[proxy,code,relevance,mcp,reports]"
uv pip install --python "$PYTHON" -e "${REPO}/local-macos/overlay_pkg"

echo "==> verifying Rust extension"
if ! "$PYTHON" -c 'from headroom._core import DiffCompressor, SmartCrusher; print("headroom._core OK", DiffCompressor, SmartCrusher)'; then
    echo "error: headroom._core did not import. Install a Rust toolchain (rustup) and re-run." >&2
    exit 1
fi

echo "==> bootout old LaunchAgents (lifecycle first)"
for label in com.headroom.lifecycle com.headroom.proxy com.headroom.proxy.openai com.headroom.proxy.grok com.headroom.mcp.http; do
    /bin/launchctl bootout "${DOMAIN}/${label}" >/dev/null 2>&1 || true
done

echo "==> stopping leftover headroom mcp stdio"
/usr/bin/pkill -f "headroom mcp serve" >/dev/null 2>&1 || true
/usr/bin/pkill -f "python -m headroom.cli proxy" >/dev/null 2>&1 || true
sleep 1

echo "==> rendering plists"
"$PYTHON" "$REPO/local-macos/scripts/render-plists.py"

echo "==> applying client config"
"$PYTHON" "$REPO/local-macos/scripts/apply-client-config.py"
echo "==> discovering signed Grok/ChatGPT/Claude/Codex clients"
/usr/bin/python3 "$REPO/local-macos/scripts/refresh-clients.py"

echo "==> bootstrap lifecycle (starts proxies when clients are present)"
/bin/launchctl bootstrap "$DOMAIN" "$HOME/Library/LaunchAgents/com.headroom.lifecycle.plist"
/bin/launchctl enable "${DOMAIN}/com.headroom.lifecycle" >/dev/null 2>&1 || true
/bin/launchctl kickstart -k "${DOMAIN}/com.headroom.lifecycle" >/dev/null 2>&1 || true
/bin/launchctl bootstrap "$DOMAIN" "$HOME/Library/LaunchAgents/com.headroom.clients-refresh.plist" >/dev/null 2>&1 || true
/bin/launchctl enable "${DOMAIN}/com.headroom.clients-refresh" >/dev/null 2>&1 || true

echo "==> headroom binary: $HEADROOM"
"$HEADROOM" --version
echo "Install complete. Fully quit and reopen ChatGPT.app so Codex/ChatGPT desktop pick up ~/.codex/config.toml."
echo "Then run: $REPO/local-macos/scripts/verify.sh"
