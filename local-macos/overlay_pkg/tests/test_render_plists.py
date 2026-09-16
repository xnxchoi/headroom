"""render-plists uses the overlay venv and retires the stock pythogoras agent."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "render-plists.py"


def _mod():
    spec = importlib.util.spec_from_file_location("render_plists", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_overlay_python_prefers_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _mod()
    venv_py = tmp_path / "python"
    venv_py.write_text("", encoding="utf-8")
    monkeypatch.setattr(mod, "VENV_PYTHON", venv_py)
    assert mod.overlay_python() == str(venv_py)


def test_overlay_python_falls_back(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _mod()
    monkeypatch.setattr(mod, "VENV_PYTHON", tmp_path / "missing")
    assert mod.overlay_python() == "/usr/bin/python3"


def test_retire_stock_proxy_plist(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    mod = _mod()
    home = tmp_path / "home"
    agents = home / "Library" / "LaunchAgents"
    agents.mkdir(parents=True)
    plist = agents / "com.headroom.proxy.plist"
    plist.write_text("pythogoras-proxy", encoding="utf-8")
    monkeypatch.setattr(mod, "HOME", home)
    monkeypatch.setattr(mod, "STOCK_PROXY_PLIST", plist)
    mod.retire_stock_proxy_plist()
    dest = home / ".headroom" / "overlay-backup" / "disabled-stock-proxy" / "com.headroom.proxy.plist"
    assert not plist.exists()
    assert dest.read_text(encoding="utf-8") == "pythogoras-proxy"
