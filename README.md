# AI Warehouse Inventory Assistant

A FastAPI backend with an LLM agent that answers warehouse questions by
combining two kinds of knowledge:

- **Structured data (MCP tools)** — stock levels, low-stock reports, supplier
  lead times and purchase orders, from Supabase Postgres.
- **Documents (RAG)** — procurement policies and SOPs uploaded as PDFs,
  searched by meaning with pgvector.

The agent decides per question which tools to use, and can combine them:
*"Pallets are low — how many must I order and who approves it?"* uses stock,
supplier and policy lookups in one answer.

The React frontend lives in a separate repository; this repo is the backend.
Requirements and status: [REQUIREMENTS.md](REQUIREMENTS.md).

## Architecture

One process on port 8000 serves everything:

```
                 ┌──────────────────── FastAPI (port 8000) ────────────────────┐
 React app ────► │ POST /chat ─► agent (LangChain) ─► MCP client ──┐           │
 (other repo)    │                     ▲                           ▼           │
                 │                     │ LLM (Groq / OpenAI)   /mcp  MCP server │ ◄── other MCP clients
                 │                                                 │  tools/   │
                 │ POST /documents ─► RAG pipeline                 │           │
                 └──────────────────────────┬──────────────────────┼───────────┘
                                            ▼                      ▼
                                  OpenAI embeddings      Supabase Postgres + pgvector
```

The agent reaches its tools through the `/mcp` endpoint, not by importing them,
so the same tools are available to any MCP client.

## Structure

```
ai-asist-warehouse/
├── app/
│   ├── main.py            # FastAPI app, CORS, mounts the MCP server at /mcp
│   ├── config.py          # all settings, from .env
│   ├── db.py              # Supabase client
│   ├── agent.py           # the agent: model, memory, tool-call metadata (no MCP code)
│   ├── routes/
│   │   ├── health.py      # GET /health
│   │   ├── chat.py        # POST /chat, GET /chat/tools
│   │   └── documents.py   # POST/GET /documents, DELETE /documents/{title}
│   ├── mcp/
│   │   ├── server.py      # MCP server, auto-registers tools/
│   │   ├── client.py      # discovers the tools over the wire for the agent
│   │   └── tools/         # one module per tool group, auto-discovered
│   │       ├── products.py         # list_products, get_stock_level, list_low_stock_items
│   │       ├── suppliers.py        # check_supplier_lead_time
│   │       ├── purchase_orders.py  # create_purchase_order (the only write)
│   │       └── policy.py           # search_procurement_policy (RAG)
│   └── rag/               # PDF -> text -> chunks -> embeddings -> DB, and search
│       ├── pdf.py         # extract text per page
│       ├── chunking.py    # ~500-token chunks, 75-token overlap, page ranges
│       ├── embeddings.py  # OpenAI text-embedding-3-small
│       ├── store.py       # save / list / delete in sop_documents
│       └── search.py      # similarity search via match_sop_documents
├── sql/
│   ├── schema.sql              # suppliers / products / purchase_orders
│   ├── sop_documents.sql       # pgvector + document chunks table + index
│   └── match_sop_documents.sql # similarity search function
├── sample_docs/           # supplier-policy.pdf (+ .md source) for testing RAG
├── requirements.txt
├── .env.example           # copy to .env (gitignored) and fill in
├── REQUIREMENTS.md
└── README.md
```

## Setup

### 1. Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### 2. Database (Supabase SQL editor)

Run these once, in order. All are safe to re-run.

| File | Creates |
|---|---|
| `sql/schema.sql` | `suppliers`, `products`, `purchase_orders` |
| `sql/sop_documents.sql` | the pgvector extension, the `sop_documents` chunk table, an HNSW index |
| `sql/match_sop_documents.sql` | `match_sop_documents()` — the similarity search (the REST client cannot sort by vector distance itself) |

`vector(1536)` in the SQL must match the embedding model. Changing the model
means changing that number, recreating the table and re-uploading every PDF.

### 3. Environment variables (`.env`)

