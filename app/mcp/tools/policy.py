"""Policy tools: semantic search over uploaded procurement policy / SOP PDFs."""

from typing import Annotated

from mcp.server.fastmcp.exceptions import ToolError
from pydantic import BaseModel, Field

from app.rag.search import search_documents


class PolicyPassage(BaseModel):
    source: str = Field(description="File name of the document the passage comes from.")
    pages: str = Field(description="Page or page range, e.g. '2' or '1-2'.")
    similarity: float = Field(description="Cosine similarity to the query, 0-1 (higher is closer).")
    text: str = Field(description="The passage text.")


class PolicySearchResult(BaseModel):
    query: str
    count: int
    # `results: [{source, pages, text}]` is also the shape the chat UI turns
    # into source chips -- keep the field names stable.
    results: list[PolicyPassage]
    message: str | None = Field(
        default=None, description="Set when nothing relevant was found."
    )


def register(server) -> None:
    """Register policy tools on the MCP server."""

    @server.tool(
        description=(
            "Search the company's procurement policies and warehouse standard "
            "operating procedures (uploaded PDF documents) by meaning. Use this "
            "for questions about rules, approvals, limits, allowed suppliers, "
            "emergency orders, safety requirements or how something must be "
            "done -- anything answered by policy text rather than inventory "
            "data. Returns the most relevant passages with their source "
            "document and page numbers; base your answer on them and cite the "
            "source. Phrase the query as a short question or topic."
        )
    )
    def search_procurement_policy(
        query: Annotated[
            str,
            Field(description="What to look up, e.g. 'who approves orders above EUR 5,000'."),
        ],
        top_k: Annotated[
            int,
            Field(description="How many passages to return (1-5).", ge=1, le=5),
        ] = 3,
    ) -> PolicySearchResult:
        try:
            matches = search_documents(query, top_k)
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"Policy search failed: {type(exc).__name__}: {exc}") from exc

        passages = [
            PolicyPassage(
                source=m["title"],
                pages=(
                    str(m["page_start"])
                    if m["page_start"] == m["page_end"]
                    else f"{m['page_start']}-{m['page_end']}"
                ),
                similarity=round(m["similarity"], 3),
                text=m["content"],
            )
            for m in matches
        ]
        return PolicySearchResult(
            query=query,
            count=len(passages),
            results=passages,
            message=None if passages else "No relevant policy passage found. Do not guess a policy.",
        )
