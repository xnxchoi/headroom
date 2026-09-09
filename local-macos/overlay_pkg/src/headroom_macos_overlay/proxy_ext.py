"""Inject overlay controls into the stock dashboard without editing Headroom."""

from __future__ import annotations

from typing import Any

from starlette.requests import Request

INJECT = b"""
<div id="macos-overlay-panel" style="position:fixed;right:16px;bottom:16px;z-index:50;max-width:20rem;background:#111827;border:1px solid #1f2937;border-radius:12px;padding:12px 14px;font:13px/1.4 system-ui,sans-serif;color:#e5e7eb;box-shadow:0 8px 24px rgba(0,0,0,.4)">
  <div style="font-weight:600;margin-bottom:6px">macOS overlay</div>
  <p id="macos-overlay-which" style="margin:0 0 6px;font-size:12px;color:#9ca3af"></p>
  <p style="margin:0 0 8px;font-size:12px"><a id="macos-overlay-other" href="http://127.0.0.1:8789/dashboard" style="color:#67e8f9">Grok dashboard (8789)</a></p>
  <p style="margin:0 0 8px;font-size:12px;color:#9ca3af">Idle stop after the last listed Grok/ChatGPT/Claude/Codex process quits.</p>
  <label style="display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:8px">
    <span>Stop grace (sec)</span>
    <input id="macos-overlay-grace" type="number" min="10" max="86400" style="width:5.5rem;background:#0b0f14;border:1px solid #374151;border-radius:6px;color:#e5e7eb;padding:4px 6px">
  </label>
  <button id="macos-overlay-save" type="button" style="width:100%;margin-bottom:6px;background:#164e63;color:#fff;border:0;border-radius:6px;padding:6px 8px;cursor:pointer">Save grace</button>
  <button id="macos-overlay-stop" type="button" style="width:100%;background:#7f1d1d;color:#fff;border:0;border-radius:6px;padding:6px 8px;cursor:pointer">Stop Headroom</button>
  <p id="macos-overlay-msg" style="margin:8px 0 0;font-size:12px;color:#9ca3af;white-space:pre-wrap"></p>
</div>
<script>
(function () {
  const msg = document.getElementById('macos-overlay-msg');
  const grace = document.getElementById('macos-overlay-grace');
  const grokDash = location.port === '8789';
  document.getElementById('macos-overlay-which').textContent = grokDash
    ? 'This dashboard is Grok (8789). Request rows and cache reads live here.'
    : 'This dashboard is ChatGPT / Codex / Claude (8787). Grok is a separate proxy.';
  const other = document.getElementById('macos-overlay-other');
  if (grokDash) {
    other.href = 'http://127.0.0.1:8787/dashboard';
    other.textContent = 'ChatGPT / Codex / Claude (8787)';
  }
  function say(t, err) { msg.style.color = err ? '#fca5a5' : '#9ca3af'; msg.textContent = t; }
  fetch('/overlay/lifecycle').then(r => r.json()).then(d => {
    grace.value = d.grace_seconds;
    const n = (d.clients || []).length;
    if (n) say(n + ' listed client(s) running; Stop will refuse until they quit.');
  }).catch(() => {});
  document.getElementById('macos-overlay-save').onclick = async () => {
    const r = await fetch('/overlay/lifecycle', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify({grace_seconds: Number(grace.value)})});
    const d = await r.json();
    say(r.ok ? ('Grace set to ' + d.grace_seconds + 's') : (d.detail || 'save failed'), !r.ok);
  };
  document.getElementById('macos-overlay-stop').onclick = async () => {
    const r = await fetch('/overlay/stop', {method:'POST'});
    const d = await r.json();
    if (r.status === 409) {
      say((d.detail || 'Quit clients first') + '\\n' + (d.clients || []).join('\\n'), true);
      return;
    }
    say(d.detail || (r.ok ? 'Stopped' : 'Stop failed'), !r.ok);
  };
})();
</script>
"""


def inject_dashboard_html(body: bytes) -> bytes:
    if b"</body>" in body:
        return body.replace(b"</body>", INJECT + b"</body>", 1)
    return body


def _loopback(request: Any) -> None:
    from fastapi import HTTPException

    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="loopback only")


def install(app: Any, config: Any) -> None:
    from fastapi.responses import JSONResponse, Response
    from starlette.middleware.base import BaseHTTPMiddleware

    from .control import grace_seconds, set_grace_seconds, status, stop

    class _Inject(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
            response = await call_next(request)
            path = request.url.path
            if not path.startswith("/dashboard"):
                return response
            if "/static" in path:
                return response
            ctype = response.headers.get("content-type", "")
            if "text/html" not in ctype:
                return response
            body = b""
            async for chunk in response.body_iterator:
                body += chunk
            body = inject_dashboard_html(body)
            headers = dict(response.headers)
            headers.pop("content-length", None)
            return Response(
                content=body,
                status_code=response.status_code,
                headers=headers,
                media_type="text/html",
            )

    app.add_middleware(_Inject)

    @app.get("/overlay/lifecycle")
    async def overlay_get(request: Request) -> JSONResponse:
        _loopback(request)
        return JSONResponse(status())

    @app.post("/overlay/lifecycle")
    async def overlay_post(request: Request) -> JSONResponse:
        _loopback(request)
        try:
            payload = await request.json()
        except Exception:
            payload = {}
        seconds = payload.get("grace_seconds") if isinstance(payload, dict) else None
        if seconds is None:
            return JSONResponse(status())
        try:
            return JSONResponse({"grace_seconds": set_grace_seconds(int(seconds))})
        except (TypeError, ValueError):
            return JSONResponse({"detail": "grace_seconds must be an integer"}, status_code=400)

    @app.post("/overlay/stop")
    async def overlay_stop(request: Request) -> JSONResponse:
        _loopback(request)
        code, detail, clients = stop()
        body = {"detail": detail, "clients": clients}
        status_code = 200 if code == 0 else (409 if code == 409 else 500)
        return JSONResponse(body, status_code=status_code)
