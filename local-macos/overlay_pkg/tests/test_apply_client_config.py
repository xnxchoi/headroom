"""apply-client-config must retarget Grok tables in place, never duplicate them."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "apply-client-config.py"

GOOD = """\
[cli]
installer = "internal"

[ui]
fork_secondary_model = "grok-4.6"
permission_mode = "always-approve"

[model.grok-build]
base_url = "http://127.0.0.1:8789/v1"

[model."grok-4.6"]
base_url = "http://127.0.0.1:8789/v1"
api_backend = "responses"

[model."grok-4.6".env_http_headers]
X-Headroom-Project = "HEADROOM_PROJECT"

[models]
default = "grok-4.6"

[mcp_servers.chrome-devtools]
command = "bunx"

[mcp_servers.headroom]
type = "http"
url = "http://127.0.0.1:8788/mcp"
"""


def _mod():
    spec = importlib.util.spec_from_file_location("apply_client_config", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _headers(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.startswith("[")]


def test_apply_grok_does_not_duplicate_existing_tables(tmp_path: Path) -> None:
    mod = _mod()
    path = tmp_path / "config.toml"
    path.write_text(GOOD, encoding="utf-8")
    mod.GROK_CONFIG = path
    mod.apply_grok()
    text = path.read_text(encoding="utf-8")
    headers = _headers(text)
    assert headers.count('[model."grok-4.6"]') == 1
    assert headers.count("[mcp_servers.headroom]") == 1
    assert headers.count("[model.grok-build]") == 1
    assert '[model."grok-4.6".env_http_headers]' in headers
    assert "env_http_headers = {" not in text
    assert 'base_url = "http://127.0.0.1:8789/v1"' in text
    import tomllib

    parsed = tomllib.loads(text)
    assert parsed["model"]["grok-4.6"]["api_backend"] == "responses"
    assert parsed["mcp_servers"]["headroom"]["url"] == "http://127.0.0.1:8788/mcp"


def test_apply_grok_is_idempotent(tmp_path: Path) -> None:
    mod = _mod()
    path = tmp_path / "config.toml"
    path.write_text(GOOD, encoding="utf-8")
    mod.GROK_CONFIG = path
    mod.apply_grok()
    first = path.read_text(encoding="utf-8")
    mod.apply_grok()
    second = path.read_text(encoding="utf-8")
    assert _headers(first) == _headers(second)
    assert _headers(second).count('[model."grok-4.6"]') == 1


def test_apply_grok_collapses_duplicate_headers(tmp_path: Path) -> None:
    mod = _mod()
    path = tmp_path / "config.toml"
    path.write_text(
        GOOD
        + """
# --- headroom:grok-4.6:start ---
[model."grok-4.6"]
base_url = "http://127.0.0.1:8789/v1"
# --- headroom:grok-4.6:end ---
""",
        encoding="utf-8",
    )
    mod.GROK_CONFIG = path
    mod.apply_grok()
    text = path.read_text(encoding="utf-8")
    assert _headers(text).count('[model."grok-4.6"]') == 1
    import tomllib

    tomllib.loads(text)
