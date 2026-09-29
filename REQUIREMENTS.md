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
| `search_procurement_policy` | `query`, `top_k?` | top matching policy chunk(s) + source title + pages | done |

PDF ingestion — **done**: `POST /documents` (upload → extract → chunk → embed →
save, replaces same file name), `GET /documents`, `DELETE /documents/{title}`.
Code in `backend/app/rag/`. Table created (`sql/sop_documents.sql`).

How it is built:
1. `pgvector` enabled in Supabase.
2. `sop_documents` table: `id`, `title`, `chunk_index`, `content`,
   `page_start`, `page_end`, `embedding vector(1536)`, `created_at`.
3. HNSW index on `embedding` (`vector_cosine_ops`).
4. Search query — SQL function `match_sop_documents` called via `rpc()`
   (`sql/match_sop_documents.sql`, run). Chosen over a direct Postgres
   connection for simpler setup; trade-off: re-upload delete + insert is not
   one transaction.
5. Embedding model — OpenAI `text-embedding-3-small` (1536 dims), own key
   `EMBEDDING_API_KEY` (Groq, the chat LLM, has no embeddings).
6. Source documents: procurement policies / SOPs, uploaded as PDFs.
7. Ingestion via `POST /documents`: extract → chunk (500 tokens, 75 overlap) →
   embed (title-prefixed) → replace rows for that file name.
8. The tool: embed the query → `match_sop_documents` (min similarity 0.2) →
   top chunks with source, pages and similarity.

## Later

- `POST /chat` returns metadata about which tool(s) were called, so the React
  frontend can render tables / cards / source citations.
- React frontend (separate).
