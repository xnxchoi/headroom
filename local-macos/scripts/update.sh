#!/bin/zsh
# Update the Headroom library for this overlay checkout.
# `headroom update` refuses editable git installs — this is the real command.
set -euo pipefail
emulate -LR zsh

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="$HOME/.headroom/venv"
PYTHON="$VENV/bin/python"
HEADROOM="$VENV/bin/headroom"
PATCH="$REPO/local-macos/patches/grok-bandage.patch"
MATCH="$HOME/.headroom/overlay/match-clients.py"
EXTRAS="proxy,code,relevance,mcp,reports"
DOMAIN="gui/$(/usr/bin/id -u)"
export PATH="$HOME/.cargo/bin:/opt/homebrew/bin:$HOME/.local/bin:$PATH"

DROP_BANDAGE=0
FORCE=0
for arg in "$@"; do
    case "$arg" in
        --drop-bandage) DROP_BANDAGE=1 ;;
        --force) FORCE=1 ;;
        -h|--help)
            # Quoted heredoc: printed as --help text, not executed.
            cat <<'EOF'
Usage: update.sh [--drop-bandage] [--force]

Update the Headroom library in ~/.headroom/venv from origin/main.
Must run on branch macos-overlay. Do not run `headroom update`.

  1. Refuse if Grok/ChatGPT/Claude/Codex are running (unless --force)
  2. git fetch + merge origin/main
  3. re-apply patches/grok-bandage.patch unless --drop-bandage
  4. uv pip install -e ".[proxy,code,relevance,mcp,reports]"
  5. rewrite LaunchAgents; retarget client URLs in place
  6. reload lifecycle + 8787/8788/8789, then verify

--force          restart proxies even if listed clients are running
--drop-bandage   skip the grok model-list patch
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

BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$BRANCH" != "macos-overlay" ]]; then
    echo "error: expected branch macos-overlay (got $BRANCH)" >&2
    exit 1
fi
if [[ ! -x "$HEADROOM" || ! -x "$PYTHON" ]]; then
    echo "error: overlay venv missing ($HEADROOM). Run install.sh first." >&2
    exit 1
fi

# Bandage lives as committed files. Do not reverse it before merge — that
# dirties headroom/ and makes `git merge origin/main` fail or double-apply.
if ! git diff --quiet -- headroom pyproject.toml uv.lock crates; then
    echo "error: dirty files under headroom/ / pyproject.toml / uv.lock / crates." >&2
    echo "Commit or stash those, then rerun." >&2
    git status --short -- headroom pyproject.toml uv.lock crates >&2
    exit 1
fi

if [[ -x "$PYTHON" && -f "$MATCH" ]]; then
    clients="$("$PYTHON" "$MATCH" --list || true)"
else
    clients=""
fi
if [[ -n "$clients" && "$FORCE" -eq 0 ]]; then
    print -u2 "Quit these clients first, then rerun. (They load the new library only after a proxy restart.)"
    print -u2 "Or pass --force to restart 8787/8788/8789 anyway."
    print -u2 -- "$clients"
    exit 1
fi

echo "==> 1/6  git fetch + merge origin/main"
git fetch origin
git merge --no-edit origin/main

echo "==> 2/6  grok bandage"
bandage_on() {
    [[ -f "$PATCH" ]] && git apply --reverse --check "$PATCH" >/dev/null 2>&1
}
if (( DROP_BANDAGE )); then
    echo "    --drop-bandage: not applying $PATCH"
elif [[ ! -f "$PATCH" ]]; then
    echo "    no patch file; skip"
elif git apply --check "$PATCH" >/dev/null 2>&1; then
    git apply "$PATCH"
    echo "    applied $PATCH"
elif bandage_on; then
    echo "    already on the tree"
else
    echo "    patch did not apply — likely upstream absorbed it. Continuing without bandage."
fi

echo "==> 3/6  editable reinstall into $VENV"
uv pip install --python "$PYTHON" -e "${REPO}[${EXTRAS}]"
uv pip install --python "$PYTHON" -e "${REPO}/local-macos/overlay_pkg"
"$PYTHON" -c 'from headroom._core import DiffCompressor, SmartCrusher; print("    headroom._core OK")'

echo "==> 4/6  LaunchAgents + client routing"
"$PYTHON" "$REPO/local-macos/scripts/render-plists.py"
"$PYTHON" "$REPO/local-macos/scripts/apply-client-config.py"
"$PYTHON" "$REPO/local-macos/scripts/refresh-clients.py"
/bin/launchctl disable "${DOMAIN}/com.headroom.proxy" >/dev/null 2>&1 || true

echo "==> 5/6  reload overlay jobs"
/bin/launchctl kickstart -k "${DOMAIN}/com.headroom.lifecycle" >/dev/null 2>&1 || true
for label in com.headroom.proxy.openai com.headroom.proxy.grok com.headroom.mcp.http; do
    /bin/launchctl kickstart -k "${DOMAIN}/${label}" >/dev/null 2>&1 || true
done
/bin/launchctl bootstrap "$DOMAIN" "$HOME/Library/LaunchAgents/com.headroom.clients-refresh.plist" >/dev/null 2>&1 || true

echo "==> 6/6  wait for /readyz, then verify"
integer ready=0
integer i
for (( i = 0; i < 30; i++ )); do
    if /usr/bin/curl --silent --fail --max-time 1 http://127.0.0.1:8787/readyz >/dev/null 2>&1 \
        && /usr/bin/curl --silent --fail --max-time 1 http://127.0.0.1:8789/readyz >/dev/null 2>&1; then
        ready=1
        break
    fi
    /bin/sleep 1
done
if (( ! ready )); then
    echo "error: proxies not ready on 8787/8789 after 30s" >&2
    "$REPO/local-macos/scripts/verify.sh" || true
    exit 1
fi
"$REPO/local-macos/scripts/verify.sh"

echo
echo "Done. Fully quit ChatGPT.app if it was open so it reloads ~/.codex/config.toml."
echo "When upstream covers grok-4.6 model-list + wrap, rerun: $0 --drop-bandage"
