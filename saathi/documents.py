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

**Every bound here is against a hostile file, not merely a large one** (PR-26).
Onboarding is open, so anyone may send a document, and a PDF is a program: the
page tree, the content streams and the embedded images are all sender-chosen and
none of them are proportional to the file's size. So:

* the declared page count is refused before anything walks the page tree;
* the text pass runs in a **bounded thread pool**, not on the event loop, with a
  wall clock — pypdf is synchronous, and a content stream that takes ten seconds
  to decode would otherwise take ten seconds of *everyone else's* turns with it;
* extracted text is capped per page and in total, because how much text a page
  yields is also the sender's choice;
* `pdftoppm` is the only part that forks and writes to disk, so it gets CPU,
  address-space and file-size rlimits from the kernel as well as a timeout —
  and it is **killed** when that timeout fires, which the original code did not
  do: `wait_for` cancelled our wait and left the renderer running.

The pool is deliberately the same size as the document gate in `pipeline`. A
timed-out extraction cannot be cancelled — a Python thread inside pypdf will
finish whatever it started — so a runaway occupies a pool slot until it ends.
Sizing the pool to the gate is what stops those accumulating: the next document
waits for a free thread and hits its own wall clock, rather than adding a second
CPU-bound thread to a two-core box.
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import resource
import tempfile
from concurrent.futures import ThreadPoolExecutor

from .config import settings

log = logging.getLogger("saathi.documents")

MAX_PAGES = 3
#: Below this many extracted characters we assume there is no real text layer.
TEXT_LAYER_MIN = 200

#: Caps on what one page, and one document, may yield. `_read_pdf_text` only
#: ever prompts with the first 6,000 characters, so these refuse nothing real.
MAX_CHARS_PER_PAGE = 20_000
MAX_CHARS_TOTAL = 60_000


class DocumentRejected(Exception):
    """This document was refused by a resource limit, not by a parse failure.

    Kept distinct from "there is no text layer" — which returns "" and falls
    through to rasterisation — because the two want opposite responses: one
    should try harder, the other must stop and tell the user why.
    """

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(f"{reason}{': ' + detail if detail else ''}")
        self.reason = reason


_pool: ThreadPoolExecutor | None = None


def _parse_pool() -> ThreadPoolExecutor:
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=max(1, settings.saathi_doc_concurrency),
                                   thread_name_prefix="saathi-pdf")
    return _pool


def _extract_blocking(pdf: bytes, max_pages: int) -> str:
    """The synchronous pypdf pass. Runs in `_parse_pool`, never on the loop."""
    try:
        from pypdf import PdfReader
    except ImportError:      # pragma: no cover - dependency is declared
        return ""
    import io
    try:
        reader = PdfReader(io.BytesIO(pdf))
        pages = len(reader.pages)
    except Exception:        # noqa: BLE001 - a malformed PDF must not 500 a reply
        log.exception("pdf text extraction failed")
        return ""

    if pages > settings.saathi_pdf_max_pages:
        # Refused before any page is touched. We read three; a document
        # declaring hundreds is not one anybody wants read aloud.
        raise DocumentRejected("too_many_pages", f"{pages} pages")

    parts: list[str] = []
    total = 0
    for page in reader.pages[:max_pages]:
        try:
            text = (page.extract_text() or "")[:MAX_CHARS_PER_PAGE]
        except Exception:    # noqa: BLE001 - one bad page is not a bad document
            log.exception("pdf page extraction failed")
            text = ""
        parts.append(text)
        total += len(text)
        if total >= MAX_CHARS_TOTAL:
            log.warning("pdf text truncated at %s characters", total)
            break
    return "\n".join(parts).strip()[:MAX_CHARS_TOTAL]


