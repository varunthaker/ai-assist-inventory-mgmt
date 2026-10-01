"""Purchase order tools. This module holds the only tool that writes data."""

from typing import Annotated

from pydantic import Field

from app.db import get_supabase


def register(server) -> None:
    """Register purchase order tools on the MCP server."""

    @server.tool(
        description=(
            "Create a new purchase order to restock a product. This WRITES to "
            "the database: only call it when the user has explicitly asked to "
            "place or create an order. The quantity must be at least the "
            "supplier's minimum order quantity (check with "
            "check_supplier_lead_time). Returns the new order's id, SKU, "
            "quantity, and status (new orders start as 'pending')."
        )
    )
    def create_purchase_order(
        sku: Annotated[str, Field(description="SKU of the product to order.")],
        quantity: Annotated[int, Field(description="Number of units to order.")],
    ) -> dict:
        sku = sku.strip().upper()
        if quantity <= 0:
            return {"error": f"Quantity must be positive, got {quantity}."}

        client = get_supabase()
        try:
            product = (
                client.table("products")
                .select("sku, name, unit, suppliers(name, min_order_qty)")
                .eq("sku", sku)
                .limit(1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Could not look up {sku}: {type(exc).__name__}: {exc}"}

        if not product.data:
            return {"error": f"No product with SKU '{sku}'. No order was created."}

        supplier = product.data[0]["suppliers"]
        min_qty = (supplier or {}).get("min_order_qty")
        if min_qty and quantity < min_qty:
            return {
                "error": (
                    f"Quantity {quantity} is below {supplier['name']}'s minimum "
                    f"order quantity of {min_qty}. No order was created."
                )
            }

        try:
            result = (
                client.table("purchase_orders")
                .insert({"sku": sku, "quantity": quantity})
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Could not create order: {type(exc).__name__}: {exc}"}

        order = result.data[0]
        return {
            "order_id": order["id"],
            "sku": order["sku"],
            "product_name": product.data[0]["name"],
            "quantity": order["quantity"],
            "unit": product.data[0]["unit"],
            "status": order["status"],
            "supplier_name": (supplier or {}).get("name"),
            "created_at": order["created_at"],
        }
