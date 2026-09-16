#!/bin/zsh
emulate -LR zsh
setopt NO_UNSET PIPE_FAIL

readonly DOMAIN="gui/$(/usr/bin/id -u)"
readonly PORT_OPENAI=8787
readonly PORT_GROK=8789
readonly PORT_MCP=8788
readonly POLL_SECONDS=2
readonly GRACE_FILE="$HOME/.headroom/overlay/stop_grace_seconds"
readonly DEFAULT_GRACE_SECONDS=90
readonly READY_TIMEOUT_SECONDS=60
readonly START_RETRY_SECONDS=15
readonly STATE_DIR="$HOME/.headroom/lifecycle"
readonly PAUSE_FILE="${STATE_DIR}/paused"
readonly PLIST_DIR="$HOME/Library/LaunchAgents"
readonly OVERLAY_PYTHON="$HOME/.headroom/venv/bin/python"

typeset -a JOBS
JOBS=(
    "com.headroom.proxy.openai"
    "com.headroom.proxy.grok"
    "com.headroom.mcp.http"
)

/bin/mkdir -p "$STATE_DIR"

log() {
    print -r -- "$(/bin/date '+%Y-%m-%d %H:%M:%S') $*"
}

stop_grace_seconds() {
    local g
    g="$(/bin/cat "$GRACE_FILE" 2>/dev/null || true)"
    if [[ "$g" != <-> ]] || (( g < 10 || g > 86400 )); then
        g="$DEFAULT_GRACE_SECONDS"
    fi
    print -r -- "$g"
}

overlay_python() {
    if [[ -x "$OVERLAY_PYTHON" ]]; then
        print -r -- "$OVERLAY_PYTHON"
    else
        print -r -- /usr/bin/python3
    fi
}

clients_present() {
    "$(overlay_python)" "$HOME/.headroom/overlay/match-clients.py" >/dev/null 2>&1
}

port_listening() {
    /usr/sbin/lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1
}

services_up() {
    port_listening "$PORT_OPENAI" && port_listening "$PORT_GROK" && port_listening "$PORT_MCP"
}

job_registered() {
    /bin/launchctl print "${DOMAIN}/$1" >/dev/null 2>&1
}

ensure_registered() {
    local label="$1"
    local plist="${PLIST_DIR}/${label}.plist"
    local attempt
    if job_registered "$label"; then
        return 0
    fi
    if [[ ! -f "$plist" ]]; then
        log "Missing plist ${plist}"
        return 1
    fi
    /bin/launchctl enable "${DOMAIN}/${label}" >/dev/null 2>&1 || true
    for attempt in {1..30}; do
        /bin/launchctl bootstrap "$DOMAIN" "$plist" >/dev/null 2>&1 || true
        if job_registered "$label"; then
            return 0
        fi
        /bin/sleep 0.5
    done
    log "Could not register ${label}"
    return 1
}

job_port() {
    case "$1" in
        com.headroom.proxy.openai) print -r -- "$PORT_OPENAI" ;;
        com.headroom.proxy.grok) print -r -- "$PORT_GROK" ;;
        com.headroom.mcp.http) print -r -- "$PORT_MCP" ;;
    esac
}

start_missing() {
    local label port
    for label in "${JOBS[@]}"; do
        ensure_registered "$label" || return 1
        port="$(job_port "$label")"
        if port_listening "$port"; then
            continue
        fi
        log "Starting ${label} (port ${port} not listening)."
        /bin/launchctl kickstart "${DOMAIN}/${label}" >/dev/null 2>&1 || true
    done
    local i
    for (( i = 0; i < READY_TIMEOUT_SECONDS * 2; i++ )); do
        if services_up; then
            log "Headroom listening on ${PORT_OPENAI}/${PORT_GROK}/${PORT_MCP}."
            return 0
        fi
        /bin/sleep 0.5
    done
    log "Headroom ports not all up yet (will retry, not killing listeners)."
    return 1
}

stop_services() {
    local label
    for label in "${JOBS[@]}"; do
        /bin/launchctl kill SIGTERM "${DOMAIN}/${label}" >/dev/null 2>&1 || true
    done
    local i
    for (( i = 0; i < 20; i++ )); do
        if ! services_up; then
            break
        fi
        /bin/sleep 0.5
    done
    for label in "${JOBS[@]}"; do
        /bin/launchctl kill SIGKILL "${DOMAIN}/${label}" >/dev/null 2>&1 || true
    done
    log "Headroom stopped."
}

watcher_shutdown() {
    log "Lifecycle watcher terminating."
    if clients_present; then
        log "Tracked clients still present; leaving Headroom running."
        exit 0
    fi
    stop_services
    exit 0
}

trap 'watcher_shutdown' TERM INT HUP

integer idle_since=0
integer now=0
integer last_start_attempt=0
integer running=0

log "Lifecycle watcher started (idle grace $(stop_grace_seconds)s)."

while true; do
    if [[ -e "$PAUSE_FILE" ]]; then
        if services_up; then
            stop_services
        fi
        idle_since=0
        running=0
        /bin/sleep "$POLL_SECONDS"
        continue
    fi

    if clients_present; then
        idle_since=0
        if services_up; then
            running=1
        else
            now="$(/bin/date +%s)"
            if (( now - last_start_attempt >= START_RETRY_SECONDS )); then
                last_start_attempt="$now"
                start_missing || true
                if services_up; then
                    running=1
                fi
            fi
        fi
    elif (( running )) || services_up; then
        now="$(/bin/date +%s)"
        if (( idle_since == 0 )); then
            idle_since="$now"
            log "No tracked clients remain; shutdown grace $(stop_grace_seconds)s started."
        elif (( now - idle_since >= $(stop_grace_seconds) )); then
            stop_services
            idle_since=0
            running=0
        fi
    else
        idle_since=0
        running=0
    fi

    /bin/sleep "$POLL_SECONDS"
done
