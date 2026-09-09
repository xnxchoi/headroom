"""Client matcher must use inventory executables, not sibling binaries in the same prefix."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "match-clients.py"


def _mod():
    spec = importlib.util.spec_from_file_location("match_clients", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_exact_codex_matches():
    mod = _mod()
    inventory = {
        "uid": 501,
        "executables": ["/opt/homebrew/Caskroom/codex/0.153.4/bin/codex"],
        "prefixes": ["/opt/homebrew/Caskroom/codex/0.153.4/bin"],
    }
    ps = "  501  42 /opt/homebrew/Caskroom/codex/0.153.4/bin/codex exec\n"
    rows = mod.matching_rows(inventory, ps, uid=501)
    assert rows == ["42  /opt/homebrew/Caskroom/codex/0.153.4/bin/codex exec"]


def test_helper_in_same_prefix_does_not_match():
    mod = _mod()
    inventory = {
        "uid": 501,
        "executables": ["/opt/homebrew/Caskroom/codex/0.153.4/bin/codex"],
        "prefixes": ["/opt/homebrew/Caskroom/codex/0.153.4/bin"],
    }
    ps = "  501  99128 /opt/homebrew/Caskroom/codex/0.153.4/bin/codex-code-mode-host\n"
    assert mod.matching_rows(inventory, ps, uid=501) == []


def test_other_uid_ignored():
    mod = _mod()
    inventory = {
        "uid": 501,
        "executables": ["/Applications/ChatGPT.app/Contents/MacOS/ChatGPT"],
        "prefixes": ["/Applications/ChatGPT.app/Contents/MacOS"],
    }
    ps = "  502  9 /Applications/ChatGPT.app/Contents/MacOS/ChatGPT\n"
    assert mod.matching_rows(inventory, ps, uid=501) == []


def test_unrelated_name_in_scan_dir_does_not_match():
    mod = _mod()
    inventory = {
        "uid": 501,
        "executables": ["/Users/me/.grok/downloads/grok-macos-aarch64"],
        "prefixes": ["/Users/me/.grok/downloads"],
    }
    ps = "  501  3 /Users/me/.grok/downloads/apgujeongrok\n"
    assert mod.matching_rows(inventory, ps, uid=501) == []


def test_bare_grok_name_verified_via_resolver(tmp_path: Path):
    mod = _mod()
    real = tmp_path / "downloads" / "grok-macos-aarch64"
    real.parent.mkdir()
    real.write_bytes(b"x")
    inventory = {
        "uid": 501,
        "executables": [str(real)],
        "names": ["grok"],
        "prefixes": [str(real.parent)],
    }
    ps = "  501  7 grok --version\n"
    rows = mod.matching_rows(
        inventory, ps, uid=501, resolve_pid=lambda pid: str(real) if pid == 7 else None
    )
    assert rows == [f"7  grok --version"]


def test_bare_name_without_real_path_does_not_match():
    mod = _mod()
    inventory = {
        "uid": 501,
        "executables": ["/Users/me/.grok/downloads/grok-macos-aarch64"],
        "names": ["grok"],
    }
    ps = "  501  7 grok --version\n"
    assert mod.matching_rows(inventory, ps, uid=501, resolve_pid=lambda _pid: None) == []


def test_symlink_argv0_resolves_to_inventory(tmp_path: Path):
    mod = _mod()
    real = tmp_path / "downloads" / "grok-macos-aarch64"
    real.parent.mkdir()
    real.write_bytes(b"x")
    real.chmod(0o755)
    link = tmp_path / "bin" / "grok"
    link.parent.mkdir()
    link.symlink_to(real)
    inventory = {
        "uid": 501,
        "executables": [str(real)],
        "prefixes": [str(real.parent)],
    }
    ps = f"  501  7 {link} --version\n"
    rows = mod.matching_rows(inventory, ps, uid=501)
    assert len(rows) == 1
    assert rows[0].startswith("7  ")
