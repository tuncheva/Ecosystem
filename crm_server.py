from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("crm")

# Mock CRM datastore (order_id -> customer record)
# NOTE: The lab still runs the fixed prompt/order (XYZ-789), but the system contains
# a few orders to better illustrate “multiple records” in the dashboard.
_MOCK_ORDERS: dict[str, dict[str, str]] = {
    "XYZ-789": {
        "customer_id": "CUST-1001",
        "name": "Taylor Rivera",
        "email": "customer@example.com",
    },
    "ABC-123": {
        "customer_id": "CUST-1002",
        "name": "Jordan Lee",
        "email": "alice@acme.com",
    },
    "QWE-456": {
        "customer_id": "CUST-1003",
        "name": "Casey Nguyen",
        "email": "bob@contoso.com",
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
