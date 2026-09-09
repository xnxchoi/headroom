"""Dashboard injection stays in the overlay package, not Headroom templates."""

from __future__ import annotations

from headroom_macos_overlay import proxy_ext


def test_inject_markup_is_self_contained() -> None:
    html = proxy_ext.INJECT.decode("utf-8")
    assert 'id="macos-overlay-panel"' in html
    assert "/overlay/lifecycle" in html
    assert "/overlay/stop" in html
    assert "Stop grace" in html
    assert "Stop Headroom" in html
    assert "http://127.0.0.1:8789/dashboard" in html
    assert "location.port" in html


def test_html_injection_rewrites_body_once() -> None:
    page = b"<html><body><h1>Dashboard</h1></body></html>"
    out = proxy_ext.inject_dashboard_html(page)
    assert out.count(b'id="macos-overlay-panel"') == 1
    assert out.endswith(b"</body></html>")
    assert b"<h1>Dashboard</h1>" in out
