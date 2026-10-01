"""Similarity search over stored document chunks.

The question is embedded with the same model as the chunks (the golden rule),
then the database function match_sop_documents (sql/match_sop_documents.sql)
returns the closest chunks -- the REST client cannot sort by vector distance
itself.
"""

import json

from app.db import get_supabase
from app.rag.embeddings import embed_query

# Below this, a chunk is treated as unrelated. With text-embedding-3-small,
# relevant matches scored ~0.3-0.5 in testing and unrelated text ~0.03.
MIN_SIMILARITY = 0.2


def search_documents(query: str, top_k: int = 3) -> list[dict]:
    """Return up to top_k chunks most similar in meaning to `query`, best first."""
    result = (
        get_supabase()
        .rpc(
            "match_sop_documents",
            {
                "query_embedding": json.dumps(embed_query(query)),
                "match_count": top_k,
                "min_similarity": MIN_SIMILARITY,
            },
        )
        .execute()
    )
    return result.data or []
