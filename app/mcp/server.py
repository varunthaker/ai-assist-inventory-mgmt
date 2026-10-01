"""MCP server for the warehouse assistant.

Not run on its own: app/main.py mounts it into the FastAPI app, so it is served
from the same process and port at /mcp (http://127.0.0.1:8000/mcp).
"""

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.config import settings
from app.mcp import tools

# DNS-rebinding protection: only these Host/Origin headers may reach /mcp,
# anything else gets 421. Localhost always; public hostnames (ngrok, a deployed
# domain) are opted in via MCP_ALLOWED_HOSTS.
_transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=True,
    allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*", *settings.mcp_allowed_hosts],
    allowed_origins=[
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
        *(f"https://{h}" for h in settings.mcp_allowed_hosts),
    ],
)

# FastMCP is the mcp 1.x name for this class (2.x renamed it MCPServer).
# We stay on 1.x because langchain-mcp-adapters requires mcp<2, and the
# server and client share one venv.
server = FastMCP(
    name="warehouse-inventory",
    instructions="Tools for querying warehouse inventory stored in Supabase.",
    streamable_http_path="/mcp",
    transport_security=_transport_security,
)

# Discovers and registers every tool module under tools/ -- see tools/__init__.py
registered = tools.register_all(server)
