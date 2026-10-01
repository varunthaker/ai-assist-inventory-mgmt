"""Document routes: upload, list and delete policy PDFs for RAG.

POST /documents runs the ingestion pipeline:
    1. upload      -- receive and validate the PDF
    2. pdf         -- extract text page by page             (app/rag/pdf.py)
    3. chunking    -- split text into overlapping chunks    (app/rag/chunking.py)
    4. embedding   -- turn each chunk into a vector         (app/rag/embeddings.py)
    5. save        -- store chunks + vectors in sop_documents (app/rag/store.py)
"""

from pathlib import PurePath

import openai
from fastapi import APIRouter, HTTPException, UploadFile, status

from app.config import settings
from app.rag.chunking import chunk_pages
from app.rag.embeddings import embed_chunks
from app.rag.pdf import extract_pages
from app.rag.store import delete_document, list_documents, save_document

router = APIRouter(tags=["documents"])

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


def _read_pdf_upload(file: UploadFile) -> tuple[str, bytes]:
    """Validate an uploaded file and return (title, raw bytes).

    The title is the bare file name; it identifies the document, so uploading
    a file with the same name later will replace it.
    """
    # Browsers may send a full path on some platforms; keep only the name.
    title = PurePath(file.filename or "").name
    if not title.lower().endswith(".pdf"):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            f"Only PDF files are supported, got '{title or 'no file name'}'.",
        )

    # Read one byte past the limit to detect oversized files without
    # buffering an arbitrarily large upload.
    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"'{title}' is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )
    # Every PDF starts with this signature; the extension alone proves nothing.
    if not data.startswith(b"%PDF-"):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"'{title}' is not a valid PDF file.",
        )
    return title, data


@router.post("/documents", status_code=status.HTTP_201_CREATED)
def upload_document(file: UploadFile) -> dict:
    """Upload a policy / SOP PDF: extract, chunk, embed and store it.

    Uploading a file with the same name replaces the stored version.
    """
    title, data = _read_pdf_upload(file)

    try:
        pages = extract_pages(data)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"'{title}': {exc}") from exc

    chunks = chunk_pages(pages)

    # Embed before touching the database, so an OpenAI failure leaves any
    # previously stored version intact.
    try:
        embedded = embed_chunks(title, chunks)
    except RuntimeError as exc:  # missing key or dimension mismatch
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except openai.OpenAIError as exc:  # bad key, no credit, rate limit, network
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            f"Embedding failed: {type(exc).__name__}: {exc}",
        ) from exc

    try:
        replaced = save_document(title, chunks, embedded.vectors)
    except RuntimeError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc

    return {
        "title": title,
        "pages": len(pages),
        "chunks": len(chunks),
        "replaced_chunks": replaced,
        "embedding_model": settings.embedding_model,
        "embedding_tokens": embedded.tokens_used,
    }


@router.get("/documents")
def get_documents() -> dict:
    """List stored documents with their chunk and page counts."""
    documents = list_documents()
    return {"count": len(documents), "documents": documents}


@router.delete("/documents/{title}")
def remove_document(title: str) -> dict:
    """Delete a stored document (all of its chunks) by its file name."""
    deleted = delete_document(title)
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No document named '{title}'.")
    return {"title": title, "deleted_chunks": deleted}
