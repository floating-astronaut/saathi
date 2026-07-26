"""PDFs and other documents an elder forwards.

Two paths, cheapest first:

1. **Text extraction.** Most documents older people receive — bank statements,
   utility bills, e-tickets, lab reports — are generated PDFs with a real text
   layer. Extracting it costs nothing and is exact.
2. **Render and look.** Scanned or photographed documents have no text layer, so
   page one is rasterised and handed to the vision model.

Bounded on purpose: only the first few pages are read. An elder asking "what
does this say" wants the gist and the deadline, not forty pages summarised — and
an unbounded document is an unbounded bill.
"""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile

log = logging.getLogger("saathi.documents")

MAX_PAGES = 3
#: Below this many extracted characters we assume there is no real text layer.
TEXT_LAYER_MIN = 200


def extract_text(pdf: bytes, max_pages: int = MAX_PAGES) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:      # pragma: no cover - dependency is declared
        return ""
    import io
    try:
        reader = PdfReader(io.BytesIO(pdf))
        parts = [(p.extract_text() or "") for p in reader.pages[:max_pages]]
        return "\n".join(parts).strip()
    except Exception:        # noqa: BLE001 - a malformed PDF must not 500 a reply
        log.exception("pdf text extraction failed")
        return ""


async def render_first_page(pdf: bytes) -> bytes | None:
    """Rasterise page 1 for the vision model. Requires poppler's pdftoppm."""
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf)
        path = f.name
    try:
        proc = await asyncio.create_subprocess_exec(
            "pdftoppm", "-png", "-r", "150", "-f", "1", "-l", "1", path, path,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await asyncio.wait_for(proc.communicate(), 30)
        for cand in (f"{path}-1.png", f"{path}-01.png", f"{path}-001.png"):
            if os.path.exists(cand):
                data = open(cand, "rb").read()
                os.unlink(cand)
                return data
        return None
    except (FileNotFoundError, asyncio.TimeoutError):
        log.warning("pdftoppm unavailable or slow; cannot read scanned PDF")
        return None
    finally:
        if os.path.exists(path):
            os.unlink(path)


def has_text_layer(text: str) -> bool:
    return len(text) >= TEXT_LAYER_MIN