async def extract_text(pdf: bytes, max_pages: int = MAX_PAGES) -> str:
    """Text layer, or "" if there isn't one. Raises `DocumentRejected` on a limit.

    Async because the work is not: it is handed to a bounded thread pool so the
    event loop — which is also running the safety classifier and everybody
    else's turn — stays free.
    """
    loop = asyncio.get_running_loop()
    fut = loop.run_in_executor(_parse_pool(), _extract_blocking, pdf, max_pages)
    try:
        return await asyncio.wait_for(fut, settings.saathi_pdf_parse_timeout_s)
    except asyncio.TimeoutError:
        # The thread may still be running; see the module docstring. What we
        # have taken back is the event loop, and the slot stays occupied so the
        # next document does not add a second runaway alongside it.
        log.warning("pdf text extraction exceeded %ss", settings.saathi_pdf_parse_timeout_s)
        raise DocumentRejected("parse_timeout") from None


def _render_limits() -> None:
    """Applied in the forked child, before exec. Syscalls only, on purpose.

    `preexec_fn` runs between fork and exec in a process that has threads (the
    parse pool), where anything taking a lock can deadlock. `resource` is
    imported at module scope for exactly that reason, and nothing in here
    allocates, imports or logs.
    """
    cpu = int(math.ceil(settings.saathi_pdf_render_timeout_s))
    mem = settings.saathi_pdf_render_max_mem_mb * 1024 * 1024
    out = settings.saathi_pdf_render_max_output_mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
    resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
    resource.setrlimit(resource.RLIMIT_FSIZE, (out, out))


def _kill(proc) -> None:
    try:
        proc.kill()
    except ProcessLookupError:      # pragma: no cover - it exited as we asked
        pass


async def render_first_page(pdf: bytes) -> bytes | None:
    """Rasterise page 1 for the vision model. Requires poppler's pdftoppm.

    Returns None when the page simply could not be rendered, and raises
    `DocumentRejected` when a limit stopped us — the caller says different
    things for those two.
    """
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf)
        path = f.name
    png = f"{path}.png"          # -singlefile: no page-number suffix to guess
    try:
        try:
            proc = await asyncio.create_subprocess_exec(
                "pdftoppm", "-png", "-singlefile", "-f", "1", "-l", "1",
                # Bound the raster by output pixels, not by DPI: the page's
                # declared size is the sender's choice, so "-r 150" on a
                # 200-inch page is not a bound at all.
                "-scale-to", str(settings.saathi_pdf_render_max_px), path, path,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                preexec_fn=_render_limits)          # noqa: PLW1509 - syscalls only
        except FileNotFoundError:
            log.warning("pdftoppm unavailable; cannot read scanned PDF")
            return None
        try:
            _, err = await asyncio.wait_for(proc.communicate(),
                                            settings.saathi_pdf_render_timeout_s)
        except asyncio.TimeoutError:
            # The original code did not do this: `wait_for` cancels our wait,
            # not the renderer. Without the kill, a slow PDF left pdftoppm
            # running unattended on a two-core box.
            log.warning("pdftoppm exceeded %ss; killing",
                        settings.saathi_pdf_render_timeout_s)
            _kill(proc)
            await proc.wait()
            raise DocumentRejected("render_timeout") from None
        if proc.returncode != 0:
            # An rlimit arrives here as a negative return code (SIGKILL from
            # RLIMIT_AS's allocation failure, SIGXCPU, SIGXFSZ) — the kernel
            # telling us the file was hostile rather than merely broken.
            log.warning("pdftoppm exited %s: %s", proc.returncode, err[:200])
            if proc.returncode < 0:
                raise DocumentRejected("render_resource_limit", f"signal {-proc.returncode}")
            return None
        if os.path.exists(png):
            with open(png, "rb") as fh:
                return fh.read()
        return None
    finally:
        # Both, always: a killed renderer leaves a partial PNG behind, and the
        # temp PDF is a copy of the sender's file sitting on our disk.
        for leftover in (png, path):
            try:
                os.unlink(leftover)
            except FileNotFoundError:
                pass


def has_text_layer(text: str) -> bool:
    return len(text) >= TEXT_LAYER_MIN
