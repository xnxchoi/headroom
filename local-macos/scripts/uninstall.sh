#!/bin/zsh
set -euo pipefail
emulate -LR zsh

UID_NUM="$(/usr/bin/id -u)"
DOMAIN="gui/${UID_NUM}"
BACKUP_ROOT="$HOME/.headroom/overlay-backup"
LATEST="$(ls -1d "$BACKUP_ROOT"/* 2>/dev/null | tail -n 1 || true)"

echo "==> bootout overlay LaunchAgents"
for label in com.headroom.lifecycle com.headroom.clients-refresh com.headroom.proxy.openai com.headroom.proxy.grok com.headroom.mcp.http; do
    /bin/launchctl bootout "${DOMAIN}/${label}" >/dev/null 2>&1 || true
done
/usr/bin/pkill -f "headroom mcp serve" >/dev/null 2>&1 || true

if [[ -n "$LATEST" ]]; then
    echo "==> restoring from $LATEST"
    if [[ -f "$LATEST/LaunchAgents/com.headroom.proxy.plist" ]]; then
        cp -p "$LATEST/LaunchAgents/com.headroom.proxy.plist" "$HOME/Library/LaunchAgents/"
        /bin/launchctl bootstrap "$DOMAIN" "$HOME/Library/LaunchAgents/com.headroom.proxy.plist" >/dev/null 2>&1 || true
    fi
    if [[ -f "$LATEST/LaunchAgents/com.headroom.lifecycle.plist" ]]; then
        cp -p "$LATEST/LaunchAgents/com.headroom.lifecycle.plist" "$HOME/Library/LaunchAgents/"
        /bin/launchctl bootstrap "$DOMAIN" "$HOME/Library/LaunchAgents/com.headroom.lifecycle.plist" >/dev/null 2>&1 || true
    fi
    [[ -f "$LATEST/libexec/headroom-lifecycle.zsh" ]] && cp -p "$LATEST/libexec/headroom-lifecycle.zsh" "$HOME/.local/libexec/"
    [[ -f "$LATEST/grok/config.toml" ]] && cp -p "$LATEST/grok/config.toml" "$HOME/.grok/config.toml"
    [[ -f "$LATEST/codex/config.toml" ]] && cp -p "$LATEST/codex/config.toml" "$HOME/.codex/config.toml"
    [[ -f "$LATEST/claude/settings.json" ]] && cp -p "$LATEST/claude/settings.json" "$HOME/.claude/settings.json"
fi

echo "Uninstall/restore complete. Savings/CCR/memory files were not touched."
