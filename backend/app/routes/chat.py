"""Chat route: POST /chat -> base agent -> tools -> reply.

This route knows nothing about which tools exist. It passes the message to
run_agent() and returns whatever the agent says, so new MCP tools need no
change here either.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.agent import run_agent
from app.mcp.client import list_available_tools

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, examples=["list all products"])


class ChatResponse(BaseModel):
    reply: str


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Send a message to the warehouse agent and get its reply."""
    try:
        reply = await run_agent(request.message)
    except Exception as exc:  # noqa: BLE001 - surface the cause to the caller
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"{type(exc).__name__}: {exc} "
                "(is the MCP server running, and is OPENAI_API_KEY set?)"
            ),
        ) from exc
    return ChatResponse(reply=reply)


@router.get("/chat/tools")
async def tools() -> dict:
    """Show which tools the agent discovered from the MCP server.

    Useful for confirming a newly added MCP tool is visible without spending an
    LLM call.
    """
    try:
        discovered = await list_available_tools()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"{type(exc).__name__}: {exc} (is the MCP server running?)",
        ) from exc
    return {"count": len(discovered), "tools": discovered}
