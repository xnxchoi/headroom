#!/usr/bin/env python3
"""Render LaunchAgent plists for the local-macos overlay."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from xml.sax.saxutils import escape

HOME = Path.home()
HEADROOM = HOME / ".headroom" / "venv" / "bin" / "headroom"
VENV_PYTHON = HOME / ".headroom" / "venv" / "bin" / "python"
LOG_DIR = HOME / "Library" / "Logs" / "headroom"
AGENT_DIR = HOME / "Library" / "LaunchAgents"
STOCK_PROXY_PLIST = AGENT_DIR / "com.headroom.proxy.plist"


def overlay_python() -> str:
    if VENV_PYTHON.is_file():
        return str(VENV_PYTHON)
    return "/usr/bin/python3"


def retire_stock_proxy_plist() -> None:
    """Keep the pre-overlay pythogoras LaunchAgent from grabbing port 8787."""
    if not STOCK_PROXY_PLIST.is_file():
        return
    backup_dir = HOME / ".headroom" / "overlay-backup" / "disabled-stock-proxy"
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / "com.headroom.proxy.plist"
    if not dest.exists():
        shutil.copy2(STOCK_PROXY_PLIST, dest)
    STOCK_PROXY_PLIST.unlink()
    print(f"retired leftover {STOCK_PROXY_PLIST} -> {dest}")


def plist(label: str, args: list[str], env: dict[str, str], stdout: str, stderr: str) -> str:
    arg_xml = "\n".join(f"        <string>{escape(a)}</string>" for a in args)
    env_xml = "\n".join(
        f"        <key>{escape(k)}</key>\n        <string>{escape(v)}</string>"
        for k, v in env.items()
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{escape(label)}</string>
    <key>ProgramArguments</key>
    <array>
{arg_xml}
    </array>
    <key>EnvironmentVariables</key>
    <dict>
{env_xml}
    </dict>
    <key>WorkingDirectory</key>
    <string>{escape(str(HOME))}</string>
    <key>StandardOutPath</key>
    <string>{escape(stdout)}</string>
    <key>StandardErrorPath</key>
    <string>{escape(stderr)}</string>
    <key>ProcessType</key>
    <string>Adaptive</string>
    <key>ThrottleInterval</key>
    <integer>10</integer>
</dict>
</plist>
"""


def refresh_agent_plist(script: Path) -> str:
    watches = [
        str(HOME / "Applications"),
        "/Applications",
        str(HOME / ".local" / "bin"),
        str(HOME / ".grok" / "bin"),
        str(HOME / ".grok" / "downloads"),
        "/opt/homebrew/bin",
        "/opt/homebrew/Caskroom",
    ]
    watch_xml = "\n".join(f"        <string>{escape(p)}</string>" for p in watches)
    python = overlay_python()
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.headroom.clients-refresh</string>
    <key>ProgramArguments</key>
    <array>
        <string>{escape(python)}</string>
        <string>{escape(str(script))}</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>{escape(str(HOME))}</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:{escape(str(HOME / ".local/bin"))}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>6</integer>
        <key>Minute</key>
        <integer>20</integer>
    </dict>
    <key>WatchPaths</key>
    <array>
{watch_xml}
    </array>
    <key>ThrottleInterval</key>
    <integer>300</integer>
    <key>StandardOutPath</key>
    <string>{escape(str(HOME / "Library/Logs/headroom/clients-refresh.log"))}</string>
    <key>StandardErrorPath</key>
    <string>{escape(str(HOME / "Library/Logs/headroom/clients-refresh-error.log"))}</string>
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
"""


def lifecycle_plist(script: Path) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.headroom.lifecycle</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>{escape(str(script))}</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>HOME</key>
        <string>{escape(str(HOME))}</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:{escape(str(HOME / ".headroom/venv/bin"))}</string>
    </dict>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ProcessType</key>
    <string>Background</string>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>StandardOutPath</key>
    <string>{escape(str(HOME / "Library/Logs/headroom-lifecycle.log"))}</string>
    <key>StandardErrorPath</key>
    <string>{escape(str(HOME / "Library/Logs/headroom-lifecycle.error.log"))}</string>
</dict>
</plist>
"""


def _link_headroom_cli() -> None:
    if not HEADROOM.is_file():
        return
    dest = HOME / ".local" / "bin" / "headroom"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        if dest.resolve() == HEADROOM.resolve():
            return
        dest.unlink()
    elif dest.exists():
        print(f"skip {dest}: exists and is not a symlink")
        return
    dest.symlink_to(HEADROOM)
    print(f"wrote {dest} -> {HEADROOM}")


