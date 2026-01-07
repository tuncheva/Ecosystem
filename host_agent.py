from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Any

import httpx

from config import Settings, load_settings


@dataclass(frozen=True)
class MCPServerSpec:
    name: str
    args: list[str]


async def _velocity_chat_completed(
    *,
    settings: Settings,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    """Call Velocity via an OpenAI-style endpoint under `VELOCITY_BASE_URL`.

    Your `.env` sets:
      VELOCITY_BASE_URL=https://chat.velocity.online/api

    NOTE: the base URL (`/api`) itself returns 405 for POST, so the actual chat endpoint is:
      POST {base_url}/chat/completions

    If your gateway differs, update only this function.
    """

    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
    }

    # OpenAI-style chat.completions payload
    payload: dict[str, Any] = {
        "model": settings.model,
        "messages": messages,
        "tools": tools,
    }

    # Velocity's API base URL is configured in .env. The base itself (`/api`) returns 405 for POST,
    # so we must call the OpenAI-style chat endpoint under that base.
    api_url = settings.base_url.rstrip("/") + "/chat/completions"

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(api_url, headers=headers, json=payload)

    # Provide maximum diagnostics (teaching + debugging)
    if resp.status_code >= 400:
        # Best-effort: enrich the error with hints and (if available) a models endpoint.
        hint_lines: list[str] = []
        hint_lines.append(
            "Hint: your gateway rejected the model. Set VELOCITY_MODEL to a model name supported by Velocity."
        )

        try:
            err_json = resp.json()
        except Exception:
            err_json = None

        detail = None
        if isinstance(err_json, dict):
            detail = err_json.get("detail") or err_json.get("message")

        # Common case: {"detail":"Model not found"}
        if isinstance(detail, str) and "model" in detail.lower():
            hint_lines.append(
                f"Current model={settings.model!r} was rejected. Try e.g. 'gpt-4o-mini', 'gpt-4o', or your org's allowed model string."
            )

        # Try a couple of common model-list endpoints derived from the base URL host.
        # Some Velocity deployments serve a web UI on /v1/models (HTML). If we detect HTML,
        # we report it and try the next candidate.
        parsed_url = httpx.URL(settings.base_url)
        candidate_urls = [
            str(parsed_url.copy_with(path="/v1/models", query=None, fragment=None)),
            str(parsed_url.copy_with(path="/api/models", query=None, fragment=None)),
            str(parsed_url.copy_with(path="/models", query=None, fragment=None)),
        ]

        models_payload: str | None = None
        async with httpx.AsyncClient(timeout=10.0) as client:
            for u in candidate_urls:
                try:
                    mresp = await client.get(
                        u,
                        headers={
                            "Authorization": headers["Authorization"],
                            "Accept": "application/json",
                        },
                    )
                    if mresp.status_code >= 400 or not mresp.text:
                        continue

                    ctype = (mresp.headers.get("content-type") or "").lower()
                    body_preview = mresp.text[:200].lstrip()
                    looks_html = ("text/html" in ctype) or body_preview.startswith("<!doctype") or body_preview.startswith("<html")

                    if looks_html:
                        hint_lines.append(
                            f"Tried models endpoint {u!r} but it returned HTML (likely the web UI), not JSON."
                        )
                        continue

                    models_payload = mresp.text[:1000]
                    hint_lines.append(f"Gateway models endpoint seems to work: {u!r}")
                    hint_lines.append(f"Models response (truncated): {models_payload!r}")
                    break
                except Exception:
                    continue

        raise RuntimeError(
            "Velocity gateway error "
            f"status={resp.status_code} url={api_url!r} body={resp.text[:500]!r}\n"
            + "\n".join(hint_lines)
        )

    try:
        return resp.json()
    except Exception as e:
        raise RuntimeError(f"Gateway returned non-JSON: {resp.text[:500]!r}") from e


