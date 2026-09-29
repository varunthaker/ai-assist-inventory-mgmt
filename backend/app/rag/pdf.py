"""Step 2: extract text from a PDF, page by page.

Pages are kept separate (rather than one big string) so that later steps can
record which page each chunk came from, for citations like "policy.pdf p. 4".
"""

import io
import re
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PdfReadError


@dataclass(frozen=True)
class Page:
    number: int  # 1-based, as a person would cite it
    text: str


def _clean(text: str) -> str:
    """Normalise whitespace from PDF extraction without changing the words."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Trailing spaces on each line are layout noise.
    text = "\n".join(line.rstrip() for line in text.split("\n"))
    # Keep paragraph breaks (one blank line) but drop runs of empty lines.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pages(data: bytes) -> list[Page]:
    """Return the cleaned text of every page that has any.

    Raises ValueError with a user-facing message if the PDF cannot be read or
    contains no extractable text (e.g. a scan, which would need OCR).
    """
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            # Many "protected" PDFs only restrict editing and open with an
            # empty password; anything else we cannot read.
            if not reader.decrypt(""):
                raise ValueError("The PDF is password-protected.")
        raw_pages = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as exc:
        raise ValueError(f"The PDF could not be read: {exc}") from exc

    pages = [
        Page(number=i, text=cleaned)
        for i, raw in enumerate(raw_pages, start=1)
        if (cleaned := _clean(raw))
    ]
    if not pages:
        raise ValueError(
            "No text could be extracted. The PDF is probably scanned images, "
            "which would need OCR."
        )
    return pages
