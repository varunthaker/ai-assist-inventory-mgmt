"""Everything MCP lives in this package.

server.py -- the MCP server (run as its own process: python -m app.mcp.server)
client.py -- the backend's connection to it; hands the agent LangChain tools
tools/    -- one module per tool group, auto-registered on the server
"""
