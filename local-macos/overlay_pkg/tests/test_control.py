"""Stop pipeline, grace clamp, and leftover-process targeting."""

from __future__ import annotations

from pathlib import Path

import pytest

from headroom_macos_overlay import control


@pytest.fixture
def overlay_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    overlay = tmp_path / "overlay"
    overlay.mkdir()
    monkeypatch.setattr(control, "OVERLAY", overlay)
    monkeypatch.setattr(control, "GRACE_FILE", overlay / "stop_grace_seconds")
    monkeypatch.setattr(control, "LIFECYCLE_JSON", overlay / "lifecycle.json")
    monkeypatch.setattr(control, "MATCH", overlay / "match-clients.py")
    return overlay


def test_overlay_python_prefers_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    venv_py = tmp_path / "python"
    venv_py.write_text("", encoding="utf-8")
    monkeypatch.setattr(control, "VENV_PYTHON", venv_py)
    assert control.overlay_python() == str(venv_py)


def test_overlay_python_falls_back_without_venv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(control, "VENV_PYTHON", tmp_path / "missing")
    assert control.overlay_python() == "/usr/bin/python3"


def test_list_clients_invokes_overlay_python(
    overlay_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (overlay_home / "match-clients.py").write_text("#", encoding="utf-8")
    monkeypatch.setattr(control, "overlay_python", lambda: "/opt/headroom-venv/bin/python")
    seen: list[list[str]] = []

    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        seen.append(list(argv))
        return type("R", (), {"stdout": "53816  grok\n", "returncode": 0})()

    monkeypatch.setattr(control.subprocess, "run", fake_run)
    assert control.list_clients() == ["53816  grok"]
    assert seen[0][0] == "/opt/headroom-venv/bin/python"
    assert seen[0][1] == str(control.MATCH)


def test_default_grace_is_90_seconds(overlay_home: Path) -> None:
    assert control.DEFAULT_GRACE == 90
    assert control.grace_seconds() == 90


def test_set_grace_clamps_and_persists(overlay_home: Path) -> None:
    assert control.set_grace_seconds(5) == 10
    assert control.grace_seconds() == 10
    assert control.set_grace_seconds(99) == 99
    assert (overlay_home / "stop_grace_seconds").read_text(encoding="utf-8").strip() == "99"
    assert control.set_grace_seconds(999999) == 86400


def test_stop_refuses_when_named_clients_exist(
    overlay_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        control,
        "list_clients",
        lambda: ["42  /Users/me/.grok/downloads/grok-macos-aarch64"],
    )
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(list(argv))
        return type("R", (), {"stdout": "", "returncode": 0})()

    monkeypatch.setattr(control.subprocess, "run", fake_run)
    code, message, clients = control.stop()
    assert code == 409
    assert "Quit these client processes first" in message
    assert clients[0].endswith("grok-macos-aarch64")
    assert not any("launchctl" in c[0] or (len(c) > 1 and c[1] == "kill") for c in calls)


def test_stop_terms_three_jobs_and_related_ours(
    overlay_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ports = [111, 222]
    related = [333]
    monkeypatch.setattr(control, "list_clients", lambda: [])
    monkeypatch.setattr(control, "_port_pids", lambda: list(ports))
    monkeypatch.setattr(control, "_ours", lambda pid: pid in {111, 222, 333})
    monkeypatch.setattr(control, "_related_pids", lambda: list(related))
    monkeypatch.setattr(control, "_ensure_jobs_registered", lambda: None)
    monkeypatch.setattr(control, "_notify", lambda *a, **k: None)
    now = {"t": 0.0}
    monkeypatch.setattr(control.time, "time", lambda: now["t"])

    def fake_sleep(seconds: float) -> None:
        now["t"] += seconds

    monkeypatch.setattr(control.time, "sleep", fake_sleep)

    seen: list[tuple[str, ...]] = []

    def fake_run(argv, **kwargs):  # type: ignore[no-untyped-def]
        cmd = tuple(str(x) for x in argv)
        seen.append(cmd)
        if len(cmd) >= 3 and cmd[0] == "/bin/kill":
            pid = int(cmd[2])
            if pid in ports:
                ports[:] = [p for p in ports if p != pid]
            if pid in related:
                related[:] = [p for p in related if p != pid]
        return type("R", (), {"stdout": "", "returncode": 0})()

    monkeypatch.setattr(control.subprocess, "run", fake_run)
    code, message, clients = control.stop()
    assert code == 0
    assert clients == []
    assert "stopped" in message.lower()
    labels = {
        "com.headroom.proxy.openai",
        "com.headroom.proxy.grok",
        "com.headroom.mcp.http",
    }
    term_labels = {c[-1].rsplit("/", 1)[-1] for c in seen if "SIGTERM" in c}
    assert labels <= term_labels
    assert ("/bin/kill", "-KILL", "111") in seen
    assert ("/bin/kill", "-KILL", "222") in seen
    assert ("/bin/kill", "-TERM", "333") in seen
    assert not any("bootout" in c for c in seen)


def test_related_pids_skip_self_and_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    me = 50
    monkeypatch.setattr(control.os, "getpid", lambda: me)
    monkeypatch.setattr(control.os, "getppid", lambda: 49)
    monkeypatch.setattr(control, "_uid", lambda: 501)
    ps = (
        "501 50 /Users/me/.headroom/venv/bin/python -m headroom.cli overlay stop\n"
        "501 49 /bin/zsh\n"
        "501 60 /bin/zsh /Users/me/.local/libexec/headroom-lifecycle.zsh\n"
        "501 70 /Users/me/.headroom/venv/bin/headroom mcp serve\n"
        "501 80 /usr/bin/python3 /Users/me/.headroom/overlay/match-clients.py\n"
        "502 90 /Users/me/.headroom/venv/bin/headroom mcp serve\n"
    )
    monkeypatch.setattr(
        control.subprocess,
        "run",
        lambda *a, **k: type("R", (), {"stdout": ps, "returncode": 0})(),
    )
    assert control._related_pids() == [70]
