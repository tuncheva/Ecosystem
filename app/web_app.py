from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from app.run_workflow import run_order_workflow
from config import load_settings


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
        # IMPORTANT:
        # Do not redirect stdout/stderr under uvicorn for this lab.
        # MCP stdio transport requires real file descriptors and redirecting can throw:
        # UnsupportedOperation('fileno')
        settings = load_settings()

        final = await run_order_workflow(
            settings=settings,
            order_id=(run.logs[0].get("order_id") if run.logs else "XYZ-789"),
            event_sink=lambda e: _append_event(run, e),
        )
        run.final = final
        run.status = "succeeded"
        _append_event(run, {"type": "final", "content": final})

    except Exception as e:
        run.status = "failed"
        run.error = repr(e)
        _append_event(run, {"type": "error", "error": run.error})


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    # Dashboard-style UI (no build step)
    # NOTE: keep JS template-literal-free and avoid backticks.
    # NOTE: never embed literal newlines inside JS string literals in this HTML.
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Autonomous Ops Agent (Module 6)</title>
  <style>
    :root {
      --bg: #05070e;
      --panel: rgba(255,255,255,0.04);
      --panel2: rgba(255,255,255,0.03);
      --text: rgba(255,255,255,0.92);
      --muted: rgba(255,255,255,0.62);
      --border: rgba(255,255,255,0.10);
      --border2: rgba(255,255,255,0.07);
      --blue: #3b82f6;
      --blue2: rgba(59,130,246,0.18);
      --shadow: 0 18px 46px rgba(0,0,0,0.55);
      --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: ui-sans-serif, system-ui, Segoe UI, Arial;
      background:
        radial-gradient(900px 500px at 20% 0%, rgba(59,130,246,0.12), transparent 55%),
        radial-gradient(1100px 520px at 90% 15%, rgba(99,102,241,0.10), transparent 50%),
        var(--bg);
      color: var(--text);
    }

    .wrap { max-width: 1180px; margin: 0 auto; padding: 18px 14px 26px; }

    .topbar {
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
    }

    .title h1 { margin: 0; font-size: 22px; letter-spacing: 0.2px; }
    .title .subtitle { margin-top: 6px; color: var(--muted); font-size: 13px; }
    .title code {
      font-family: var(--mono);
      background: rgba(255,255,255,0.06);
      border: 1px solid rgba(255,255,255,0.10);
      padding: 3px 8px;
      border-radius: 999px;
      color: rgba(255,255,255,0.88);
    }

    .right {
      display: flex;
      gap: 10px;
      align-items: center;
      justify-content: flex-end;
      flex-wrap: wrap;
    }

    .chip {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 7px 10px;
      border-radius: 999px;
      border: 1px solid var(--border2);
      background: rgba(255,255,255,0.03);
      color: rgba(255,255,255,0.82);
      font-size: 12px;
      white-space: nowrap;
    }

    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--blue);
      box-shadow: 0 0 0 4px rgba(59,130,246,0.16);
    }

    .btn {
      appearance: none;
      border: 1px solid rgba(59,130,246,0.55);
      background: linear-gradient(180deg, rgba(59,130,246,0.98), rgba(59,130,246,0.78));
      color: white;
      padding: 10px 14px;
      border-radius: 12px;
      font-size: 13px;
      font-weight: 800;
      cursor: pointer;
      box-shadow: 0 14px 22px rgba(59,130,246,0.16);
    }
    .btn:hover { filter: brightness(1.04); }
    .btn:disabled { opacity: 0.55; cursor: not-allowed; box-shadow: none; filter: none; }

    .grid {
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 14px;
    }

    @media (max-width: 980px) {
      .grid { grid-template-columns: 1fr; }
    }

    .card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 16px;
      box-shadow: var(--shadow);
      overflow: hidden;
    }

    .card .hd {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      padding: 12px 12px;
      background: var(--panel2);
      border-bottom: 1px solid var(--border2);
    }

    .card .hd .h { font-weight: 900; letter-spacing: 0.2px; font-size: 13px; color: rgba(255,255,255,0.90); }
    .card .bd { padding: 12px; }

    .kv {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: center;
      padding: 8px 10px;
      border: 1px solid var(--border2);
      background: rgba(0,0,0,0.16);
      border-radius: 12px;
      margin-bottom: 10px;
    }

    .kv .k { color: var(--muted); font-size: 12px; }
    .kv .v { font-family: var(--mono); font-size: 12px; color: rgba(255,255,255,0.90); }

    .orders {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }

    .order {
      border: 1px solid var(--border2);
      background: rgba(255,255,255,0.03);
      border-radius: 14px;
      padding: 10px;
    }

    .order .top {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 8px;
    }

    .order .id {
      font-family: var(--mono);
      font-weight: 900;
      font-size: 12px;
      color: rgba(255,255,255,0.92);
    }

    .pill {
      padding: 5px 8px;
      border-radius: 999px;
      border: 1px solid var(--border2);
      background: rgba(255,255,255,0.03);
      color: rgba(255,255,255,0.72);
      font-size: 11px;
      white-space: nowrap;
    }

    .pill.primary {
      border-color: rgba(59,130,246,0.40);
      background: rgba(59,130,246,0.12);
      color: rgba(255,255,255,0.88);
    }

    .order .meta {
      color: rgba(255,255,255,0.70);
      font-size: 12px;
      line-height: 1.35;
    }

    .mono { font-family: var(--mono); }

    .two {
      display: grid;
      grid-template-columns: 1fr;
      gap: 14px;
    }

    .log {
      font-family: var(--mono);
      font-size: 12px;
      line-height: 1.35;
      white-space: pre-wrap;
      min-height: 160px;
      max-height: 270px;
      overflow: auto;
      padding: 12px;
      border: 1px solid var(--border2);
      border-radius: 14px;
      background: rgba(0,0,0,0.18);
      color: rgba(255,255,255,0.82);
    }

    .answer {
      padding: 14px;
      border: 1px solid rgba(59,130,246,0.22);
      border-radius: 14px;
      background: rgba(59,130,246,0.08);
      color: rgba(255,255,255,0.96);
      line-height: 1.45;
      white-space: pre-wrap;
      min-height: 96px;
      box-shadow: 0 12px 26px rgba(0,0,0,0.40);
    }

    .answer.empty { color: rgba(255,255,255,0.60); }

    .diag {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 10px;
      color: rgba(255,255,255,0.65);
      font-size: 12px;
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div class="title">
        <h1>Autonomous Operations Agent</h1>
        <div class="subtitle">Lab prompt: <code id="promptText">Process new order #XYZ-789.</code></div>
      </div>
      <div class="right">
        <div class="chip"><span class="dot"></span> MCP Host + Tools</div>
        <div class="chip">Status: <span id="status">idle</span></div>
        <button class="btn" id="runBtn" style="display:none">Run workflow</button>
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <div class="hd">
          <div class="h">Orders (mock CRM)</div>
          <div class="pill primary">click an order to run</div>
        </div>
        <div class="bd">
          <div class="kv"><div class="k">Prompt</div><div class="v" id="ghostPrompt">Process new order #XYZ-789.</div></div>
          <div class="orders" id="orders"></div>
          <div class="diag">
            <div class="pill">UI: dashboard view</div>
            <div class="pill">MCP: stdio servers</div>
            <div class="pill">Diag: <span id="uiDiag">ui loaded</span></div>
          </div>
        </div>
      </div>

      <div class="two">
        <div class="card">
          <div class="hd">
            <div class="h">Processing timeline</div>
            <div class="pill" id="runIdPill">run: -</div>
          </div>
          <div class="bd">
            <div class="log" id="processLog">Process:\\n- Select an order to run...</div>
          </div>
        </div>

        <div class="card">
          <div class="hd">
            <div class="h">Output</div>
            <div class="pill" id="resultPill">result: -</div>
          </div>
          <div class="bd">
            <div class="answer empty" id="finalAnswer">Click an order to run the agent.</div>
          </div>
        </div>
      </div>
    </div>
  </div>

<script>
  const runBtn = document.getElementById('runBtn');
  const statusEl = document.getElementById('status');
  const uiDiag = document.getElementById('uiDiag');
  const promptTextEl = document.getElementById('promptText');
  const ghostPromptEl = document.getElementById('ghostPrompt');
  const ordersEl = document.getElementById('orders');
  const processLogEl = document.getElementById('processLog');
  const finalAnswerEl = document.getElementById('finalAnswer');
  const runIdPillEl = document.getElementById('runIdPill');
  const resultPillEl = document.getElementById('resultPill');

  const PROMPT_PREFIX = 'Process new order #';

  const MOCK_ORDERS = [
    { id: 'XYZ-789', email: 'customer@example.com', customer: 'Taylor Rivera', status: 'active demo' },
    { id: 'ABC-123', email: 'alice@acme.com', customer: 'Jordan Lee', status: 'active demo' },
    { id: 'QWE-456', email: 'bob@contoso.com', customer: 'Casey Nguyen', status: 'active demo' }
  ];

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text;
  }

  function setRunMeta(runId, status) {
    if (runIdPillEl) runIdPillEl.textContent = 'run: ' + (runId || '-');
    if (resultPillEl) resultPillEl.textContent = 'result: ' + (status || '-');
  }

  function renderOrders() {
    if (!ordersEl) return;
    ordersEl.textContent = '';

    for (let i = 0; i < MOCK_ORDERS.length; i++) {
      const o = MOCK_ORDERS[i];
      const el = document.createElement('div');
      el.className = 'order';
      el.setAttribute('data-order-id', o.id);
      el.style.cursor = 'pointer';

      const top = document.createElement('div');
      top.className = 'top';

      const id = document.createElement('div');
      id.className = 'id';
      id.textContent = '#' + o.id;

      const pill = document.createElement('div');
      pill.className = 'pill primary';
      pill.textContent = o.status;

      top.appendChild(id);
      top.appendChild(pill);

      const meta = document.createElement('div');
      meta.className = 'meta';
      meta.innerHTML = '<div><span class="mono">' + o.email + '</span></div>' +
                       '<div>' + o.customer + '</div>';

      el.appendChild(top);
      el.appendChild(meta);

      ordersEl.appendChild(el);
    }
  }

  function toProcessLine(ev) {
    if (!ev || !ev.type) return '';

    if (ev.type === 'mcp_server_started') {
      const name = String(ev.name || '').toLowerCase();
      if (name.indexOf('crm') >= 0) return 'Connected to CRM system.';
      if (name.indexOf('email') >= 0) return 'Connected to Email system.';
      return 'Connected to tool server: ' + String(ev.name || '');
    }

    if (ev.type === 'gateway_request') return 'Contacting model gateway...';

    if (ev.type === 'assistant') {
      const hasText = (ev.content && String(ev.content).trim());
      if (hasText) return 'Model response received.';
      return 'Planning next action...';
    }

    if (ev.type === 'tool_call') {
      const n = String(ev.name || '');
      if (n.indexOf('getCustomerEmail') >= 0) return 'Looking up customer email for the order...';
      if (n.indexOf('sendShippingConfirmation') >= 0) return 'Sending shipping confirmation email...';
      return 'Calling tool: ' + n;
    }

    if (ev.type === 'final') return 'Completed.';

    if (ev.type === 'error') return 'Failed.';

    return '';
  }

  function resetPanels() {
    if (processLogEl) processLogEl.textContent = 'Process:' + String.fromCharCode(10) + '- Select an order to run...';
    if (finalAnswerEl) {
      finalAnswerEl.textContent = 'Click an order to run the agent.';
      finalAnswerEl.className = 'answer empty';
    }
    setRunMeta('', '');
  }

  async function startRun(orderId) {
    const oid = String(orderId || '').trim().replace(/^#/, '').toUpperCase();
    if (!oid) throw new Error('Missing order id');

    if (runBtn) runBtn.disabled = true;
    setStatus('starting...');
    setRunMeta('-', 'starting');

    resetPanels();

    if (processLogEl) processLogEl.textContent = 'Process:' + String.fromCharCode(10) + '- Starting order #' + oid + '...';

    const resp = await fetch('/api/runs?order_id=' + encodeURIComponent(oid), { method: 'POST' });
    if (!resp.ok) {
      const txt = await resp.text();
      throw new Error('POST /api/runs failed: ' + resp.status + ' ' + txt);
    }

    const data = await resp.json();
    const runId = data.run_id;
    setStatus('running');
    setRunMeta(runId, 'running');

    const processLines = [];
    let lastLen = 0;

    const timer = setInterval(async () => {
      try {
        const r = await fetch('/api/runs/' + runId);
        if (!r.ok) {
          const txt = await r.text();
          setStatus('poll failed');
          setRunMeta(runId, 'poll failed');
          if (processLogEl) processLogEl.textContent = 'Process:' + String.fromCharCode(10) + '- [ui] poll error: ' + txt;
          if (finalAnswerEl) {
            finalAnswerEl.textContent = 'UI polling error.';
            finalAnswerEl.className = 'answer';
          }
          return;
        }

        const s = await r.json();
        setStatus(s.status);
        setRunMeta(runId, s.status + (s.error ? ' error' : ''));

        const logs = s.logs || [];
        if (logs.length > lastLen) {
          for (let i = lastLen; i < logs.length; i++) {
            const ev = logs[i];
            const line = toProcessLine(ev);
            if (line) {
              if (processLines.length === 0 || processLines[processLines.length - 1] !== line) {
                processLines.push(line);
              }
              // Use real newlines in JS strings (avoid embedding literal newlines in the HTML source).
              if (processLogEl) processLogEl.textContent = 'Process:' + String.fromCharCode(10) + '- ' + processLines.join(String.fromCharCode(10) + '- ');
            }

            if (ev && ev.type === 'final') {
              if (finalAnswerEl) {
                finalAnswerEl.textContent = String(ev.content || '');
                finalAnswerEl.className = 'answer';
              }
            }
            if (ev && ev.type === 'error') {
              if (finalAnswerEl) {
                finalAnswerEl.textContent = 'Workflow failed.';
                finalAnswerEl.className = 'answer';
              }
              if (processLogEl) processLogEl.textContent = 'Process:' + String.fromCharCode(10) + '- [error] ' + String(ev.error || '');
            }
          }
          lastLen = logs.length;
        }

        if (s.status !== 'running') {
          clearInterval(timer);
          if (runBtn) runBtn.disabled = false;
          setRunMeta(runId, s.status);
        }
      } catch (e) {
        setStatus('poll exception');
        setRunMeta(runId, 'poll exception');
        if (processLogEl) processLogEl.textContent = 'Process:' + String.fromCharCode(10) + '- [ui] poll exception: ' + String(e);
        if (runBtn) runBtn.disabled = false;
      }
    }, 750);
  }

  if (uiDiag) uiDiag.textContent = 'ui loaded';
  if (promptTextEl) promptTextEl.textContent = PROMPT_PREFIX + '...';
  if (ghostPromptEl) ghostPromptEl.textContent = PROMPT_PREFIX + '...';

  renderOrders();
  resetPanels();

  // Clicking an order card runs the workflow.
  if (ordersEl) {
    ordersEl.onclick = function (e) {
      let node = e && e.target ? e.target : null;
      while (node && node !== ordersEl) {
        if (node.getAttribute && node.getAttribute('data-order-id')) {
          const oid = node.getAttribute('data-order-id');
          if (runBtn && runBtn.disabled) return;
          startRun(oid).catch(err => {
            setStatus('failed to start');
            setRunMeta('-', 'start error');
            if (runBtn) runBtn.disabled = false;
            if (processLogEl) processLogEl.textContent = 'Process:' + String.fromCharCode(10) + '- [ui] start error: ' + String(err);
            if (finalAnswerEl) {
              finalAnswerEl.textContent = 'Failed to start run.';
              finalAnswerEl.className = 'answer';
            }
          });
          return;
        }
        node = node.parentNode;
      }
    };
  }
</script>
</body>
</html>"""


@app.post('/api/runs')
async def create_run(order_id: str = Query(default="XYZ-789")) -> dict[str, str]:
    run_id = uuid.uuid4().hex
    run = RunState(run_id=run_id)

    # Store order_id as the first log event so the background runner can pick it up
    # without changing the RunState dataclass.
    _append_event(run, {"type": "run_started", "order_id": order_id.strip().lstrip('#').upper()})

    _RUNS[run_id] = run

    asyncio.create_task(_run_background(run))

    return {'run_id': run_id}


@app.get('/api/runs/{run_id}')
async def get_run(run_id: str) -> dict[str, Any]:
    run = _RUNS.get(run_id)
    if run is None:
        return {'run_id': run_id, 'status': 'not_found', 'logs': []}

    return {
        'run_id': run.run_id,
        'status': run.status,
        'logs': run.logs,
        'final': run.final,
        'error': run.error,
    }
