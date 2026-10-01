"""Step 5: save chunks + vectors to sop_documents, and list / delete documents.

A document is identified by its title (the file name). Saving replaces any
previous version, so an edited policy never leaves stale rules searchable.
"""

import json
from collections import defaultdict

from app.db import get_supabase
from app.rag.chunking import Chunk

TABLE = "sop_documents"


def save_document(title: str, chunks: list[Chunk], vectors: list[list[float]]) -> int:
    """Replace the stored chunks of `title`. Returns how many old chunks it replaced.

    Call this only after embedding succeeded, so a failed embedding never
    touches the database. The delete and insert are two requests, not one
    transaction: if the insert fails, the old version is already gone and the
    error says to re-upload. The insert itself is a single request, so it
    stores either every chunk or none.
    """
    client = get_supabase()
    replaced = len(client.table(TABLE).delete().eq("title", title).execute().data or [])

    rows = [
        {
            "title": title,
            "chunk_index": c.index,
            "page_start": c.page_start,
            "page_end": c.page_end,
            "content": c.text,
            # pgvector parses its text form '[0.1, 0.2, ...]'.
            "embedding": json.dumps(v),
        }
        for c, v in zip(chunks, vectors, strict=True)
    ]
    try:
        # returning="minimal": don't send 1536 numbers per row back to us.
        client.table(TABLE).insert(rows, returning="minimal").execute()
    except Exception as exc:
        note = f" The previous {replaced} chunk(s) were already removed." if replaced else ""
        raise RuntimeError(
            f"Saving '{title}' failed: {type(exc).__name__}: {exc}.{note} Upload it again."
        ) from exc
    return replaced


def list_documents() -> list[dict]:
    """One entry per stored document: chunk count, pages, upload time."""
    rows = (
        get_supabase()
        .table(TABLE)
        .select("title, page_end, created_at")  # no embeddings: they are large
        .execute()
        .data
        or []
    )
    docs: dict[str, dict] = defaultdict(lambda: {"chunks": 0, "pages": 0, "uploaded_at": None})
    for row in rows:
        doc = docs[row["title"]]
        doc["chunks"] += 1
        doc["pages"] = max(doc["pages"], row["page_end"] or 0)
        doc["uploaded_at"] = max(filter(None, [doc["uploaded_at"], row["created_at"]]))
    return [{"title": title, **info} for title, info in sorted(docs.items())]


def delete_document(title: str) -> int:
    """Delete every chunk of `title`. Returns how many were deleted."""
    return len(get_supabase().table(TABLE).delete().eq("title", title).execute().data or [])
