"""Product tools: listing, single-SKU stock lookup, low-stock report."""

from typing import Annotated

from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from app.db import get_supabase

# Columns exposed to the agent. Kept explicit rather than "*" so internal
# fields (id, supplier_id, timestamps) stay out of the LLM's context.
PRODUCT_COLUMNS = "sku, name, category, quantity, reorder_threshold, unit, unit_price"


# Return models: typed returns make the MCP server publish an outputSchema
# for each tool, so clients know the exact shape of the result.
class Product(BaseModel):
    sku: str = Field(description="Stock keeping unit, e.g. 'PAL-STD-001'.")
    name: str
    category: str | None = None
    quantity: int = Field(description="Units currently on hand.")
    reorder_threshold: int = Field(description="Restock when quantity falls below this.")
    unit: str | None = Field(default=None, description="Unit of measure, e.g. 'pcs', 'rolls'.")
    unit_price: float | None = Field(
        default=None, description="Price per unit in EUR; null if unknown."
    )


class ProductList(BaseModel):
    count: int
    products: list[Product]


class LowStockItem(Product):
    shortfall: int = Field(description="reorder_threshold minus quantity.")


class LowStockReport(BaseModel):
    category: str | None = Field(description="The category filter used, or null for all.")
    count: int
    items: list[LowStockItem]


def register(server) -> None:
    """Register product tools on the MCP server."""

    # Failures raise ToolError: the MCP result is marked isError with this
    # message, and the agent receives it as a failed tool call it can explain
    # or retry (mcp 1.x keeps the message; see README).

    @server.tool(
        description=(
            "List every product in the warehouse inventory. Returns each "
            "product's SKU, name, category, current quantity on hand, the "
            "reorder threshold at which it should be restocked, its unit of "
            "measure and its unit price in EUR. Use this for questions about "
            "the whole inventory; prefer get_stock_level for one product and "
            "list_low_stock_items for what needs restocking."
        )
    )
    def list_products() -> ProductList:
        try:
            result = (
                get_supabase()
                .table("products")
                .select(PRODUCT_COLUMNS)
                .order("name")
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"Could not query products: {type(exc).__name__}: {exc}") from exc

        products = [Product(**row) for row in result.data or []]
        return ProductList(count=len(products), products=products)

    @server.tool(
        description=(
            "Get one product by its SKU: name, quantity on hand, unit of "
            "measure, reorder threshold and unit price in EUR. Use this when "
            "the user asks how many of a specific item are in stock or what it "
            "costs. If you only know the product name, call list_products "
            "first to find its SKU."
        )
    )
    def get_stock_level(
        sku: Annotated[str, Field(description="Product SKU, e.g. 'PKG-BOX-002'.")],
    ) -> Product:
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
            raise ToolError(f"Could not query product {sku}: {type(exc).__name__}: {exc}") from exc

        if not result.data:
            raise ToolError(f"No product with SKU '{sku}'.")
        return Product(**result.data[0])

    @server.tool(
        description=(
            "List products that are low on stock, i.e. whose quantity on hand "
            "is below their reorder threshold, optionally filtered to one "
            "category (e.g. 'packaging', 'pallets', 'safety'). Each item "
            "includes the shortfall (threshold minus quantity) and its unit "
            "price in EUR. Use this for questions like 'what needs "
            "reordering?' or 'what is running low?'."
        )
    )
    def list_low_stock_items(
        category: Annotated[
            str | None,
            Field(description="Only include this category. Omit for all categories."),
        ] = None,
    ) -> LowStockReport:
        try:
            query = get_supabase().table("products").select(PRODUCT_COLUMNS)
            if category:
                # Case-insensitive exact match: categories are stored lowercase.
                query = query.ilike("category", category.strip())
            result = query.order("name").execute()
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"Could not query products: {type(exc).__name__}: {exc}") from exc

        # PostgREST cannot compare two columns in a filter, so the
        # quantity < reorder_threshold check happens here. Fine at this scale;
        # move it into a SQL view or function if the catalogue grows large.
        items = [
            LowStockItem(**row, shortfall=row["reorder_threshold"] - row["quantity"])
            for row in result.data or []
            if row["quantity"] < row["reorder_threshold"]
        ]
        return LowStockReport(category=category, count=len(items), items=items)
