"""Chat route: POST /chat -> base agent -> tools -> reply.

This route knows nothing about which tools exist. It passes the message to
run_agent() and returns whatever the agent says, so new MCP tools need no
change here either.
"""

import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.agent import run_agent
from app.mcp.client import list_available_tools

router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, examples=["list all products"])
    conversation_id: str | None = Field(
        default=None,
        description=(
            "Continue an existing conversation. Omit to start a new one; the "
            "response returns the id to send with follow-up messages."
        ),
    )


class ToolCallInfo(BaseModel):
    """A tool the agent used, so the frontend can render its data.

    `result` is the tool's own JSON (e.g. a product list for a table, an order
    for a card, policy passages for citations). Calls with `error: true` were
    failed attempts -- often retried with corrected arguments.
    """

    name: str = Field(examples=["list_low_stock_items"])
    args: dict[str, Any] = Field(examples=[{"category": "safety"}])
    result: Any = None
    error: bool = False


class ChatResponse(BaseModel):
    conversation_id: str
    reply: str
    tool_calls: list[ToolCallInfo] = Field(
        default_factory=list,
        description="Tools called this turn, in order.",
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Send a message to the warehouse agent and get its reply.

    Messages with the same conversation_id share history (kept in server
    memory until restart), so follow-ups like "order 20 of those" work.
    """
    conversation_id = request.conversation_id or str(uuid.uuid4())
    try:
        answer = await run_agent(request.message, conversation_id)
    except Exception as exc:  # noqa: BLE001 - surface the cause to the caller
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                f"{type(exc).__name__}: {exc} "
                "(is the MCP server running, and is OPENAI_API_KEY set?)"
            ),
        ) from exc
    return ChatResponse(
        conversation_id=conversation_id,
        reply=answer.text,
        tool_calls=[
            ToolCallInfo(name=c.name, args=c.args, result=c.result, error=c.error)
            for c in answer.tool_calls
        ],
    )


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
