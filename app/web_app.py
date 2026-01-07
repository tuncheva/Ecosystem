from __future__ import annotations

import asyncio
import contextlib
import io
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from config import load_settings
from app.run_workflow import run_order_workflow


@dataclass
class RunState:
    run_id: str
    created_at: float = field(default_factory=lambda: time.time())
    status: str = "running"  # running|succeeded|failed
    logs: list[dict[str, Any]] = field(default_factory=list)
    final: str | None = None
    error: str | None = None


app = FastAPI(title="Module 6 Autonomous Operations Agent")

_RUNS: dict[str, RunState] = {}


def _append_event(run: RunState, event: dict[str, Any]) -> None:
    event = dict(event)
    event.setdefault("ts", time.time())
    run.logs.append(event)


async def _run_background(run: RunState) -> None:
    try:
        # Capture prints from MCP servers + any workflow prints to mirror terminal behavior.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            settings = load_settings()
            _append_event(run, {"type": "settings", "model": settings.model, "base_url": settings.base_url})

            final = await run_order_workflow(settings=settings, event_sink=lambda e: _append_event(run, e))
            run.final = final
            run.status = "succeeded"
            _append_event(run, {"type": "final", "content": final})

        captured = buf.getvalue().strip()
        if captured:
            _append_event(run, {"type": "stdout", "text": captured})

    except Exception as e:
        # Flush any captured output so the UI shows the same details you’d see in terminal.
        try:
            captured = buf.getvalue().strip()  # type: ignore[name-defined]
        except Exception:
            captured = ""
        if captured:
            _append_event(run, {"type": "stdout", "text": captured})

        run.status = "failed"
        run.error = repr(e)
        _append_event(run, {"type": "error", "error": run.error})


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    # Minimal self-contained UI (no build step)
    return """<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Autonomous Ops Agent (Module 6)</title>
  <style>
    body { font-family: ui-sans-serif, system-ui, Segoe UI, Arial; margin: 20px; }
    button { padding: 10px 14px; font-size: 14px; }
    #status { margin-left: 10px; font-weight: 600; }
    pre { background: #111; color: #ddd; padding: 12px; border-radius: 8px; overflow: auto; max-height: 60vh; }
    .muted { color: #666; }
  </style>
</head>
<body>
  <h1>Autonomous Operations Agent</h1>
  <p class=\"muted\">Prompt: <code>Process new order #XYZ-789.</code></p>

  <div>
    <button id=\"runBtn\">Run workflow</button>
    <span id=\"status\"></span>
  </div>
  <div id=\"uiDiag\" class=\"muted\" style=\"margin-top:8px;\"></div>

  <h3>Logs</h3>
  <pre id=\"log\"></pre>

<script>
  const runBtn = document.getElementById('runBtn');
  const statusEl = document.getElementById('status');
  const logEl = document.getElementById('log');
  const uiDiag = document.getElementById('uiDiag');
  if (uiDiag) uiDiag.textContent = 'ui loaded';

  function fmt(ev) {
    const ts = new Date((ev.ts || Date.now()/1000) * 1000).toISOString();
    return `[${ts}] ${ev.type}: ${JSON.stringify(ev)}`;
  }

  async function startRun() {
    logEl.textContent = '';
    statusEl.textContent = 'starting...';

    const resp = await fetch('/api/runs', { method: 'POST' });
    if (!resp.ok) {
      const txt = await resp.text();
      throw new Error(`POST /api/runs failed: ${resp.status} ${txt}`);
    }

    const data = await resp.json();
    const runId = data.run_id;

    statusEl.textContent = `running (${runId})`;

    let lastLen = 0;
    const timer = setInterval(async () => {
      try {
        const r = await fetch(`/api/runs/${runId}`);
        if (!r.ok) {
          const txt = await r.text();
          statusEl.textContent = `poll failed (${r.status})`;
          logEl.textContent += `\n[ui] poll error: ${txt}`;
          return;
        }

        const s = await r.json();
        statusEl.textContent = s.status + (s.error ? ' (error)' : '');

        const logs = s.logs || [];
        if (logs.length > lastLen) {
          const newLines = logs.slice(lastLen).map(fmt).join('\n') + '\n';
          logEl.textContent += newLines;
          logEl.scrollTop = logEl.scrollHeight;
          lastLen = logs.length;
        }

        if (s.status !== 'running') {
          clearInterval(timer);
        }
      } catch (e) {
        statusEl.textContent = 'poll exception';
        logEl.textContent += `\n[ui] poll exception: ${String(e)}`;
      }
    }, 750);
  }

  runBtn.addEventListener('click', () => {
    startRun().catch(err => {
      statusEl.textContent = 'failed to start';
      logEl.textContent += `\n[ui] start error: ${String(err)}`;
    });
  });
</script>
</body>
</html>"""


@app.post("/api/runs")
async def create_run() -> dict[str, str]:
    run_id = uuid.uuid4().hex
    run = RunState(run_id=run_id)
    _RUNS[run_id] = run

    # Fire-and-forget background task.
    asyncio.create_task(_run_background(run))

    return {"run_id": run_id}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict[str, Any]:
    run = _RUNS.get(run_id)
    if run is None:
        return {"run_id": run_id, "status": "not_found", "logs": []}

    return {
        "run_id": run.run_id,
        "status": run.status,
        "logs": run.logs,
        "final": run.final,
        "error": run.error,
    }