def main() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    AGENT_DIR.mkdir(parents=True, exist_ok=True)
    retire_stock_proxy_plist()
    _link_headroom_cli()
    headroom = str(HEADROOM)
    common_env = {
        "HOME": str(HOME),
        "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:" + str(HOME / ".headroom/venv/bin"),
        "HEADROOM_OUTPUT_SHAPER": "1",
        "HEADROOM_KOMPRESS_BACKEND": "onnx_coreml",
        "HEADROOM_KOMPRESS_TIME_BUDGET_SECONDS": "5",
        "HEADROOM_KOMPRESS_ACQUIRE_TIMEOUT_SECONDS": "2",
        "HEADROOM_SAVINGS_PROFILE": "coding",
        "HEADROOM_HOST": "127.0.0.1",
        "HEADROOM_PROXY_EXTENSIONS": "macos-overlay",
    }

    jobs = {
        "com.headroom.proxy.openai": plist(
            "com.headroom.proxy.openai",
            [
                headroom,
                "proxy",
                "--host",
                "127.0.0.1",
                "--port",
                "8787",
                "--memory",
                "--learn",
                "--proxy-extension",
                "macos-overlay",
            ],
            {**common_env, "HEADROOM_PORT": "8787"},
            str(LOG_DIR / "proxy-openai.log"),
            str(LOG_DIR / "proxy-openai-error.log"),
        ),
        "com.headroom.proxy.grok": plist(
            "com.headroom.proxy.grok",
            [
                headroom,
                "proxy",
                "--host",
                "127.0.0.1",
                "--port",
                "8789",
                "--memory",
                "--learn",
                "--proxy-extension",
                "macos-overlay",
            ],
            {
                **common_env,
                "HEADROOM_PORT": "8789",
                "OPENAI_TARGET_API_URL": "https://cli-chat-proxy.grok.com",
                "HEADROOM_SAVINGS_PATH": str(HOME / ".headroom/proxy_savings.grok.json"),
            },
            str(LOG_DIR / "proxy-grok.log"),
            str(LOG_DIR / "proxy-grok-error.log"),
        ),
        "com.headroom.mcp.http": plist(
            "com.headroom.mcp.http",
            [
                headroom,
                "mcp",
                "serve",
                "--transport",
                "http",
                "--host",
                "127.0.0.1",
                "--port",
                "8788",
                "--path",
                "/mcp",
                "--proxy-url",
                "http://127.0.0.1:8787",
            ],
            {**common_env, "HEADROOM_PROXY_URL": "http://127.0.0.1:8787"},
            str(LOG_DIR / "mcp-http.log"),
            str(LOG_DIR / "mcp-http-error.log"),
        ),
    }
    for label, body in jobs.items():
        path = AGENT_DIR / f"{label}.plist"
        path.write_text(body, encoding="utf-8")
        os.chmod(path, 0o644)
        print(f"wrote {path}")

    repo_root = Path(__file__).resolve().parents[2]
    script = HOME / ".local/libexec/headroom-lifecycle.zsh"
    script.parent.mkdir(parents=True, exist_ok=True)
    src = repo_root / "local-macos" / "libexec" / "headroom-lifecycle.zsh"
    script.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    os.chmod(script, 0o700)
    life = AGENT_DIR / "com.headroom.lifecycle.plist"
    life.write_text(lifecycle_plist(script), encoding="utf-8")
    os.chmod(life, 0o644)
    print(f"wrote {life}")
    print(f"wrote {script}")

    overlay = HOME / ".headroom" / "overlay"
    overlay.mkdir(parents=True, exist_ok=True)
    matcher = repo_root / "local-macos" / "scripts" / "match-clients.py"
    dest_matcher = overlay / "match-clients.py"
    dest_matcher.write_text(matcher.read_text(encoding="utf-8"), encoding="utf-8")
    os.chmod(dest_matcher, 0o755)
    refresh = repo_root / "local-macos" / "scripts" / "refresh-clients.py"
    refresh_plist = AGENT_DIR / "com.headroom.clients-refresh.plist"
    refresh_plist.write_text(
        refresh_agent_plist(refresh),
        encoding="utf-8",
    )
    os.chmod(refresh_plist, 0o644)
    print(f"wrote {dest_matcher}")
    print(f"wrote {refresh_plist}")

    stop_src = repo_root / "local-macos" / "scripts" / "stop.sh"
    stop_bin = HOME / ".local" / "bin" / "headroom-stop"
    stop_bin.parent.mkdir(parents=True, exist_ok=True)
    stop_bin.write_text(stop_src.read_text(encoding="utf-8"), encoding="utf-8")
    os.chmod(stop_bin, 0o755)
    print(f"wrote {stop_bin}")

    grace = HOME / ".headroom" / "overlay" / "stop_grace_seconds"
    grace.parent.mkdir(parents=True, exist_ok=True)
    current = ""
    if grace.exists():
        current = grace.read_text(encoding="utf-8").strip()
    if not current or current == "5400":
        grace.write_text("90\n", encoding="utf-8")

    aliases = overlay / "aliases.zsh"
    aliases.write_text(
        '# Headroom overlay stop. Source from ~/.zshrc if you want the alias:\n'
        '#   source ~/.headroom/overlay/aliases.zsh\n'
        'alias headroom-stop="${HOME}/.local/bin/headroom-stop"\n',
        encoding="utf-8",
    )
    print(f"wrote {aliases}")


if __name__ == "__main__":
    main()
