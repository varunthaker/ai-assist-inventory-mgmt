"""Base agent: a single LangChain agent over whatever tools exist.

This module deliberately contains NO tool-specific code and does not know
where tools come from. It asks app.mcp.client for the current tool list and
hands it to the agent, so adding a tool module makes it available here after a
restart -- with no edit to this file.

Flow:
    get_tools()                        -> LangChain tools
    create_agent(model, tools)         -> agent that can call any of them
    agent.ainvoke({"messages": [...]}) -> LLM decides which tool(s) to call
"""

import asyncio
from typing import Any

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from app.config import settings
from app.mcp.client import get_tools

SYSTEM_PROMPT = (
    "You are a warehouse inventory assistant. Answer questions about inventory "
    "using the tools available to you. Always call a tool to get real data "
    "rather than guessing or inventing product information. Present results "
    "clearly and concisely; use a short table or list when showing several "
    "products. If a tool returns no rows, say the inventory is empty rather "
    "than making up products. Never create, change or delete anything (such "
    "as placing an order) unless the user explicitly asks for it. If a tool "
    "returns an error, tell the user what went wrong. When an answer is based "
    "on a document, cite it in plain text as (file name, p. N), e.g. "
    "(procurement-policy.pdf, p. 2); if no relevant passage is found, say so "
    "instead of guessing."
)

_agent: Any | None = None
_agent_lock = asyncio.Lock()


async def get_agent() -> Any:
    """Build the agent once, then reuse it.

    Tool discovery is a network round-trip, so it happens on the first request
    rather than at import time -- the backend still starts if the tool server
    is not running yet.
    """
    global _agent
    if _agent is not None:
        return _agent

    async with _agent_lock:
        # Re-check inside the lock: concurrent first requests must not each
        # build their own agent.
        if _agent is not None:
            return _agent

        settings.validate_openai()

        # Discovered at runtime -- nothing here is hardcoded.
        tools = await get_tools()

        model = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            reasoning_effort=settings.openai_reasoning_effort or None,
            temperature=0,
        )

        _agent = create_agent(model=model, tools=tools, system_prompt=SYSTEM_PROMPT)
        return _agent


def reset_agent() -> None:
    """Drop the cached agent so the next call rediscovers tools.

    Call this after adding a tool if you don't want to restart the backend.
    """
    global _agent
    _agent = None


def _message_text(message: Any) -> str:
    """Flatten a model message into plain text.

    Content is usually a string, but can be a list of content blocks depending
    on the model and whether tool calls were involved.
    """
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        ]
        return "".join(parts).strip()
    return str(content)


async def run_agent(user_message: str) -> str:
    """Run one turn through the agent and return its natural-language reply.

    This is the single entrypoint the /chat route calls. Its signature does not
    change as tools are added.
    """
    agent = await get_agent()
    result = await agent.ainvoke({"messages": [{"role": "user", "content": user_message}]})
    return _message_text(result["messages"][-1])
