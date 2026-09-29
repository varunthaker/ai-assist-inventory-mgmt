"""Policy tools: semantic search over uploaded procurement policy / SOP PDFs."""

from typing import Annotated

from pydantic import Field

from app.rag.search import search_documents


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
    ) -> dict:
        try:
            matches = search_documents(query, top_k)
        except Exception as exc:  # noqa: BLE001 - keep the cause in the agent's context
            return {"error": f"Policy search failed: {type(exc).__name__}: {exc}"}

        if not matches:
            return {
                "query": query,
                "count": 0,
                "message": "No relevant policy passage found. Do not guess a policy.",
            }
        return {
            "query": query,
            "count": len(matches),
            "results": [
                {
                    "source": m["title"],
                    "pages": (
                        str(m["page_start"])
                        if m["page_start"] == m["page_end"]
                        else f"{m['page_start']}-{m['page_end']}"
                    ),
                    "similarity": round(m["similarity"], 3),
                    "text": m["content"],
                }
                for m in matches
            ],
        }
