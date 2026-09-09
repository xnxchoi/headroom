#!/bin/zsh
set -euo pipefail
emulate -LR zsh

fail=0
check() {
    local name="$1"
    shift
    if "$@"; then
        print -r -- "PASS  $name"
    else
        print -r -- "FAIL  $name"
        fail=1
    fi
}

check "proxy 8787 /readyz" /usr/bin/curl --silent --fail --max-time 2 http://127.0.0.1:8787/readyz
check "proxy 8789 /readyz" /usr/bin/curl --silent --fail --max-time 2 http://127.0.0.1:8789/readyz
check "mcp 8788 listening" /usr/sbin/lsof -nP -iTCP:8788 -sTCP:LISTEN
check "grok-4.6 base_url" /usr/bin/grep -q 'base_url = "http://127.0.0.1:8789/v1"' "$HOME/.grok/config.toml"
if /usr/bin/awk 'BEGIN{h=""} /^\[/{h=$0} h=="[models]" && $0 ~ /^base_url/{found=1} END{exit found?0:1}' "$HOME/.grok/config.toml"; then
    print -r -- "FAIL  no [models] base_url"
    fail=1
else
    print -r -- "PASS  no [models] base_url"
fi
check "codex model_provider=headroom" /usr/bin/grep -q 'model_provider = "headroom"' "$HOME/.codex/config.toml"
check "codex websockets" /usr/bin/grep -q 'supports_websockets = true' "$HOME/.codex/config.toml"
check "codex requires_openai_auth" /usr/bin/grep -q 'requires_openai_auth = true' "$HOME/.codex/config.toml"
check "claude ANTHROPIC_BASE_URL" /usr/bin/grep -q '127.0.0.1:8787' "$HOME/.claude/settings.json"
check "savings file preserved" test -s "$HOME/.headroom/proxy_savings.json"
check "overlay grace file" /usr/bin/grep -Eq '^[0-9]+$' "$HOME/.headroom/overlay/stop_grace_seconds"
check "headroom-stop on PATH or ~/.local/bin" test -x "$HOME/.local/bin/headroom-stop"
if /usr/bin/curl --silent --fail --max-time 2 http://127.0.0.1:8787/dashboard | /usr/bin/grep -q 'macos-overlay-panel'; then
    print -r -- "PASS  dashboard overlay inject"
else
    print -r -- "FAIL  dashboard overlay inject"
    fail=1
fi
if /usr/bin/curl --silent --fail --max-time 2 http://127.0.0.1:8787/overlay/lifecycle | /usr/bin/grep -q 'grace_seconds'; then
    print -r -- "PASS  overlay lifecycle API"
else
    print -r -- "FAIL  overlay lifecycle API"
    fail=1
fi

print -r -- "--- mcp serve count ---"
/usr/bin/pgrep -lf "headroom mcp serve" || true
print -r -- "--- doctor ---"
"$HOME/.headroom/venv/bin/headroom" doctor --port 8787 || true

exit "$fail"
