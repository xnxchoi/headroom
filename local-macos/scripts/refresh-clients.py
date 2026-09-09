#!/usr/bin/env python3
"""Discover signed Grok / ChatGPT / Codex / Claude binaries into clients.json."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
REPO = Path(__file__).resolve().parents[1]
PROVIDERS = REPO / "providers.json"
OUT_DIR = HOME / ".headroom" / "overlay"
OUT = OUT_DIR / "clients.json"


def _expand(p: str) -> Path:
    return Path(os.path.expanduser(p)).resolve()


def _codesign(path: Path) -> dict[str, str]:
    result = subprocess.run(
        ["/usr/bin/codesign", "-dv", "--verbose=4", str(path)],
        capture_output=True,
        text=True,
    )
    info: dict[str, str] = {}
    for line in (result.stderr + result.stdout).splitlines():
        if line.startswith("Identifier="):
            info["identifier"] = line.split("=", 1)[1].strip()
        elif line.startswith("TeamIdentifier="):
            info["team_id"] = line.split("=", 1)[1].strip()
    return info


def _app_executable(app: Path) -> Path | None:
    plist = app / "Contents" / "Info.plist"
    if not plist.exists():
        return None
    result = subprocess.run(
        ["/usr/bin/defaults", "read", str(plist), "CFBundleExecutable"],
        capture_output=True,
        text=True,
    )
    name = result.stdout.strip()
    if not name:
        return None
    exe = app / "Contents" / "MacOS" / name
    return exe if exe.exists() else None


def _accept(path: Path, team_id: str, identifiers: list[str]) -> dict | None:
    if not path.is_file():
        return None
    try:
        path = path.resolve()
    except OSError:
        return None
    sign = _codesign(path)
    if sign.get("team_id") != team_id:
        return None
    ident = sign.get("identifier", "")
    if ident not in identifiers:
        return None
    return {
        "path": str(path),
        "identifier": ident,
        "team_id": team_id,
        "comm": path.name,
    }


def discover() -> dict:
    spec = json.loads(PROVIDERS.read_text(encoding="utf-8"))
    uid = os.getuid()
    clients: list[dict] = []
    seen: set[str] = set()

    def add(provider_id: str, kind: str, rec: dict | None) -> None:
        if rec is None or rec["path"] in seen:
            return
        seen.add(rec["path"])
        clients.append({"provider": provider_id, "kind": kind, **rec})

    for provider in spec["providers"]:
        pid = provider["id"]
        team = provider["team_id"]
        idents = list(provider.get("identifiers") or [])
        for app in provider.get("apps") or []:
            app_path = _expand(app)
            exe = _app_executable(app_path) if app_path.exists() else None
            if exe:
                add(pid, "desktop", _accept(exe, team, idents))
        for name in provider.get("which") or []:
            found = shutil.which(name)
            if found:
                add(pid, "cli", _accept(Path(found), team, idents))
        for raw_dir in provider.get("scan_dirs") or []:
            directory = _expand(raw_dir)
            if not directory.is_dir():
                continue
            for child in directory.iterdir():
                target = child
                if child.is_symlink():
                    try:
                        target = child.resolve()
                    except OSError:
                        continue
                add(pid, "cli", _accept(target, team, idents))

    prefixes = sorted({str(Path(c["path"]).parent) for c in clients})
    names = {c["comm"] for c in clients}
    names.update(Path(c["path"]).name for c in clients)
    for provider in spec["providers"]:
        names.update(provider.get("which") or [])
        for app in provider.get("apps") or []:
            names.add(Path(app).stem)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "uid": uid,
        "executables": sorted(c["path"] for c in clients),
        "prefixes": prefixes,
        "names": sorted(n for n in names if n),
        "clients": clients,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data = discover()
    OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(data['clients'])} signed clients)")
    for client in data["clients"]:
        print(f"  {client['provider']:10} {client['kind']:8} {client['path']}")


if __name__ == "__main__":
    main()
