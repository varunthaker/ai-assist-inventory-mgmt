# Requirements

AI Warehouse Inventory Assistant: an agent that answers inventory questions and
takes procurement actions by combining **MCP tools** (structured lookups and
actions on Postgres) with **RAG** (similarity search over procurement policy
documents). Built in two parts.

## Part 1 — MCP tools (structured data)

Tools on the MCP server, backed by the existing Supabase tables
(`suppliers`, `products`, `purchase_orders`).

| Tool | Input | Returns | Status |
|---|---|---|---|
| `list_products` | — | every product with stock + threshold | done |
| `get_stock_level` | `sku` | name, quantity, unit | done |
| `list_low_stock_items` | `category?` | products where `quantity < reorder_threshold` | done |
| `check_supplier_lead_time` | `sku` | supplier name, `lead_time_days`, `min_order_qty` | done |
| `create_purchase_order` | `sku`, `quantity` | new order id + status | done |

Rules:
- `create_purchase_order` is the only write. It rejects unknown SKUs,
  non-positive quantities, and quantities below the supplier's `min_order_qty`.
- The agent only creates an order when the user explicitly asks for one.
- `/mcp` has no auth yet. Add it before exposing write tools publicly (ngrok).

## Part 2 — Vector DB / RAG (procurement policy)

| Tool | Input | Returns | Status |
|---|---|---|---|
| `search_procurement_policy` | `query` | top matching policy chunk(s) + source title | todo |

Needed:
1. Enable `pgvector` in Supabase.
2. `sop_documents` table: `id`, `title`, `chunk_index`, `content`,
   `embedding vector(N)`, `created_at` (does not exist yet).
3. HNSW index on `embedding` (`vector_cosine_ops`).
4. SQL function `match_sop_documents(query_embedding, match_count)`, called via
   `rpc()` — the Supabase client cannot order by vector distance directly.
5. Embedding model — **decision pending**. Groq (current LLM) has no embeddings.
   Options: OpenAI `text-embedding-3-small` (1536 dims) or local
   `all-MiniLM-L6-v2` (384 dims). The choice fixes `N`; ingest and query must
   use the same model.
6. Source documents: procurement policies / SOPs.
7. Ingestion script (separate from MCP): load → chunk (~500 tokens, overlap) →
   embed → insert.
8. The tool: embed the query → `match_sop_documents` → top chunks with title
   and similarity.

## Later

- `POST /chat` returns metadata about which tool(s) were called, so the React
  frontend can render tables / cards / source citations.
- React frontend (separate).
