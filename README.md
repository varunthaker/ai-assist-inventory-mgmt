# AI Warehouse Inventory Assistant

FastAPI + Supabase (Postgres) backend with a LangChain agent that answers
inventory questions using tools served by an MCP server.

## Structure

One process on port 8000 serves both the REST API and the MCP server (mounted
at `/mcp`). The agent reaches its tools through that `/mcp` endpoint, so the
same server can also be used by any other MCP client.

```
ai-asist-warehouse/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI app; also mounts the MCP server at /mcp
│   │   ├── config.py        # env vars
│   │   ├── db.py            # Supabase client (API routes + MCP tools)
│   │   ├── agent.py         # BASE agent — no MCP code, just gets a tool list
│   │   ├── routes/
│   │   │   ├── health.py    # GET /health
│   │   │   └── chat.py      # POST /chat, GET /chat/tools
│   │   └── mcp/
│   │       ├── server.py    # MCP server, auto-registers tools/
│   │       ├── client.py    # backend side: discovers tools over the wire
│   │       └── tools/
│   │           ├── __init__.py   # auto-discovers tool modules
│   │           ├── products.py         # list_products, get_stock_level, list_low_stock_items
│   │           ├── suppliers.py        # check_supplier_lead_time
│   │           └── purchase_orders.py  # create_purchase_order (the only write)
│   ├── requirements.txt
│   └── .env.example
├── sql/
│   └── schema.sql           # suppliers / products / purchase_orders
└── README.md
```

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# fill in the values from
# Supabase dashboard -> Project Settings -> API
```

### What the variables mean

| Variable | Supabase calls it | Respects RLS? | Used by |
|---|---|---|---|
| `SUPABASE_URL` | Project URL (`https://<ref>.supabase.co`) | n/a | backend + frontend |
| `SUPABASE_SERVICE_ROLE_KEY` | `service_role` / `sb_secret_...` | **No — bypasses it** | backend only |
| `SUPABASE_ANON_KEY` | `anon` / `sb_publishable_...` | Yes | React frontend (later) |

Only `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` are required to boot.

The backend uses the **service_role** key: it runs server-side so the key is
never exposed, and bypassing RLS means `/health` counts real rows instead of
returning `0` because no access policy exists yet. That key is full database
access — `.env` is gitignored, and it must never reach the frontend.

## Database

Tables already exist in your Supabase project; `sql/schema.sql` is the
checked-in copy of that schema and is safe to re-run.

## Run

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

On startup it prints the tool modules it registered:

```
MCP tool modules: products
```

The MCP endpoint is http://127.0.0.1:8000/mcp. If you run uvicorn on another
host or port, set `MCP_SERVER_URL` in `.env` to match.

The `mcp` package is pinned below 2.0 because `langchain-mcp-adapters` requires
it, so the server uses the 1.x class `FastMCP` (renamed `MCPServer` in 2.x).

## Verify

```bash
curl http://127.0.0.1:8000/health
```

Healthy:

```json
{"status": "ok", "database": "connected", "products_count": 0}
```

If Supabase is unreachable or misconfigured the route returns HTTP 503 with
`"status": "degraded"` and the underlying error message.

### Test the agent

Check which tools the agent discovered — no LLM call, so this is free:

```bash
curl http://127.0.0.1:8000/chat/tools
```

```json
{"count": 1, "tools": [{"name": "list_products", "description": "List every product ..."}]}
```

Then talk to it:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{"message": "list all products"}'
```

```json
{"reply": "You have 3 products in inventory: ..."}
```

`POST /chat` returns HTTP 503 with the underlying reason if the MCP endpoint is
unreachable (e.g. `MCP_SERVER_URL` points at the wrong port) or
`OPENAI_API_KEY` is missing.

Interactive docs: http://127.0.0.1:8000/docs

## How dynamic tool loading works

The goal: adding a tool means adding **one file** to `backend/app/mcp/tools/`.
Neither `server.py`, `client.py` nor `agent.py` is ever edited.

**1. The MCP server auto-registers tool modules.** `tools/__init__.py` walks the
package with `pkgutil.iter_modules()`, imports each module, and calls its
`register(server)` function. Each module registers its own functions with
`@server.tool(...)`. Drop in `suppliers.py` with a `register()` and it is served.

**2. The client discovers tools over the wire.** `app/mcp/client.py` never names
a tool. On the first request the agent asks it for tools, and it calls:

```python
return await _mcp_client.get_tools()
```

That issues an MCP `tools/list` call to the server, which answers with each
tool's name, description, and JSON-Schema arguments — all derived from your
Python type hints and docstrings. `langchain-mcp-adapters` converts each one
into a LangChain `StructuredTool`.

**3. The agent gets whatever came back.** `agent.py` has no MCP code:

```python
tools = await get_tools()
_agent = create_agent(model=model, tools=tools, system_prompt=SYSTEM_PROMPT)
```

The tool list is data, not code. The LLM reads the descriptions and decides
which tool to call; `create_agent` runs the call loop. That is why the tool
description in `products.py` is written for a reader — it is the only thing the
model uses to decide whether the tool is relevant.

**Caching:** the agent is built once and reused, so `tools/list` is not re-sent
on every request. A new tool is picked up after a restart (`--reload`
does this automatically when you save the file).

## Adding a tool later

1. Create `backend/app/mcp/tools/<name>.py` with a `register(server)` function.
2. Restart the backend (automatic with `--reload`).
3. `curl http://127.0.0.1:8000/chat/tools` — it is there.

No edits to `server.py`, `client.py`, `agent.py`, or `chat.py`.
