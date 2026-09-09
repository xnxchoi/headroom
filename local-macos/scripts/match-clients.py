#!/usr/bin/env python3
"""Match this user's signed inventory clients.

Exit 0 if any match (clients present). --list prints matching command lines.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

INVENTORY = Path.home() / ".headroom" / "overlay" / "clients.json"


def pid_executable(pid: int) -> str | None:
    """Absolute path of pid's executable (kernel path, not argv0)."""
    try:
        buf = ctypes.create_string_buffer(4096)
        n = ctypes.CDLL("/usr/lib/libproc.dylib").proc_pidpath(
            ctypes.c_int(pid), buf, ctypes.c_uint32(len(buf))
        )
        if n > 0:
            return buf.value.decode()
    except (OSError, AttributeError, ValueError):
        return None
    return None


def matching_rows(
    data: dict,
    ps_stdout: str,
    uid: int | None = None,
    resolve_pid: Callable[[int], str | None] | None = None,
) -> list[str]:
    """Return `pid  command` rows whose real binary is an inventory executable.

    Prefixes are discovery-only. A sibling helper in the same directory
    (e.g. `codex-code-mode-host` next to `codex`) is not a named client.
    Bare names like `grok` are verified with proc_pidpath.
    """
    uid = int(uid if uid is not None else os.getuid())
    try:
        inv_uid = int(data.get("uid") or uid)
    except (TypeError, ValueError):
        return []
    if inv_uid != uid:
        return []

    executables: set[str] = set()
    for raw in data.get("executables") or []:
        if not raw:
            continue
        executables.add(str(raw))
        try:
            executables.add(str(Path(raw).resolve()))
        except OSError:
            pass
    if not executables:
        return []

    names = {Path(p).name for p in executables}
    names.update(str(n) for n in (data.get("names") or []) if n)
    names.update(("grok", "codex", "claude", "ChatGPT", "Claude", "Codex"))
    resolver = resolve_pid or pid_executable

    found: list[str] = []
    for line in ps_stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        try:
            proc_uid = int(parts[0])
            pid = int(parts[1])
        except ValueError:
            continue
        if proc_uid != uid:
            continue
        command = parts[2]
        argv0 = command.split(None, 1)[0]
        candidates = {argv0}
        if argv0.startswith("/"):
            try:
                candidates.add(str(Path(argv0).resolve()))
            except OSError:
                pass
        elif argv0 in names:
            real = resolver(pid)
            if real:
                candidates.add(real)
                try:
                    candidates.add(str(Path(real).resolve()))
                except OSError:
                    pass
        if candidates & executables:
            found.append(f"{pid}  {command}")
    return found


def _matches() -> list[str]:
    if not INVENTORY.is_file():
        return []
    data = json.loads(INVENTORY.read_text(encoding="utf-8"))
    proc = subprocess.run(
        ["/bin/ps", "-axo", "uid=,pid=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    return matching_rows(data, proc.stdout, uid=os.getuid())


def main() -> int:
    found = _matches()
    if "--list" in sys.argv:
        for row in found:
            print(row)
    return 0 if found else 1


if __name__ == "__main__":
    raise SystemExit(main())
