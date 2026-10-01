"""The backend's connection to the MCP server.

Tools are discovered at runtime, never named here: get_tools() performs an MCP
`tools/list` call and converts each returned tool -- its name, description and
JSON-Schema arguments -- into a LangChain tool the agent can call.
"""

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.config import settings

# One client for the whole app. The connection name ("warehouse") is arbitrary;
# it only labels this server in the client's registry. Adding a second MCP
# server later means adding another entry to this dict -- nothing else changes.
_mcp_client = MultiServerMCPClient(
    {
        "warehouse": {
            "url": settings.mcp_server_url,
            "transport": "streamable_http",
        }
    }
)


async def get_tools() -> list[BaseTool]:
    """Return every tool the MCP server currently exposes, as LangChain tools."""
    return await _mcp_client.get_tools()


async def list_available_tools() -> list[dict[str, str]]:
    """Return name + description of each tool (for debugging)."""
    tools = await get_tools()
    return [{"name": t.name, "description": t.description or ""} for t in tools]
