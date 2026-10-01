"""Step 4: turn text into vectors with the embedding model.

The same model must embed both the stored chunks and every search query --
vectors from different models are not comparable. That is why the model and
its dimension live in config and are checked here.
"""

from dataclasses import dataclass
from functools import lru_cache

from openai import OpenAI

from app.config import settings
from app.rag.chunking import Chunk

# Texts sent per API request. OpenAI accepts up to 2048 inputs per call;
# smaller batches keep each request (and a failure) small.
_BATCH_SIZE = 100


@dataclass(frozen=True)
class Embedded:
    vectors: list[list[float]]
    tokens_used: int  # billed tokens, for cost visibility


@lru_cache(maxsize=1)
def _client() -> OpenAI:
    settings.validate_embeddings()
    return OpenAI(
        api_key=settings.embedding_api_key,
        base_url=settings.embedding_base_url,
    )


def embed_texts(texts: list[str]) -> Embedded:
    """Embed texts in batches; vectors come back in the same order."""
    vectors: list[list[float]] = []
    tokens = 0
    for i in range(0, len(texts), _BATCH_SIZE):
        response = _client().embeddings.create(
            model=settings.embedding_model,
            input=texts[i : i + _BATCH_SIZE],
        )
        # The API tags each result with its input index; sort to be safe.
        vectors.extend(d.embedding for d in sorted(response.data, key=lambda d: d.index))
        tokens += response.usage.total_tokens

    # A mismatch would only surface later as a database error on insert, or
    # worse, as meaningless search results -- so fail here, clearly.
    if vectors and len(vectors[0]) != settings.embedding_dimensions:
        raise RuntimeError(
            f"{settings.embedding_model} returned {len(vectors[0])}-dimensional vectors, "
            f"but EMBEDDING_DIMENSIONS is {settings.embedding_dimensions} "
            "(and must match vector(N) in sql/sop_documents.sql)."
        )
    return Embedded(vectors=vectors, tokens_used=tokens)


def embed_chunks(title: str, chunks: list[Chunk]) -> Embedded:
    """Embed document chunks, each prefixed with its document title.

    The prefix gives a chunk context it may lack on its own (a chunk saying
    "orders above EUR 5,000 need sign-off" gains "procurement-policy.pdf"), which
    helps it match questions. Only the embedding sees it; the stored chunk text
    stays as-is.
    """
    return embed_texts([f"{title}\n\n{c.text}" for c in chunks])


def embed_query(query: str) -> list[float]:
    """Embed a search query (used by the search tool later)."""
    return embed_texts([query]).vectors[0]