| Variable | Required | What it is |
|---|---|---|
| `SUPABASE_URL` | yes | Project URL, `https://<ref>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | yes | `service_role` / `sb_secret_...` key. Bypasses RLS — backend only |
| `SUPABASE_ANON_KEY` | no | Public key; not used by the backend |
| `OPENAI_API_KEY` | for `/chat` | Key for the **chat** LLM — an OpenAI key, or a Groq key (`gsk_...`) |
| `OPENAI_BASE_URL` | no | Empty for OpenAI; `https://api.groq.com/openai/v1` for Groq |
| `OPENAI_MODEL` | no | Default `gpt-4o-mini`. Recommended: **`gpt-5.4-mini`** (OpenAI). Also works: `openai/gpt-oss-20b` on Groq |
| `OPENAI_REASONING_EFFORT` | no | Reasoning models only. **`none` for gpt-5.x** (tools + reasoning aren't allowed on the chat API), **`low` for Groq gpt-oss-20b** (see Troubleshooting) |
| `EMBEDDING_API_KEY` | for documents | **OpenAI** key for embeddings — separate because Groq has no embeddings |
| `EMBEDDING_MODEL` / `EMBEDDING_DIMENSIONS` | no | Default `text-embedding-3-small` / `1536`; must match the SQL |
| `CORS_ORIGINS` | no | Browser origins allowed to call the API. Default: the Vite dev server, `http://localhost:5173` and `http://127.0.0.1:5173` |
| `MCP_SERVER_URL` | no | Where the agent finds `/mcp`. Change only if uvicorn runs on another host/port |
| `MCP_ALLOWED_HOSTS` | no | Public hostnames allowed to reach `/mcp`, e.g. an ngrok domain (otherwise 421) |

Only the two Supabase values are needed to boot; `/health` works without any
LLM key. `.env` is gitignored — never commit keys or put them in `.env.example`.

## Run

All commands run from the repository root.

```bash
source .venv/bin/activate
uvicorn app.main:app --reload
```

On startup it prints the registered tool modules:

```
MCP tool modules: policy, products, purchase_orders, suppliers
```

- API docs (try every endpoint, including PDF upload): http://127.0.0.1:8000/docs
- MCP endpoint: http://127.0.0.1:8000/mcp

`--reload` restarts on `.py` changes but **not** on `.env` changes — restart
manually after editing `.env`.

## API

### `GET /health`

Checks the Supabase connection.

```json
{"status": "ok", "database": "connected", "products_count": 5}
```

HTTP 503 with `"status": "degraded"` and the error if Supabase is unreachable.

### `POST /chat`

Send a message; get the agent's reply plus the tools it used.

```bash
curl -X POST http://127.0.0.1:8000/chat -H 'Content-Type: application/json' \
  -d '{"message": "Which safety items are low, and who approves orders above 5000 euros?"}'
```

```json
{
  "conversation_id": "bad67739-ccad-4302-bf2f-fd2add609b65",
  "reply": "**Low-stock safety items** ... (procurement-policy.pdf, p. 1)",
  "tool_calls": [
    {"name": "list_low_stock_items", "args": {"category": "safety"},
     "result": {"category": "safety", "count": 1, "items": [...]}, "error": false},
    {"name": "search_procurement_policy", "args": {"query": "approval above 5000 euros"},
     "result": {"count": 3, "results": [{"source": "...", "pages": "1", "similarity": 0.44, "text": "..."}]},
     "error": false}
  ]
}
```

- **Conversations:** omit `conversation_id` to start a new one; send the
  returned id with follow-ups so "order 20 of those" works. The agent remembers
  the **last 10 questions** (`MAX_QUESTIONS` in `agent.py`) with their answers
  and tool calls. History is kept in server memory and is **lost on restart**.
- **`tool_calls`:** the tools called this turn, in order, with their JSON
  results — for rendering tables, order cards and citations. `error: true`
  marks failed attempts (e.g. a guessed SKU that doesn't exist), which the agent
  usually retries.
- HTTP 503 with the reason if the LLM key is missing or `/mcp` is unreachable.

### `GET /chat/tools`

The tools the agent can see — no LLM call.

### Documents (RAG)

| Endpoint | Does |
|---|---|
| `POST /documents` (multipart `file`) | Upload a PDF: extract → chunk → embed → save. Same file name **replaces** the stored version. Returns 201 with `{title, pages, chunks, replaced_chunks, embedding_tokens}` |
| `GET /documents` | List stored documents with chunk/page counts and upload time |
| `DELETE /documents/{title}` | Delete a document by file name (404 if unknown) |

```bash
curl -X POST http://127.0.0.1:8000/documents -F "file=@sample_docs/supplier-policy.pdf"
```

Rejected uploads: non-PDF files (415), over 20 MB (413), damaged or
password-protected PDFs and scans with no text layer (422 — scans would need OCR).

## Tools

| Tool | Input | Returns |
|---|---|---|
| `list_products` | — | every product with stock, threshold and unit price (EUR) |
| `get_stock_level` | `sku` | name, quantity, unit, threshold, unit price |
| `list_low_stock_items` | `category?` | products below their reorder threshold, with shortfall |
| `check_supplier_lead_time` | `sku` | supplier name, lead time, minimum order quantity, email |
| `create_purchase_order` | `sku`, `quantity` | new order id and status. Rejects unknown SKUs, quantity ≤ 0, and quantities below the supplier minimum. The agent only uses it when explicitly asked |
| `search_procurement_policy` | `query`, `top_k?` (1–5, default 3) | most relevant passages with source file, pages and similarity; "no relevant passage" below 0.2 similarity |

## How RAG works here

**Ingestion** (`POST /documents`):

1. **Extract** text page by page with pypdf (`rag/pdf.py`).
2. **Chunk** into ~500-token pieces with 75 tokens of overlap, splitting at
   paragraphs, then lines, sentences, words; each chunk records the pages it
   spans (`rag/chunking.py`).
3. **Embed** each chunk with `text-embedding-3-small` (1536 numbers per chunk),
   prefixed with the file name for context (`rag/embeddings.py`).
4. **Save** to `sop_documents`, replacing any previous version of the file
   (`rag/store.py`). Embedding happens first, so an OpenAI failure never touches
   the database.

**Search** (`search_procurement_policy`): the question is embedded with the
same model, `match_sop_documents` returns the closest chunks by cosine
similarity, and chunks below 0.2 are dropped. With this model, relevant matches
typically score 0.3–0.5 and unrelated text ~0.03.

## How dynamic tool loading works

Adding a tool means adding **one file** to `app/mcp/tools/` — no edits
to `server.py`, `client.py`, `agent.py` or `chat.py`.

1. **The server auto-registers tool modules.** `tools/__init__.py` imports every
   module in the package and calls its `register(server)`, which registers
   functions with `@server.tool(...)`.
2. **The client discovers tools over the wire.** `mcp/client.py` sends an MCP
   `tools/list` request; each tool's name, description and JSON-Schema
   arguments (from type hints) become a LangChain tool.
3. **The agent gets whatever came back.** `agent.py` never names a tool. The LLM
   picks tools from their descriptions alone — which is why descriptions are
   written for a reader.

The agent is built once and cached; new tools are picked up on restart
(automatic with `--reload`).

### Adding a tool

1. Create `app/mcp/tools/<name>.py` with a `register(server)` function.
2. Save — `--reload` restarts the server.
3. `curl http://127.0.0.1:8000/chat/tools` — it is listed.

Give each tool a **typed return model** (a Pydantic `BaseModel`, with
`Field(description=...)` on its fields): the MCP server then publishes an
`outputSchema` for the tool, so clients know the exact result shape. A plain
`dict` return publishes no schema. On failure **raise `ToolError("...")`**: the
result is marked `isError`, the message is kept, and the agent receives it as a
failed tool call it can explain or retry.

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `/chat` returns `{"reply": ""}` or 503 `output_parse_failed` | Groq gpt-oss-20b at default reasoning effort fails on multi-tool questions. Set `OPENAI_REASONING_EFFORT=low` |
| 503 "Function tools with reasoning_effort are not supported" | gpt-5.x with reasoning on the chat completions API. Set `OPENAI_REASONING_EFFORT=none` |
| Agent places orders without checking policy / misstates approval rules | Weak model. gpt-oss-20b did this in testing; `gpt-5.4-mini` followed the rules |
| Upload fails with 401 "Invalid API Key" | The embeddings request went to Groq. `EMBEDDING_BASE_URL` must be empty or OpenAI's URL; the default already is |
| Upload fails with 429 `insufficient_quota` | The OpenAI account has no API credit (Settings → Billing) |
| `/mcp` via ngrok returns 421 | Add the ngrok hostname to `MCP_ALLOWED_HOSTS`, then restart |
| `/mcp` returns 406 | Expected for browsers / plain curl — only MCP clients send the required `Accept` header |
| Browser: "blocked by CORS policy" | Add the frontend's origin to `CORS_ORIGINS`, then restart |
| Follow-up questions lose context | The server restarted (history is in memory), or the request lacked `conversation_id` |

## Known limitations

- **No authentication.** Fine on localhost. Anything exposed publicly (e.g. via
  ngrok) lets anyone chat, create purchase orders, and upload/delete/search
  documents — stop the tunnel when not in use.
- **Conversation history is in memory** and lost on restart.
- **Re-upload is two steps** (delete old chunks, insert new). If the insert
  fails, the old version is already gone — the error says to re-upload.
- `mcp` is pinned below 2.0 because `langchain-mcp-adapters` requires it.
