"""Stop/status/grace for the macOS overlay — shared by CLI, dashboard, stop.sh."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

OVERLAY = Path.home() / ".headroom" / "overlay"
GRACE_FILE = OVERLAY / "stop_grace_seconds"
LIFECYCLE_JSON = OVERLAY / "lifecycle.json"
MATCH = OVERLAY / "match-clients.py"
VENV_PYTHON = Path.home() / ".headroom" / "venv" / "bin" / "python"
PLIST_DIR = Path.home() / "Library" / "LaunchAgents"
LABELS = (
    "com.headroom.proxy.openai",
    "com.headroom.proxy.grok",
    "com.headroom.mcp.http",
)
LIFECYCLE_LABEL = "com.headroom.lifecycle"
PORTS = (8787, 8788, 8789)
DEFAULT_GRACE = 90
MIN_GRACE = 10
MAX_GRACE = 86400


def _uid() -> int:
    return os.getuid()


def _domain() -> str:
    return f"gui/{_uid()}"


def overlay_python() -> str:
    """Interpreter for overlay helpers. Prefer the Headroom 3.13 venv.

    Login PATH may be python.org / Homebrew 3.14, and /usr/bin/python3 is
    still 3.9 on macOS. Matching and refresh must not follow that PATH.
    """
    if VENV_PYTHON.is_file():
        return str(VENV_PYTHON)
    return "/usr/bin/python3"


def list_clients() -> list[str]:
    if not MATCH.is_file():
        return []
    result = subprocess.run(
        [overlay_python(), str(MATCH), "--list"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [ln for ln in result.stdout.splitlines() if ln.strip()]


def grace_seconds() -> int:
    try:
        raw = GRACE_FILE.read_text(encoding="utf-8").strip()
        value = int(raw)
    except (OSError, ValueError):
        value = DEFAULT_GRACE
    return max(MIN_GRACE, min(MAX_GRACE, value))


def set_grace_seconds(value: int) -> int:
    clamped = max(MIN_GRACE, min(MAX_GRACE, int(value)))
    OVERLAY.mkdir(parents=True, exist_ok=True)
    GRACE_FILE.write_text(f"{clamped}\n", encoding="utf-8")
    LIFECYCLE_JSON.write_text(
        json.dumps({"stop_grace_seconds": clamped}, indent=2) + "\n",
        encoding="utf-8",
    )
    return clamped


def _notify(title: str, body: str) -> None:
    text = " ".join(body.split())[:200]
    script = f"display notification {json.dumps(text)} with title {json.dumps(title)}"
    subprocess.run(
        ["/usr/bin/osascript", "-e", script],
        capture_output=True,
        check=False,
    )


def _port_pids() -> list[int]:
    pids: list[int] = []
    for port in PORTS:
        result = subprocess.run(
            ["/usr/sbin/lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.split():
            try:
                pids.append(int(line))
            except ValueError:
                continue
    return pids


def _ours(pid: int) -> bool:
    result = subprocess.run(
        ["/bin/ps", "-p", str(pid), "-o", "uid=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    line = result.stdout.strip()
    if not line:
        return False
    parts = line.split(None, 1)
    try:
        if int(parts[0]) != _uid():
            return False
    except ValueError:
        return False
    cmd = parts[1] if len(parts) > 1 else ""
    return ".headroom/venv" in cmd or "headroom.cli" in cmd or "headroom mcp" in cmd


def _related_pids() -> list[int]:
    """Overlay leftovers that are not the lifecycle watcher or this stop command."""
    me = os.getpid()
    parent = os.getppid()
    uid = _uid()
    result = subprocess.run(
        ["/bin/ps", "-axo", "uid=,pid=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    pids: list[int] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) < 3:
            continue
        try:
            proc_uid = int(parts[0])
            pid = int(parts[1])
        except ValueError:
            continue
        if proc_uid != uid or pid in {me, parent}:
            continue
        cmd = parts[2]
        if "headroom-lifecycle" in cmd or "match-clients.py" in cmd:
            continue
        if " overlay " in cmd or "headroom_macos_overlay" in cmd:
            continue
        if "headroom mcp serve" in cmd or "headroom.cli mcp" in cmd:
            pids.append(pid)
            continue
        if "headroom proxy" in cmd or "headroom.cli proxy" in cmd:
            pids.append(pid)
    return pids


def _job_registered(label: str) -> bool:
    result = subprocess.run(
        ["/bin/launchctl", "print", f"{_domain()}/{label}"],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def _ensure_jobs_registered() -> None:
    """Keep jobs loaded (not running) so lifecycle can start them later."""
    domain = _domain()
    for label in (*LABELS, LIFECYCLE_LABEL):
        if _job_registered(label):
            continue
        plist = PLIST_DIR / f"{label}.plist"
        if not plist.is_file():
            continue
        subprocess.run(
            ["/bin/launchctl", "bootstrap", domain, str(plist)],
            capture_output=True,
            check=False,
        )
        subprocess.run(
            ["/bin/launchctl", "enable", f"{domain}/{label}"],
            capture_output=True,
            check=False,
        )


def status() -> dict:
    listening = {}
    for port in PORTS:
        result = subprocess.run(
            ["/usr/sbin/lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            check=False,
        )
        listening[port] = "LISTEN" in result.stdout
    return {
        "grace_seconds": grace_seconds(),
        "clients": list_clients(),
        "listening": listening,
        "running": any(listening.values()),
    }


def stop() -> tuple[int, str, list[str]]:
    """Stop overlay proxies. Refuse if inventory clients are still running."""
    clients = list_clients()
    if clients:
        _notify(
            "headroom-stop",
            "Quit these Grok/ChatGPT/Claude/Codex processes first, then retry.",
        )
        return (
            409,
            "Quit these client processes first, then retry.",
            clients,
        )

    domain = _domain()
    for label in LABELS:
        subprocess.run(
            ["/bin/launchctl", "kill", "SIGTERM", f"{domain}/{label}"],
            capture_output=True,
            check=False,
        )

    deadline = time.time() + 8
    while time.time() < deadline:
        if not _port_pids() and not _related_pids():
            break
        time.sleep(0.25)

    for pid in _related_pids():
        subprocess.run(["/bin/kill", "-TERM", str(pid)], check=False)

    time.sleep(0.25)

    remaining = list(dict.fromkeys([*_port_pids(), *_related_pids()]))
    for pid in remaining:
        if _ours(pid) or pid in _related_pids():
            subprocess.run(["/bin/kill", "-KILL", str(pid)], check=False)

    leftover = [p for p in _port_pids() if _ours(p)]
    leftover.extend(p for p in _related_pids() if p not in leftover)
    _ensure_jobs_registered()
    if leftover:
        return 500, f"still listening: {leftover}", []
    _notify(
        "headroom-stop",
        "Headroom overlay stopped. It will start again when a listed client appears.",
    )
    return 0, "Headroom overlay proxies stopped.", []
