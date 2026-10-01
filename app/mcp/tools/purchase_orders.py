"""Purchase order tools. This module holds the only tool that writes data."""

from typing import Annotated

from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from app.db import get_supabase


class PurchaseOrder(BaseModel):
    order_id: str
    sku: str
    product_name: str
    quantity: int
    unit: str | None = None
    unit_price: float | None = Field(
        default=None, description="Price per unit in EUR; null if unknown."
    )
    status: str = Field(description="New orders start as 'pending'.")
    supplier_name: str | None = None
    created_at: str


def register(server) -> None:
    """Register purchase order tools on the MCP server."""

    @server.tool(
        description=(
            "Create a new purchase order to restock a product. This WRITES to "
            "the database: only call it when the user has explicitly asked to "
            "place or create an order. Before calling it: (1) call "
            "search_procurement_policy for the ordering rules -- approval "
            "limits, approved suppliers, emergency orders, ordering rules -- "
            "and follow them; (2) check the supplier's minimum order quantity "
            "with check_supplier_lead_time (the quantity must be at least "
            "that); (3) get the unit price with get_stock_level, work out the "
            "order value (quantity x unit price) and tell the user which "
            "approval the policy requires for that value. Returns the new "
            "order's id, SKU, quantity, unit price and status (new orders "
            "start as 'pending')."
        )
    )
    def create_purchase_order(
        sku: Annotated[str, Field(description="SKU of the product to order.")],
        quantity: Annotated[int, Field(description="Number of units to order.")],
    ) -> PurchaseOrder:
        sku = sku.strip().upper()
        if quantity <= 0:
            raise ToolError(f"Quantity must be positive, got {quantity}.")

        client = get_supabase()
        try:
            product = (
                client.table("products")
                .select("sku, name, unit, unit_price, suppliers(name, min_order_qty)")
                .eq("sku", sku)
                .limit(1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"Could not look up {sku}: {type(exc).__name__}: {exc}") from exc

        if not product.data:
            raise ToolError(f"No product with SKU '{sku}'. No order was created.")

        row = product.data[0]
        supplier = row["suppliers"]
        min_qty = (supplier or {}).get("min_order_qty")
        if min_qty and quantity < min_qty:
            raise ToolError(
                f"Quantity {quantity} is below {supplier['name']}'s minimum "
                f"order quantity of {min_qty}. No order was created."
            )

        try:
            result = (
                client.table("purchase_orders")
                .insert({"sku": sku, "quantity": quantity})
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"Could not create order: {type(exc).__name__}: {exc}") from exc

        order = result.data[0]
        return PurchaseOrder(
            order_id=order["id"],
            sku=order["sku"],
            product_name=row["name"],
            quantity=order["quantity"],
            unit=row["unit"],
            unit_price=row["unit_price"],
            status=order["status"],
            supplier_name=(supplier or {}).get("name"),
            created_at=order["created_at"],
        )
