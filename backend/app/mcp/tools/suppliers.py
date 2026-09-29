"""Supplier tools."""

from typing import Annotated

from pydantic import Field

from app.db import get_supabase


def register(server) -> None:
    """Register supplier tools on the MCP server."""

    @server.tool(
        description=(
            "Look up the supplier of a product by its SKU. Returns the "
            "supplier's name, lead time in days (how long a new order takes to "
            "arrive), minimum order quantity, and contact email. Use this for "
            "questions about who supplies an item, how long restocking takes, "
            "or the minimum amount that can be ordered."
        )
    )
    def check_supplier_lead_time(
        sku: Annotated[str, Field(description="Product SKU, e.g. 'PAL-STD-001'.")],
    ) -> dict:
        sku = sku.strip().upper()
        try:
            # Embedded select: follows products.supplier_id -> suppliers.id.
            result = (
                get_supabase()
                .table("products")
                .select("sku, name, suppliers(name, lead_time_days, min_order_qty, contact_email)")
                .eq("sku", sku)
                .limit(1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Could not query supplier for {sku}: {type(exc).__name__}: {exc}"}

        if not result.data:
            return {"error": f"No product with SKU '{sku}'."}

        product = result.data[0]
        supplier = product["suppliers"]
        if not supplier:
            return {"error": f"Product {sku} has no supplier assigned."}

        return {
            "sku": product["sku"],
            "product_name": product["name"],
            "supplier_name": supplier["name"],
            "lead_time_days": supplier["lead_time_days"],
            "min_order_qty": supplier["min_order_qty"],
            "contact_email": supplier["contact_email"],
        }
