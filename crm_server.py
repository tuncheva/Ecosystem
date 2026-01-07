from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("crm")

# Mock CRM datastore (order_id -> customer record)
_MOCK_ORDERS: dict[str, dict[str, str]] = {
    "XYZ-789": {
        "customer_id": "CUST-1001",
        "name": "Taylor Rivera",
        "email": "customer@example.com",
    },
    "ABC-123": {
        "customer_id": "CUST-1002",
        "name": "Jordan Lee",
        "email": "jordan.lee@example.com",
    },
}


@mcp.tool()
def getCustomerEmail(order_id: str) -> dict[str, str]:
    """Look up a customer's email address by order id.

    Teaching note: in real life this would query a CRM database or external CRM API.

    Args:
        order_id: Order identifier, e.g. "XYZ-789".

    Returns:
        Object containing at least `email`, plus optional customer metadata.
    """
    normalized = order_id.strip().lstrip("#")
    if normalized in _MOCK_ORDERS:
        return _MOCK_ORDERS[normalized]

    # Deterministic fallback for unknown orders (keeps demo smooth)
    return {
        "customer_id": "CUST-0000",
        "name": "Unknown Customer",
        "email": f"{normalized.lower()}@example.com",
    }


async def main() -> None:
    # stdio server (so the Host can spawn it as a subprocess)
    await mcp.run_stdio_async()


if __name__ == "__main__":
    asyncio.run(main())
