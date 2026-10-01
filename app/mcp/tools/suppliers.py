"""Supplier tools."""

from typing import Annotated

from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from app.db import get_supabase


class SupplierInfo(BaseModel):
    sku: str
    product_name: str
    supplier_name: str
    lead_time_days: int | None = Field(
        default=None, description="Days from placing an order to delivery."
    )
    min_order_qty: int | None = Field(
        default=None, description="Smallest quantity this supplier accepts per order."
    )
    contact_email: str | None = None


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
    ) -> SupplierInfo:
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
            raise ToolError(
                f"Could not query supplier for {sku}: {type(exc).__name__}: {exc}"
            ) from exc

        if not result.data:
            raise ToolError(f"No product with SKU '{sku}'.")

        product = result.data[0]
        supplier = product["suppliers"]
        if not supplier:
            raise ToolError(f"Product {sku} has no supplier assigned.")

        return SupplierInfo(
            sku=product["sku"],
            product_name=product["name"],
            supplier_name=supplier["name"],
            lead_time_days=supplier["lead_time_days"],
            min_order_qty=supplier["min_order_qty"],
            contact_email=supplier["contact_email"],
        )
