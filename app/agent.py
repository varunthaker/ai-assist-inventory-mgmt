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
import json
from dataclasses import dataclass, field
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import before_model
from langchain_core.messages import RemoveMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.message import REMOVE_ALL_MESSAGES

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

# Conversation memory: stores each conversation's messages by conversation id
# (LangGraph calls it thread_id) and feeds them back to the model on the next
# turn. Kept in RAM -- lost when the server restarts (including --reload).
# Module-level so reset_agent() does not wipe conversations.
_memory = InMemorySaver()

# How many user questions a conversation remembers, counting the current one.
# Older questions -- with their answers and tool calls -- are forgotten.
MAX_QUESTIONS = 10


@before_model
def _keep_recent_questions(state: dict, runtime: Any) -> dict | None:
    """Trim the conversation to its last MAX_QUESTIONS questions.

    Runs before every model call. It cuts only at the start of a user
    question, so a tool call is never separated from its result (the model API
    rejects that). The trimmed history replaces the stored one, so memory use
    stays bounded too.
    """
    messages = state["messages"]
    questions = [i for i, m in enumerate(messages) if m.type == "human"]
    if len(questions) <= MAX_QUESTIONS:
        return None
    keep_from = questions[-MAX_QUESTIONS]
    return {"messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *messages[keep_from:]]}


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

        _agent = create_agent(
            model=model,
            tools=tools,
            system_prompt=SYSTEM_PROMPT,
            middleware=[_keep_recent_questions],
            checkpointer=_memory,
        )
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


@dataclass
class ToolCall:
    """One tool the agent called during a turn, with what it got back."""

    id: str
    name: str
    args: dict[str, Any]
    result: Any = None  # parsed JSON when the tool returned JSON, else text
    error: bool = False


@dataclass
class AgentReply:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


def _tool_result(message: Any) -> Any:
    """Parse a tool message's content back into the tool's return value.

    MCP tools return JSON, which arrives as text content blocks; turning it
    back into a dict lets the frontend render tables and cards from it.
    """
    text = _message_text(message)
    try:
        return json.loads(text)
    except ValueError:
        return text


def _tool_calls(messages: list[Any]) -> list[ToolCall]:
    """Pair each tool call the model made with the result that came back.

    Generic over tools: nothing here knows which tools exist.
    """
    calls: dict[str, ToolCall] = {}
    for message in messages:
        for tc in getattr(message, "tool_calls", None) or []:
            calls[tc["id"]] = ToolCall(id=tc["id"], name=tc["name"], args=tc["args"])
        call_id = getattr(message, "tool_call_id", None)
        if call_id in calls:
            call = calls[call_id]
            call.result = _tool_result(message)
            # Our tools report failures as {"error": ...} with a "success"
            # status, so check both.
            call.error = getattr(message, "status", None) == "error" or (
                isinstance(call.result, dict) and "error" in call.result
            )
    return list(calls.values())


async def run_agent(user_message: str, conversation_id: str) -> AgentReply:
    """Run one turn of a conversation: the reply plus the tools called this turn.

    Earlier turns of the same conversation_id are loaded from memory, so the
    model sees the whole conversation. This is the single entrypoint the /chat
    route calls; its signature does not change as tools are added.
    """
    agent = await get_agent()
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": user_message}]},
        config={"configurable": {"thread_id": conversation_id}},
    )
    messages = result["messages"]

    # result["messages"] is the whole conversation; only report tool calls
    # made after this turn's user message.
    turn_start = max(i for i, m in enumerate(messages) if getattr(m, "type", None) == "human")
    return AgentReply(
        text=_message_text(messages[-1]),
        tool_calls=_tool_calls(messages[turn_start:]),
    )
