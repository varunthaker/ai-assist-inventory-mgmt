"""FastAPI application entrypoint.

Run from the backend/ directory:
    uvicorn app.main:app --reload

Serves the REST API and the MCP server (at /mcp) from one process.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.mcp.server import registered, server as mcp_server
from app.routes import chat, documents, health

# Build the MCP ASGI app up front: this also creates the session manager that
# the lifespan below has to run.
mcp_app = mcp_server.streamable_http_app()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # A mounted sub-app's own lifespan is not run by FastAPI, so start the MCP
    # session manager here.
    async with mcp_server.session_manager.run():
        print(f"MCP tool modules: {', '.join(registered) or '(none)'}")
        yield


app = FastAPI(
    title="AI Warehouse Inventory Assistant",
    description="Backend API for warehouse inventory management.",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(documents.router)


@app.get("/")
def root() -> dict:
    """Basic index so hitting the server root is not a 404."""
    return {
        "service": "warehouse-assistant-api",
        "version": "0.1.0",
        "health": "/health",
        "chat": "POST /chat",
        "documents": "POST /documents",
        "mcp": "/mcp",
    }


# Mounted last so the routes above take precedence; the MCP app only serves
# /mcp and 404s everything else.
app.mount("/", mcp_app)
