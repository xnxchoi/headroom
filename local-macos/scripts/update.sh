#!/bin/zsh
# Official Headroom upgrade for this machine (git checkout + editable venv),
# then re-apply the macOS overlay.
#
# headroom update refuses checkouts/editables and prints "git pull" /
# "reinstall from source". This script does exactly that, then the overlay.
set -euo pipefail
emulate -LR zsh

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="$HOME/.headroom/venv"
PYTHON="$VENV/bin/python"
HEADROOM="$VENV/bin/headroom"
PATCH="$REPO/local-macos/patches/grok-bandage.patch"
EXTRAS="proxy,code,relevance,mcp,reports"
DOMAIN="gui/$(/usr/bin/id -u)"
export PATH="$HOME/.cargo/bin:/opt/homebrew/bin:$HOME/.local/bin:$PATH"

DROP_BANDAGE=0
for arg in "$@"; do
    case "$arg" in
        --drop-bandage) DROP_BANDAGE=1 ;;
        -h|--help)
            cat <<'EOF'
Usage: update.sh [--drop-bandage]

Runs the official Headroom checkout upgrade, then refreshes this overlay.

  1. headroom update --check
  2. git pull --ff-only origin main
  3. re-apply patches/grok-bandage.patch (unless --drop-bandage)
  4. uv pip install -e ".[proxy,code,relevance,mcp,reports]"
  5. rewrite LaunchAgents + Grok/Codex/Claude routing
  6. restart overlay jobs and verify

--drop-bandage  skip the grok model-list patch (use when upstream has it)
EOF
            exit 0
            ;;
        *)
            echo "unknown argument: $arg" >&2
            exit 1
            ;;
    esac
done

cd "$REPO"

if [[ "$(git rev-parse --abbrev-ref HEAD)" != "main" ]]; then
    echo "error: expected branch main" >&2
    exit 1
fi
if [[ ! -x "$HEADROOM" ]]; then
    echo "error: overlay venv missing ($HEADROOM). Run install.sh first." >&2
    exit 1
fi

echo "==> 1/6  official: headroom update --check"
"$HEADROOM" update --check || true
echo "    (checkout/editable installs cannot self-update; continuing with git pull)"

bandage_on() {
    [[ -f "$PATCH" ]] && git apply --reverse --check "$PATCH" >/dev/null 2>&1
}

echo "==> 2/6  official: git pull --ff-only origin main"
if bandage_on; then
    echo "    reversing grok bandage so pull is clean"
    git apply --reverse "$PATCH"
fi
git fetch origin
git pull --ff-only origin main

echo "==> 3/6  grok bandage"
if (( DROP_BANDAGE )); then
    echo "    --drop-bandage: not applying $PATCH"
elif [[ ! -f "$PATCH" ]]; then
    echo "    no patch file; skip"
elif git apply --check "$PATCH" >/dev/null 2>&1; then
    git apply "$PATCH"
    echo "    applied $PATCH"
elif bandage_on; then
    echo "    already applied"
else
    echo "    patch did not apply — likely upstream absorbed it. Continuing without bandage."
    echo "    To confirm: git diff origin/main -- headroom/providers/grok/model_metadata.py"
fi

echo "==> 4/6  official editable reinstall"
uv pip install --python "$PYTHON" -e "${REPO}[${EXTRAS}]"
uv pip install --python "$PYTHON" -e "${REPO}/local-macos/overlay_pkg"
"$PYTHON" -c 'from headroom._core import DiffCompressor, SmartCrusher; print("    headroom._core OK")'

echo "==> 5/6  overlay: LaunchAgents + client routing"
"$PYTHON" "$REPO/local-macos/scripts/render-plists.py"
"$PYTHON" "$REPO/local-macos/scripts/apply-client-config.py"
/usr/bin/python3 "$REPO/local-macos/scripts/refresh-clients.py"
for label in com.headroom.proxy.openai com.headroom.proxy.grok com.headroom.mcp.http; do
    /bin/launchctl kickstart -k "${DOMAIN}/${label}" >/dev/null 2>&1 || true
done
/bin/launchctl bootstrap "$DOMAIN" "$HOME/Library/LaunchAgents/com.headroom.clients-refresh.plist" >/dev/null 2>&1 || true
/bin/launchctl kickstart "${DOMAIN}/com.headroom.clients-refresh" >/dev/null 2>&1 || true

echo "==> 6/6  verify"
sleep 3
"$REPO/local-macos/scripts/verify.sh" || true

echo
echo "Done. Fully quit ChatGPT.app if it was open so it reloads ~/.codex/config.toml."
echo "When upstream covers grok-4.6 model-list + wrap, rerun: $0 --drop-bandage"