def _extract_assistant_and_tool_calls(gateway_json: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    """Best-effort normalization of the gateway response.

    We support a few common shapes:
    - OpenAI-like chat.completions response
    - A custom {content, tool_calls} response

    Returns:
      (assistant_text, tool_calls)

    tool_calls is list of {id, name, arguments} where arguments is a JSON string.
    """

    # 1) OpenAI-like: {choices:[{message:{content, tool_calls:[{id,function:{name,arguments}}]}}]}
    if isinstance(gateway_json.get("choices"), list) and gateway_json["choices"]:
        msg = (gateway_json["choices"][0] or {}).get("message") or {}
        assistant_text = msg.get("content") or ""
        calls: list[dict[str, str]] = []
        for tc in msg.get("tool_calls") or []:
            fn = tc.get("function") or {}
            calls.append(
                {
                    "id": tc.get("id") or "toolcall_1",
                    "name": fn.get("name") or "",
                    "arguments": fn.get("arguments") or "{}",
                }
            )
        return assistant_text, calls

    # 2) Custom: {content: "...", tool_calls:[{id,name,arguments}]}
    if "content" in gateway_json and "tool_calls" in gateway_json:
        assistant_text = str(gateway_json.get("content") or "")
        calls = []
        for tc in gateway_json.get("tool_calls") or []:
            calls.append(
                {
                    "id": tc.get("id") or "toolcall_1",
                    "name": tc.get("name") or "",
                    "arguments": tc.get("arguments") or "{}",
                }
            )
        return assistant_text, calls

    # 3) Fallback: treat entire payload as text
    return json.dumps(gateway_json)[:2000], []


async def _run_agent(settings: Settings) -> str:
    """Host agent:

    - Spawns two MCP stdio servers as subprocesses
    - Lists their tools
    - Uses the Velocity gateway LLM to decide which tools to call
    """

    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    print("[host] Loaded settings:")
    print(f"[host]   model={settings.model!r}")
    print(f"[host]   base_url={settings.base_url!r}")

    servers: list[MCPServerSpec] = [
        MCPServerSpec(name="crm", args=[sys.executable, "crm_server.py"]),
        MCPServerSpec(name="email", args=[sys.executable, "email_server.py"]),
    ]

    sessions: dict[str, ClientSession] = {}
    stdio_cm: dict[str, Any] = {}

    async def start_server(spec: MCPServerSpec) -> None:
        params = StdioServerParameters(command=spec.args[0], args=spec.args[1:])
        cm = stdio_client(params)
        stdio_cm[spec.name] = cm
        read_stream, write_stream = await cm.__aenter__()
        session = ClientSession(read_stream, write_stream)
        await session.__aenter__()
        await session.initialize()
        sessions[spec.name] = session
        print(f"[host] MCP server started: {spec.name} -> {spec.args}")

    async def stop_all() -> None:
        for _, session in list(sessions.items()):
            try:
                await session.__aexit__(None, None, None)
            except Exception:
                pass
        for _, cm in list(stdio_cm.items()):
            try:
                await cm.__aexit__(None, None, None)
            except (asyncio.CancelledError, Exception):
                pass

    try:
        for spec in servers:
            await start_server(spec)

        # Build OpenAI-like tool descriptors for the gateway.
        tool_index: dict[str, tuple[str, str]] = {}
        tools: list[dict[str, Any]] = []

        for server_name, session in sessions.items():
            tool_list = await session.list_tools()
            for t in tool_list.tools:
                # OpenAI tool names must match ^[a-zA-Z0-9_-]+$.
                # MCP tool names may include dots or other chars, so we sanitize.
                global_name = f"{server_name}.{t.name}"
                safe_name = f"{server_name}_{t.name}".replace(".", "_")
                tool_index[safe_name] = (server_name, t.name)

                tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": safe_name,
                            "description": (t.description or "").strip(),
                            "parameters": t.inputSchema or {"type": "object", "properties": {}},
                        },
                    }
                )

        system = (
            "You are an Autonomous Operations Agent. "
            "Your job is to process incoming customer orders by using available tools. "
            "Workflow: look up customer email for the order, then send a shipping confirmation email. "
            "After completing, respond with a short summary of actions taken."
        )
        user = "Process new order #XYZ-789."

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        # Tool loop
        for _ in range(10):
            gateway_json = await _velocity_chat_completed(settings=settings, messages=messages, tools=tools)
            assistant_text, tool_calls = _extract_assistant_and_tool_calls(gateway_json)

            if not tool_calls:
                return assistant_text

            # Append assistant with tool calls.
            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_text,
                    "tool_calls": [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {"name": tc["name"], "arguments": tc["arguments"]},
                        }
                        for tc in tool_calls
                    ],
                }
            )

            # Execute tool calls.
            for tc in tool_calls:
                global_name = tc["name"]
                args_json = tc["arguments"]
                try:
                    args = json.loads(args_json) if args_json else {}
                except json.JSONDecodeError:
                    args = {"_raw": args_json}

                if global_name not in tool_index:
                    result = {"error": f"Unknown tool: {global_name}"}
                else:
                    server_name, local_tool = tool_index[global_name]
                    session = sessions[server_name]
                    print(f"[host] Tool call -> {global_name}({args})")
                    call_result = await session.call_tool(local_tool, args)
                    result = {
                        "content": [
                            {"type": c.type, "text": getattr(c, "text", None)}
                            for c in (call_result.content or [])
                        ]
                    }

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": json.dumps(result),
                    }
                )

        return "Failed: model kept requesting tools without finishing."

    finally:
        await stop_all()


async def main() -> None:
    settings = load_settings()
    final = await _run_agent(settings)
    print("\n[host] Final answer:\n")
    print(final)


if __name__ == "__main__":
    asyncio.run(main())
