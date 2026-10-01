"""Step 3: split a document's pages into overlapping chunks.

Each chunk becomes one vector (step 4) and one search result, so its size is a
trade-off: too small loses context ("this requires approval" -- what does?),
too large blends several topics into one fuzzy meaning.

Pages are joined into one text before splitting so a paragraph that continues
onto the next page stays together; each chunk records the pages it spans.
"""

from bisect import bisect_right
from dataclasses import dataclass

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.rag.pdf import Page

# Sizes are in tokens, the unit embedding models read and limit on
# (~4 characters of English per token).
CHUNK_TOKENS = 500
# Neighbouring chunks share this much text, so a rule that straddles a
# boundary still appears whole in at least one chunk.
OVERLAP_TOKENS = 75

# The tokenizer used by OpenAI's text-embedding-3 models.
_ENCODING = "cl100k_base"
_encoder = tiktoken.get_encoding(_ENCODING)

_PAGE_SEPARATOR = "\n\n"  # pages join like paragraphs

# Tries each separator in turn: split at blank lines (paragraphs) first, and
# only fall back to lines, sentences, then words when a piece is still too big.
_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    encoding_name=_ENCODING,
    chunk_size=CHUNK_TOKENS,
    chunk_overlap=OVERLAP_TOKENS,
    separators=["\n\n", "\n", ". ", " ", ""],
)


@dataclass(frozen=True)
class Chunk:
    index: int  # 0-based position in the document
    text: str
    page_start: int
    page_end: int
    tokens: int


def chunk_pages(pages: list[Page]) -> list[Chunk]:
    """Split pages into chunks of about CHUNK_TOKENS, with page ranges."""
    # Join the pages, remembering the character offset where each one starts.
    page_offsets: list[int] = []
    parts: list[str] = []
    offset = 0
    for page in pages:
        page_offsets.append(offset)
        parts.append(page.text)
        offset += len(page.text) + len(_PAGE_SEPARATOR)
    full_text = _PAGE_SEPARATOR.join(parts)

    def page_at(char_offset: int) -> int:
        # The last page whose start offset is <= char_offset.
        return pages[bisect_right(page_offsets, char_offset) - 1].number

    chunks: list[Chunk] = []
    start = -1
    for i, text in enumerate(_splitter.split_text(full_text)):
        # Chunks are verbatim, in order, and each starts after the previous
        # one's start, so search forward from there. (LangChain's own
        # add_start_index is wrong here: it rewinds by chunk_overlap as if it
        # were characters, but ours is in tokens, so the search overshoots.)
        start = full_text.find(text, start + 1)
        if start == -1:
            raise RuntimeError(f"Chunk {i} not found in the document text.")
        end = start + len(text) - 1
        chunks.append(
            Chunk(
                index=i,
                text=text,
                page_start=page_at(start),
                page_end=page_at(end),
                tokens=len(_encoder.encode(text)),
            )
        )
    return chunks
