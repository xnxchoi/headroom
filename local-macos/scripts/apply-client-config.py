#!/usr/bin/env python3
"""Apply reversible client routing for the local-macos overlay."""

from __future__ import annotations

import json
import re
from pathlib import Path

HOME = Path.home()
GROK_CONFIG = HOME / ".grok" / "config.toml"
CODEX_CONFIG = HOME / ".codex" / "config.toml"
CLAUDE_SETTINGS = HOME / ".claude" / "settings.json"

GROK_MCP_START = "# --- Headroom MCP server ---"
GROK_MCP_END = "# --- end Headroom MCP server ---"
GROK_MODEL_START = "# --- headroom:grok-4.6:start ---"
GROK_MODEL_END = "# --- headroom:grok-4.6:end ---"
CODEX_TOP = "# --- Headroom proxy (auto-injected by headroom wrap codex) ---"
CODEX_END = "# --- end Headroom ---"
CODEX_MCP_START = "# --- Headroom MCP server ---"
CODEX_MCP_END = "# --- end Headroom MCP server ---"

OPENAI_PROXY = "http://127.0.0.1:8787/v1"
GROK_PROXY = "http://127.0.0.1:8789/v1"
MCP_URL = "http://127.0.0.1:8788/mcp"


def _strip_block(content: str, start: str, end: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)
    content = pattern.sub("", content)
    return re.sub(r"\n{3,}", "\n\n", content).strip() + ("\n" if content.strip() else "")


def _retarget_table_base_url(content: str, header: str, base_url: str) -> str:
    match = re.search(rf"(?m)^{re.escape(header)}\s*$", content)
    if match is None:
        return content
    start = match.end()
    next_table = re.search(r"(?m)^\[", content[start:])
    end = start + next_table.start() if next_table else len(content)
    section = content[start:end]
    if re.search(r'(?m)^[ \t]*base_url[ \t]*=', section):
        section = re.sub(
            r'(?m)^(?P<indent>[ \t]*)base_url[ \t]*=.*$',
            lambda m: f'{m.group("indent")}base_url = "{base_url}"',
            section,
            count=1,
        )
    else:
        section = f'\nbase_url = "{base_url}"' + section
    return content[:start] + section + content[end:]


def _upsert_block(content: str, start: str, end: str, block: str) -> str:
    content = _strip_block(content, start, end)
    if content.strip():
        return content.rstrip() + "\n\n" + block.strip() + "\n"
    return block.strip() + "\n"


_TABLE_HEADER = re.compile(r"(?m)^(\[[^]]+\])\s*$")


def _iter_tables(content: str) -> list[tuple[str, int, int]]:
    matches = list(_TABLE_HEADER.finditer(content))
    spans: list[tuple[str, int, int]] = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        spans.append((match.group(1), match.start(), end))
    return spans


def _remove_duplicate_tables(content: str) -> str:
    """Keep the first copy of each `[table]`. Array tables `[[x]]` may repeat."""
    seen: set[str] = set()
    parts: list[str] = []
    last = 0
    for header, start, end in _iter_tables(content):
        parts.append(content[last:start])
        if header.startswith("[[") or header not in seen:
            seen.add(header)
            parts.append(content[start:end])
        last = end
    parts.append(content[last:])
    return "".join(parts)


def _has_table(content: str, header: str) -> bool:
    return re.search(rf"(?m)^{re.escape(header)}\s*$", content) is not None


def _set_table_key(content: str, header: str, key: str, literal: str) -> str:
    match = re.search(rf"(?m)^{re.escape(header)}\s*$", content)
    if match is None:
        return content
    start = match.end()
    next_table = re.search(r"(?m)^\[", content[start:])
    end = start + next_table.start() if next_table else len(content)
    section = content[start:end]
    if re.search(rf"(?m)^[ \t]*{re.escape(key)}[ \t]*=", section):
        section = re.sub(
            rf"(?m)^(?P<indent>[ \t]*){re.escape(key)}[ \t]*=.*$",
            lambda m: f"{m.group('indent')}{key} = {literal}",
            section,
            count=1,
        )
    else:
        section = f"\n{key} = {literal}" + section
    return content[:start] + section + content[end:]


