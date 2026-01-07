from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from config import Settings


@dataclass(frozen=True)
class MCPServerSpec:
    name: str
    args: list[str]


EventSink = Callable[[dict[str, Any]], None]


def _emit(sink: EventSink | None, event: dict[str, Any]) -> None:
    if sink is None:
        return
    try:
        sink(event)
    except Exception:
        # Never fail the workflow due to logging/UI plumbing.
        pass


def _extract_assistant_and_tool_calls(gateway_json: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    """Best-effort normalization of the gateway response.

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


async def _velocity_chat_completions(
    *,
    settings: Settings,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    event_sink: EventSink | None,
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
    }

    payload: dict[str, Any] = {
        "model": settings.model,
        "messages": messages,
        "tools": tools,
    }

    api_url = settings.base_url.rstrip("/") + "/chat/completions"

    _emit(event_sink, {"type": "gateway_request", "url": api_url, "model": settings.model})

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(api_url, headers=headers, json=payload)

    if resp.status_code >= 400:
        _emit(
            event_sink,
            {
                "type": "gateway_error",
                "status": resp.status_code,
                "url": api_url,
                "body": resp.text[:2000],
            },
        )
        raise RuntimeError(
            "Velocity gateway error "
            f"status={resp.status_code} url={api_url!r} body={resp.text[:500]!r}"
        )

    try:
        return resp.json()
    except Exception as e:
        raise RuntimeError(f"Gateway returned non-JSON: {resp.text[:500]!r}") from e


async def run_order_workflow(*, settings: Settings, event_sink: EventSink | None = None) -> str:
    """Runs the exact lab workflow.

    Prompt is fixed to:
      Process new order #XYZ-789.

    This function is designed to be called from both CLI and web UI.
    """

    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    # Mirror CLI prints so the Web UI can display the same output you see in a terminal.
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
        _emit(event_sink, {"type": "mcp_server_started", "name": spec.name, "args": spec.args})

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

        tool_index: dict[str, tuple[str, str]] = {}
        tools: list[dict[str, Any]] = []

        for server_name, session in sessions.items():
            tool_list = await session.list_tools()
            for t in tool_list.tools:
                # OpenAI tool names must match ^[a-zA-Z0-9_-]+$.
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

        for _ in range(10):
            gateway_json = await _velocity_chat_completions(
                settings=settings, messages=messages, tools=tools, event_sink=event_sink
            )
            assistant_text, tool_calls = _extract_assistant_and_tool_calls(gateway_json)

            _emit(event_sink, {"type": "assistant", "content": assistant_text, "tool_calls": tool_calls})

            if not tool_calls:
                return assistant_text

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

            for tc in tool_calls:
                tool_name = tc["name"]
                args_json = tc["arguments"]
                try:
                    args = json.loads(args_json) if args_json else {}
                except json.JSONDecodeError:
                    args = {"_raw": args_json}

                if tool_name not in tool_index:
                    result = {"error": f"Unknown tool: {tool_name}"}
                else:
                    server_name, local_tool = tool_index[tool_name]
                    session = sessions[server_name]
                    print(f"[host] Tool call -> {tool_name}({args})")
                    _emit(event_sink, {"type": "tool_call", "name": tool_name, "args": args})
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
