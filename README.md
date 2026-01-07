# Module 6 — Autonomous Operations Agent (MCP + Velocity gateway, Python)

This is a runnable teaching demo for **Module 6: The Ecosystem: The Future of Agent Architecture**.

- **Host**: [`host_agent.py`](host_agent.py)
- **MCP servers** (stdio):
  - [`crm_server.py`](crm_server.py): `getCustomerEmail(order_id)`
  - [`email_server.py`](email_server.py): `sendShippingConfirmation(email, order_details)`

The host spawns both MCP servers automatically (one-command run).

## 0) Prereqs

- Windows 10+
- Python 3.10+ recommended

## 1) Configure `.env`

You already have a `.env` at repo root. Required keys:

- `VELOCITY_API_KEY`
- `VELOCITY_BASE_URL` (e.g. `https://chat.velocity.online/api`)
- `VELOCITY_MODEL` (a supported model id from `GET https://chat.velocity.online/api/models`)

Example:

```ini
VELOCITY_API_KEY=...
VELOCITY_BASE_URL=https://chat.velocity.online/api
VELOCITY_MODEL=nebius.deepseek-ai/DeepSeek-V3-0324
```

## 2) Install deps

In repo root:

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 3) Run (CLI)

PowerShell:

```powershell
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python host_agent.py
```

cmd.exe:

```bat
.venv\Scripts\activate
python -m pip install -r requirements.txt
python host_agent.py
```

Expected behavior:

- Host prints loaded settings.
- Host spawns MCP servers.
- Model (via Velocity gateway) autonomously calls:
  - `crm.getCustomerEmail({"order_id":"XYZ-789"})`
  - `email.sendShippingConfirmation({"email":..., "order_details":...})`
- Host prints a final summary.

## 4) Run (Web UI)

Start the web server:

```bat
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app.web_app:app --host 127.0.0.1 --port 8000
```

Open:
- http://127.0.0.1:8000

Click **Run workflow** to execute the exact lab prompt (`Process new order #XYZ-789.`) and view logs + final summary.

## Troubleshooting

### 405 / Method Not Allowed
If you see 405 calling the base URL (e.g. `https://chat.velocity.online/api`), it means you hit a route that doesn't accept the method.
The host calls the OpenAI-style chat endpoint under your base URL (see [`_velocity_chat_completed()`](host_agent.py:20)).

### Gateway response format mismatch
If the gateway returns a different JSON shape than expected, update only:
- [`_extract_assistant_and_tool_calls()`](host_agent.py:70)

## Teaching plan reference

See [`plans/module6_mcp_autonomous_ops_plan.md`](plans/module6_mcp_autonomous_ops_plan.md).