def _insert_after_header(content: str, after_header: str, block: str) -> str:
    match = re.search(rf"(?m)^{re.escape(after_header)}\s*$", content)
    if match is None:
        return content.rstrip() + "\n\n" + block.strip() + "\n"
    start = match.end()
    next_table = re.search(r"(?m)^\[", content[start:])
    end = start + next_table.start() if next_table else len(content)
    return content[:end].rstrip() + "\n\n" + block.strip() + "\n" + content[end:]


def apply_grok() -> None:
    GROK_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    content = GROK_CONFIG.read_text(encoding="utf-8") if GROK_CONFIG.exists() else ""

    content = _strip_block(content, GROK_MODEL_START, GROK_MODEL_END)
    content = _strip_block(content, GROK_MCP_START, GROK_MCP_END)
    content = _remove_duplicate_tables(content)

    parts: list[str] = []
    current_header = ""
    for line in content.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_header = stripped
        if current_header == "[models]" and re.match(r"^[ \t]*base_url[ \t]*=", line):
            continue
        parts.append(line)
    content = "".join(parts)

    if _has_table(content, "[model.grok-build]"):
        content = _retarget_table_base_url(content, "[model.grok-build]", GROK_PROXY)
    else:
        content = _insert_after_header(
            content,
            "[ui]",
            f'[model.grok-build]\nbase_url = "{GROK_PROXY}"\n',
        )

    grok_header = '[model."grok-4.6"]'
    headers_header = '[model."grok-4.6".env_http_headers]'
    if _has_table(content, grok_header):
        content = _retarget_table_base_url(content, grok_header, GROK_PROXY)
        content = _set_table_key(content, grok_header, "api_backend", '"responses"')
        content = re.sub(
            r"(?m)^[ \t]*env_http_headers[ \t]*=.*\n?",
            "",
            content,
        )
        if not _has_table(content, headers_header):
            content = _insert_after_header(
                content,
                grok_header,
                f"{headers_header}\nX-Headroom-Project = \"HEADROOM_PROJECT\"\n",
            )
    else:
        content = _insert_after_header(
            content,
            "[model.grok-build]",
            (
                f"{grok_header}\n"
                f'base_url = "{GROK_PROXY}"\n'
                'api_backend = "responses"\n\n'
                f"{headers_header}\n"
                'X-Headroom-Project = "HEADROOM_PROJECT"\n'
            ),
        )

    mcp_header = "[mcp_servers.headroom]"
    if _has_table(content, mcp_header):
        content = _set_table_key(content, mcp_header, "type", '"http"')
        content = _set_table_key(content, mcp_header, "url", f'"{MCP_URL}"')
    else:
        content = _insert_after_header(
            content,
            "[mcp_servers.chrome-devtools]",
            f'{mcp_header}\ntype = "http"\nurl = "{MCP_URL}"\n',
        )

    content = _remove_duplicate_tables(content)
    content = re.sub(r"\n{3,}", "\n\n", content).strip() + "\n"
    GROK_CONFIG.write_text(content, encoding="utf-8")
    print(f"updated {GROK_CONFIG}")


def apply_codex() -> None:
    from headroom.cli.wrap import _inject_codex_provider_config

    _inject_codex_provider_config(8787)
    content = CODEX_CONFIG.read_text(encoding="utf-8") if CODEX_CONFIG.exists() else ""
    mcp_block = f"""{CODEX_MCP_START}
[mcp_servers.headroom]
url = "{MCP_URL}"
{CODEX_MCP_END}
"""
    content = _upsert_block(content, CODEX_MCP_START, CODEX_MCP_END, mcp_block)
    CODEX_CONFIG.write_text(content if content.endswith("\n") else content + "\n", encoding="utf-8")
    print(f"updated {CODEX_CONFIG}")


def apply_claude() -> None:
    CLAUDE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    if CLAUDE_SETTINGS.exists():
        data = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
    else:
        data = {}
    env = data.get("env")
    if not isinstance(env, dict):
        env = {}
    env["ANTHROPIC_BASE_URL"] = "http://127.0.0.1:8787"
    data["env"] = env
    CLAUDE_SETTINGS.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"updated {CLAUDE_SETTINGS}")


def main() -> None:
    apply_grok()
    apply_codex()
    apply_claude()


if __name__ == "__main__":
    main()
