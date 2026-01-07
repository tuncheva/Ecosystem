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
- `VELOCITY_MODEL` (e.g. `gpt-5.2`)
- `VELOCITY_CHAT_COMPLETED_URL` (optional; defaults to `https://chat.velocity.online/api/chat/completed`)

Example:

```ini
VELOCITY_API_KEY=...
VELOCITY_MODEL=gpt-5.2
VELOCITY_CHAT_COMPLETED_URL=https://chat.velocity.online/api/chat/completed
```

Notes:
- You can keep `VELOCITY_BASE_URL` in `.env` if other tooling needs it.
- The demo Host uses the custom gateway endpoint configured in [`load_settings()`](config.py:34).

## 2) Install deps

In repo root:

```bat
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## 3) Run

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

## Troubleshooting

### 405 / Method Not Allowed
That error usually happens when you call an OpenAI-style endpoint that your gateway does not expose.
This demo calls the custom endpoint in [`_velocity_chat_completed()`](host_agent.py:19).

### Gateway response format mismatch
If the gateway returns a different JSON shape than expected, update only:
- [`_extract_assistant_and_tool_calls()`](host_agent.py:70)

## Teaching plan reference

See [`plans/module6_mcp_autonomous_ops_plan.md`](plans/module6_mcp_autonomous_ops_plan.md).
