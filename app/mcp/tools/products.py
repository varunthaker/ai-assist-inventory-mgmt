"""Product tools: listing, single-SKU stock lookup, low-stock report."""

from typing import Annotated

from pydantic import Field

from app.db import get_supabase

# Columns exposed to the agent. Kept explicit rather than "*" so internal
# fields (id, supplier_id, timestamps) stay out of the LLM's context.
PRODUCT_COLUMNS = "sku, name, category, quantity, reorder_threshold, unit"


def register(server) -> None:
    """Register product tools on the MCP server."""

    # Errors are returned rather than raised: the MCP SDK wraps a raised
    # exception in a generic "Error executing tool ..." message, which hides
    # the cause from the agent. Returning it keeps the reason in the model's
    # context so it can tell the user what actually went wrong.

    @server.tool(
        description=(
            "List every product in the warehouse inventory. Returns each "
            "product's SKU, name, category, current quantity on hand, the "
            "reorder threshold at which it should be restocked, and its unit "
            "of measure. Use this for questions about the whole inventory; "
            "prefer get_stock_level for one product and list_low_stock_items "
            "for what needs restocking."
        )
    )
    def list_products() -> dict:
        try:
            result = (
                get_supabase()
                .table("products")
                .select(PRODUCT_COLUMNS)
                .order("name")
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Could not query products: {type(exc).__name__}: {exc}"}

        rows = result.data or []
        return {"count": len(rows), "products": rows}

    @server.tool(
        description=(
            "Get the current stock level of one product by its SKU. Returns "
            "the product name, quantity on hand, unit of measure, and reorder "
            "threshold. Use this when the user asks how many of a specific "
            "item are in stock. If you only know the product name, call "
            "list_products first to find its SKU."
        )
    )
    def get_stock_level(
        sku: Annotated[str, Field(description="Product SKU, e.g. 'PKG-BOX-002'.")],
    ) -> dict:
        sku = sku.strip().upper()
        try:
            result = (
                get_supabase()
                .table("products")
                .select(PRODUCT_COLUMNS)
                .eq("sku", sku)
                .limit(1)
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Could not query product {sku}: {type(exc).__name__}: {exc}"}

        if not result.data:
            return {"error": f"No product with SKU '{sku}'."}
        return result.data[0]

    @server.tool(
        description=(
            "List products that are low on stock, i.e. whose quantity on hand "
            "is below their reorder threshold, optionally filtered to one "
            "category (e.g. 'packaging', 'pallets', 'safety'). Each item "
            "includes the shortfall (threshold minus quantity). Use this for "
            "questions like 'what needs reordering?' or 'what is running low?'."
        )
    )
    def list_low_stock_items(
        category: Annotated[
            str | None,
            Field(description="Only include this category. Omit for all categories."),
        ] = None,
    ) -> dict:
        try:
            query = get_supabase().table("products").select(PRODUCT_COLUMNS)
            if category:
                # Case-insensitive exact match: categories are stored lowercase.
                query = query.ilike("category", category.strip())
            result = query.order("name").execute()
        except Exception as exc:  # noqa: BLE001
            return {"error": f"Could not query products: {type(exc).__name__}: {exc}"}

        # PostgREST cannot compare two columns in a filter, so the
        # quantity < reorder_threshold check happens here. Fine at this scale;
        # move it into a SQL view or function if the catalogue grows large.
        low = [
            {**row, "shortfall": row["reorder_threshold"] - row["quantity"]}
            for row in result.data or []
            if row["quantity"] < row["reorder_threshold"]
        ]
        return {"category": category, "count": len(low), "items": low}
