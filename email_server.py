from __future__ import annotations

import asyncio
import time
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("email")


@mcp.tool()
def sendShippingConfirmation(email: str, order_details: str) -> dict[str, str]:
    """Send a shipping confirmation email.

    Teaching note: in real life this would call an email provider (SendGrid, SES, etc.).

    Args:
        email: Recipient email.
        order_details: Human-readable order details (or JSON string).

    Returns:
        status + message_id.
    """
    message_id = f"msg_{int(time.time())}"

    # Simulate sending (stdout is visible in the Host logs when spawned)
    print("[email_server] Sending shipping confirmation")
    print(f"[email_server] To: {email}")
    print(f"[email_server] Body: {order_details}")
    print(f"[email_server] message_id={message_id}")

    return {"status": "sent", "message_id": message_id}


async def main() -> None:
    await mcp.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
