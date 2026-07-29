"""Resource limits on inbound media (PR-26).

Four bugs in this repo have shipped with passing tests that agreed with the
bug, because the test was written from the implementation rather than from the
contract. A test that calls a limit function directly and watches it reject
10 MiB proves only that the function exists — not that anything calls it.

So every test here that claims a guard *works* drives
`pipeline.handle_message`, the same entry point a WhatsApp document webhook
reaches. The narrow unit tests below it are labelled as such and are there to
prove the mechanism, not the wiring.
"""
import asyncio
import contextlib
import hashlib
import hmac
import io
import json
import math
import os
import re
import resource
import signal
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from pypdf import PdfWriter

from saathi import documents, pipeline, vision
from saathi.channels import registry
from saathi.channels.base import MediaTooLarge
from saathi.config import settings
from saathi.core import backpressure
from saathi.wa import client as wa_client

MIB = 1024 * 1024


# --- fakes -------------------------------------------------------------------

class FakeCursor:
    def __init__(self, row=None): self._row = row
    async def fetchone(self): return self._row
    async def fetchall(self): return []
    rowcount = 1


class FakeConn:
    """Records SQL. It never parses it — see LANDMINES, "a fake connection will
    certify SQL that Postgres rejects"."""

    def __init__(self):
        self.sql = []
        self.calls = []

    async def execute(self, q, params=None):
        self.sql.append(" ".join(q.split())[:70])
        self.calls.append((" ".join(q.split()), params))
        low = q.lower()
        if "from user_channels c join users u" in low:
            return FakeCursor((5, 1, datetime.now(timezone.utc),
                               "Kamala", "Asia/Kolkata", "auto", "active"))
        if "select 1 from messages" in low:
            return FakeCursor(None)
        if "from conversations" in low:
            return FakeCursor((7,))
        if "select onboarding" in low:
            return FakeCursor(("done",))
        if "returning id" in low:
            return FakeCursor((99,))
        return FakeCursor(None)


def doc_msg(mid="w.doc", mime="application/pdf", caption=None):
    """The shape a forwarded PDF actually arrives in."""
    node = {"id": f"media-{mid}", "mime_type": mime}
    if caption:
        node["caption"] = caption
    return {"id": mid, "from": "919812345678", "type": "document", "document": node}


@pytest.fixture
def wire(monkeypatch):
    """Patch the transport, not the pipeline: the guards must sit in the path a
    real message takes, and the transport is the only thing a test may stub."""
    t = registry.get("whatsapp")
    state = SimpleNamespace(sent=[], asked=[], blob=b"", honour_limit=True, fetches=0)

    async def fake_send_text(conn, uid, handle, text):
        state.sent.append(text)
        return "wamid.out"

    async def fake_fetch(media_id, max_bytes):
        state.asked.append(max_bytes)
        state.fetches += 1
        if state.honour_limit and len(state.blob) > max_bytes:
            raise MediaTooLarge(media_id, len(state.blob), max_bytes)
        return state.blob

    async def fake_touch(conn, uid, at=None):
        return None

    monkeypatch.setattr(t, "send_text", fake_send_text)
    monkeypatch.setattr(t, "fetch_media", fake_fetch)
    monkeypatch.setattr(pipeline.window, "touch", fake_touch)
    return state


def make_pdf(pages: int = 1, width: int = 595, height: int = 842) -> bytes:
    w = PdfWriter()
    for _ in range(pages):
        w.add_blank_page(width=width, height=height)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


# --- the byte cap, driven through the inbound path ---------------------------

async def test_an_oversize_document_never_reaches_the_parser(wire, monkeypatch):
    """The whole of PR-26 in one test: a 9 MiB PDF from a valid sender must be
    refused, and pypdf must never see it."""
    async def boom(*a, **k):
        raise AssertionError("pypdf ran on a document that was over the limit")
    monkeypatch.setattr(documents, "extract_text", boom)
    wire.blob = b"%PDF-1.4\n" + b"x" * (9 * MIB)

    out = await pipeline.handle_message(FakeConn(), doc_msg())

    assert out["handled"] == "media_refused" and out["reason"] == "too_large"
    # The limit is declared by the caller and handed to the download, not
    # discovered afterwards.
    assert wire.asked == [settings.saathi_max_document_bytes]


async def test_a_transport_that_ignores_the_limit_cannot_fail_open(wire, monkeypatch):
    """A limit that trusts its downloader is not a limit. Here the transport
    hands back more than it was asked for; the turn must still refuse."""
    async def boom(*a, **k):
        raise AssertionError("pypdf ran on a document that was over the limit")
    monkeypatch.setattr(documents, "extract_text", boom)
    wire.honour_limit = False
    wire.blob = b"%PDF-1.4\n" + b"x" * (9 * MIB)

    out = await pipeline.handle_message(FakeConn(), doc_msg())
    assert out["handled"] == "media_refused" and out["reason"] == "too_large"


async def test_the_refusal_is_kind_and_says_what_would_work(wire):
    """She may have photographed her prescription by accident. A rejection is a
    message in her language that tells her what to do next, not a dropped turn."""
    wire.blob = b"%PDF-1.4\n" + b"x" * (9 * MIB)
    await pipeline.handle_message(FakeConn(), doc_msg())

    assert len(wire.sent) == 1
    said = wire.sent[0]
    assert "bahut badi" in said                      # Hindi half
    assert "too big" in said.lower()                 # English half
    assert "photo" in said.lower()                   # and a way forward
    assert "error" not in said.lower()


async def test_a_photo_sent_as_a_file_is_held_to_the_image_limit(wire, monkeypatch):
    """WhatsApp lets you send a picture "as a document". It is still a picture,
    and the vision model's own ceiling must be the one that applies — otherwise
    we download 8 MiB and then throw it away inside `vision._ask`."""
    captured = {}

    async def fake_read(image, mime=None, question=None):
        captured["bytes"] = len(image)
        return vision.Reading("a bill", None, "document")

    monkeypatch.setattr(vision, "read_document", fake_read)
    wire.blob = b"\xff\xd8" + b"x" * (4 * MIB)
    out = await pipeline.handle_message(
        FakeConn(), doc_msg("w.img", mime="image/jpeg"))

    assert wire.asked == [settings.saathi_max_image_bytes]
    assert out["handled"] == "media" and captured["bytes"] == len(wire.blob)


async def test_an_unreadable_document_still_gets_an_answer(wire, monkeypatch):
    """A .docx used to be handed to the vision model as if it were a photograph:
    one model call, spent to produce nothing, and then silence."""
    async def boom(*a, **k):
        raise AssertionError("a .docx was sent to the vision model")
    monkeypatch.setattr(vision, "describe_image", boom)
    monkeypatch.setattr(vision, "read_document", boom)
    wire.blob = b"PK\x03\x04 not a pdf"

    out = await pipeline.handle_message(FakeConn(), doc_msg(
        "w.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"))

    assert out["handled"] == "media_refused" and out["reason"] == "unsupported_type"
    assert "couldn't read that file" in wire.sent[0]


# --- the page limit, driven through the inbound path -------------------------

async def test_a_model_failure_still_ends_in_a_sentence(wire, monkeypatch):
    """`dispatch` logs a raising capability and moves on, so an exception here
    would end the turn in silence — indistinguishable, to her, from the product
    being broken."""
    async def throttled(*a, **k):
        raise RuntimeError("ThrottlingException")
    monkeypatch.setattr(vision, "describe_image", throttled)
    wire.blob = b"\xff\xd8 jpeg"

    out = await pipeline.handle_message(FakeConn(), doc_msg("w.jpg", mime="image/jpeg"))
    assert out["reason"] == "read_failed"
    assert wire.sent and "send it again" in wire.sent[0].lower()


async def test_a_pdf_declaring_too_many_pages_is_refused(wire, monkeypatch):
    """A real 250-page PDF through the real pypdf, from the webhook's entry
    point. Nothing may rasterise it either."""
    async def boom(*a, **k):
        raise AssertionError("rasterised a document we had already refused")
    monkeypatch.setattr(documents, "render_first_page", boom)
    wire.blob = make_pdf(pages=settings.saathi_pdf_max_pages + 50)

    out = await pipeline.handle_message(FakeConn(), doc_msg())

    assert out["handled"] == "media_refused" and out["reason"] == "too_many_pages"
    assert "bahut lamba" in wire.sent[0] and "very long" in wire.sent[0]


async def test_a_text_pass_that_runs_long_is_given_up_on(wire, monkeypatch):
    """pypdf is synchronous. Before PR-26 this ran on the event loop, so a
    content stream that took ten seconds to decode took ten seconds of
    everybody else's turns with it."""
    import time

    def slow(pdf, max_pages):
        time.sleep(0.5)
        return "x" * 400

    monkeypatch.setattr(documents, "_extract_blocking", slow)
    monkeypatch.setattr(settings, "saathi_pdf_parse_timeout_s", 0.05)
    wire.blob = make_pdf()

    out = await pipeline.handle_message(FakeConn(), doc_msg())
    assert out["handled"] == "media_refused" and out["reason"] == "parse_timeout"
    assert "couldn't read that file" in wire.sent[0]


async def test_no_message_is_recorded_with_a_kind_the_enum_lacks(wire, monkeypatch):
    """The wiring, not the mechanism: a document arriving at the webhook must
    not reach `messages` carrying its wire type."""
    monkeypatch.setattr(documents, "extract_text",
                        lambda pdf, max_pages=documents.MAX_PAGES: _ok_text())
    monkeypatch.setattr(pipeline, "_read_pdf_text", lambda text, question: _reading())
    wire.blob = make_pdf()
    conn = FakeConn()

    await pipeline.handle_message(conn, doc_msg())

    logged = [p[2] for q, p in conn.calls if "insert into messages" in q and p]
    assert logged, "the inbound document was never recorded"
    assert set(logged) <= pipeline.MSG_KINDS


async def test_a_normal_pdf_is_still_read(wire, monkeypatch):
    """The limits must not make the product refuse the thing it is for."""
    async def fake_read(text, question):
        return vision.Reading(f"read {len(text)} chars", None, "document")
    monkeypatch.setattr(pipeline, "_read_pdf_text", fake_read)
    monkeypatch.setattr(documents, "extract_text",
                        lambda pdf, max_pages=documents.MAX_PAGES: _ok_text())
    wire.blob = make_pdf(pages=2)

    out = await pipeline.handle_message(FakeConn(), doc_msg())
    assert out["handled"] == "media" and out["kind"] == "document"


async def _ok_text():
    return "Bijli ka bill. " * 40


# --- concurrency, driven through the inbound path ----------------------------

async def test_a_second_document_is_refused_while_one_is_being_parsed(wire, monkeypatch):
    """2 vCPU. The (N+1)th document is told to try again, not queued behind
    work that is already using the box."""
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow_extract(pdf, max_pages=documents.MAX_PAGES):
        entered.set()
        await release.wait()
        return "Bijli ka bill. " * 40

    async def fake_read(text, question):
        return vision.Reading("your electricity bill", None, "document")

    monkeypatch.setattr(documents, "extract_text", slow_extract)
    monkeypatch.setattr(pipeline, "_read_pdf_text", fake_read)
    wire.blob = make_pdf()

    first = asyncio.create_task(pipeline.handle_message(FakeConn(), doc_msg("w.d1")))
    await asyncio.wait_for(entered.wait(), 5)
    # `wait_for`, because without the gate the second document does not get
    # refused — it gets *admitted*, and then waits behind the first forever.
    second = await asyncio.wait_for(
        pipeline.handle_message(FakeConn(), doc_msg("w.d2")), 5)

    assert second["handled"] == "media_refused" and second["reason"] == "busy"
    assert "reading something else" in wire.sent[0]
    release.set()
    assert (await asyncio.wait_for(first, 5))["handled"] == "media"


async def test_media_downloads_are_bounded_process_wide(wire, monkeypatch):
    """The webhook detaches every message, so without this the number of
    multi-MiB blobs resident at once is the sender's choice."""
    monkeypatch.setattr(pipeline, "_MEDIA_GATE", backpressure.Gate("media", 1))
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow_fetch(media_id, max_bytes):
        wire.fetches += 1
        entered.set()
        await release.wait()
        return make_pdf()

    monkeypatch.setattr(registry.get("whatsapp"), "fetch_media", slow_fetch)
    monkeypatch.setattr(documents, "extract_text",
                        lambda pdf, max_pages=documents.MAX_PAGES: _ok_text())
    monkeypatch.setattr(pipeline, "_read_pdf_text",
                        lambda text, question: _reading())

    first = asyncio.create_task(pipeline.handle_message(FakeConn(), doc_msg("w.m1")))
    await asyncio.wait_for(entered.wait(), 5)
    second = await asyncio.wait_for(
        pipeline.handle_message(FakeConn(), doc_msg("w.m2")), 5)

    assert second["handled"] == "media_refused" and second["reason"] == "busy"
    # Refused before the download, not after it — that is the whole point.
    assert wire.fetches == 1
    release.set()
    await asyncio.wait_for(first, 5)


async def _reading():
    return vision.Reading("your electricity bill", None, "document")


# --- the download cap itself, against a real httpx stack ---------------------

def _mock_httpx(monkeypatch, handler):
    class _Client(httpx.AsyncClient):
        def __init__(self, **kw):
            super().__init__(transport=httpx.MockTransport(handler), **kw)
    monkeypatch.setattr(wa_client.httpx, "AsyncClient", _Client)


async def test_the_download_is_abandoned_rather_than_buffered(monkeypatch):
    """`fetch_media` streams and stops. The bytes past the limit are never
    transferred, which is what makes this a memory bound and not a report."""
    produced = []
    chunk = 256 * 1024

    async def body():
        for _ in range(80):                 # 20 MiB if anyone read it all
            produced.append(chunk)
            yield b"x" * chunk

    def handler(request):
        if request.url.path.endswith("/media-1"):
            return httpx.Response(200, json={"url": "https://cdn.example/blob"})
        return httpx.Response(200, content=body())

    _mock_httpx(monkeypatch, handler)
    with pytest.raises(MediaTooLarge):
        await wa_client.fetch_media("media-1", 2 * MIB)
    assert sum(produced) <= 2 * MIB + chunk


async def test_a_size_meta_declares_is_refused_before_any_bytes_move(monkeypatch):
    hits = []

    def handler(request):
        if request.url.path.endswith("/media-1"):
            return httpx.Response(200, json={"url": "https://cdn.example/blob",
                                             "file_size": 90 * MIB})
        hits.append(request.url)
        return httpx.Response(200, content=b"x")

    _mock_httpx(monkeypatch, handler)
    with pytest.raises(MediaTooLarge):
        await wa_client.fetch_media("media-1", 8 * MIB)
    assert hits == []


async def test_a_size_we_could_not_determine_is_not_treated_as_small(monkeypatch):
    """Meta omitting `file_size` must not disable the cap. Fail loudly, never
    fail open.

    The body is a chunked generator so that httpx sets **no `Content-Length`**
    either. With a `bytes` body this test passed even with the streaming cap
    deleted, because the header check caught it first — which made it a test of
    a guard it was not naming. Now nothing but the streamed count can catch it.
    """
    async def body():
        for _ in range(12):
            yield b"x" * (256 * 1024)

    def handler(request):
        if request.url.path.endswith("/media-1"):
            return httpx.Response(200, json={"url": "https://cdn.example/blob",
                                             "file_size": "unknown"})
        resp = httpx.Response(200, content=body())
        assert "content-length" not in resp.headers, "the header would mask the cap"
        return resp

    _mock_httpx(monkeypatch, handler)
    with pytest.raises(MediaTooLarge):
        await wa_client.fetch_media("media-1", 1 * MIB)


async def test_a_document_within_the_cap_downloads_normally(monkeypatch):
    def handler(request):
        if request.url.path.endswith("/media-1"):
            return httpx.Response(200, json={"url": "https://cdn.example/blob",
                                             "file_size": 12})
        return httpx.Response(200, content=b"hello world!")

    _mock_httpx(monkeypatch, handler)
    assert await wa_client.fetch_media("media-1", 1 * MIB) == b"hello world!"


@pytest.mark.parametrize("limit", [0, -1, None, "8388608"])
async def test_fetch_media_will_not_run_without_a_usable_limit(limit):
    """No default: a new call site must say what it can afford."""
    with pytest.raises(ValueError):
        await wa_client.fetch_media("media-1", limit)


# --- the renderer: proven by running it, not by reading the flags ------------

async def test_render_first_page_actually_produces_a_png(monkeypatch):
    """`ffmpeg -version` passed for hours while every voice note failed. The
    flags here (`-singlefile`, `-scale-to`) change the *output filename*, so
    this runs the real pdftoppm and looks at the bytes.

    Also checks the directory's mode while the child is alive: `pdftoppm`
    creates the PNG under our umask, so the rendered page — a prescription, a
    bank letter — was briefly world-readable in /tmp.
    """
    seen = {}
    real = asyncio.create_subprocess_exec

    async def spy(*a, **kw):
        seen["mode"] = stat.S_IMODE(os.stat(Path(a[-1]).parent).st_mode)
        return await real(*a, **kw)

    monkeypatch.setattr(documents.asyncio, "create_subprocess_exec", spy)
    png = await documents.render_first_page(make_pdf())
    assert png is not None and png[:4] == b"\x89PNG"
    assert seen["mode"] == 0o700, "the rendered page was readable by other users"


async def test_a_slow_renderer_is_killed_and_leaves_nothing_behind(monkeypatch):
    """`wait_for` cancels *our wait*, not the renderer. Before PR-26 an
    overrunning pdftoppm was simply abandoned, still running, on a 2-core box.

    So this looks at the child's exit status rather than at our exception: -9
    is us killing it, and it is the only evidence that distinguishes a kill
    from a shrug.
    """
    spawned, args = [], []
    real = asyncio.create_subprocess_exec

    async def spy(*a, **kw):
        proc = await real(*a, **kw)
        spawned.append(proc)
        args.append(a)
        return proc

    monkeypatch.setattr(documents.asyncio, "create_subprocess_exec", spy)
    monkeypatch.setattr(settings, "saathi_pdf_render_timeout_s", 0.001)

    with pytest.raises(documents.DocumentRejected) as exc:
        await documents.render_first_page(make_pdf())

    assert exc.value.reason == "render_timeout"
    assert spawned and spawned[0].returncode == -signal.SIGKILL
    # Reaped, not merely signalled — and checked by pid, not by `pgrep`, which
    # would also see a real `saathi-web` rendering somebody's PDF next door.
    with pytest.raises(ProcessLookupError):
        os.kill(spawned[0].pid, 0)
    # A killed renderer leaves a partial PNG and a copy of the sender's file.
    # Scoped to this render's own directory for the same reason.
    workdir = Path(args[0][-1]).parent
    assert workdir.name.startswith("saathi-pdf-") and not workdir.exists()


async def test_the_file_size_rlimit_actually_stops_the_renderer(monkeypatch):
    """End to end, through the real subprocess: with nothing allowed to be
    written, the kernel kills pdftoppm (SIGXFSZ) and we hear about it. This is
    what proves the rlimits are *reaching* the child, not merely defined."""
    monkeypatch.setattr(settings, "saathi_pdf_render_max_output_mb", 0)
    with pytest.raises(documents.DocumentRejected) as exc:
        await documents.render_first_page(make_pdf())
    assert exc.value.reason == "render_resource_limit"


async def test_the_rlimits_reach_the_child_process():
    """The renderer's caps are set by `preexec_fn`, which runs in the forked
    child and cannot be observed from here — so ask a child what it got.

    `_prepare_limits()` first, because that is the production sequence:
    `render_first_page` builds the values in the parent and `_render_limits`
    only reads them, so that the child allocates nothing between fork and exec.
    """
    documents._prepare_limits()
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c",
        "import resource;print(resource.getrlimit(resource.RLIMIT_CPU)[0],"
        "resource.getrlimit(resource.RLIMIT_AS)[0],"
        "resource.getrlimit(resource.RLIMIT_FSIZE)[0])",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        preexec_fn=documents._render_limits)
    out, _ = await proc.communicate()
    cpu, mem, fsize = (int(v) for v in out.split())
    assert cpu == math.ceil(settings.saathi_pdf_render_timeout_s)
    assert mem == settings.saathi_pdf_render_max_mem_mb * MIB
    assert fsize == settings.saathi_pdf_render_max_output_mb * MIB
    # And the box's own limits were not what we just measured.
    assert resource.getrlimit(resource.RLIMIT_AS)[0] != mem


# --- the actual entry point: a signed webhook through the real app -----------

async def test_a_signed_document_webhook_is_refused_end_to_end(monkeypatch):
    """The claim the CHANGELOG makes, as a test rather than as a scratch script.

    Everything above enters at `pipeline.handle_message`. This one enters where
    Meta does: an HMAC-signed POST to the FastAPI route, which acks immediately
    and does the work in a detached task. It therefore covers the signature
    check, `extract_messages`, the `create_task` hand-off, and the fact that a
    refusal survives all of it — none of which the pipeline-level tests touch.
    """
    from saathi import db
    from saathi.web import app as webapp

    monkeypatch.setattr(settings, "wa_app_secret", "test-secret")
    conn, sent = FakeConn(), []

    class FakePool:
        async def open(self): return None

        @contextlib.asynccontextmanager
        async def connection(self):
            yield conn

    async def fake_send_text(c, uid, handle, text):
        sent.append(text)
        return "wamid.out"

    async def fake_fetch(media_id, max_bytes):
        return b"%PDF-1.4\n" + b"x" * (max_bytes + 1)   # one byte over, whatever it is

    async def fake_touch(c, uid, at=None):
        return None

    monkeypatch.setattr(db, "pool", lambda: FakePool())
    monkeypatch.setattr(registry.get("whatsapp"), "send_text", fake_send_text)
    monkeypatch.setattr(registry.get("whatsapp"), "fetch_media", fake_fetch)
    monkeypatch.setattr(pipeline.window, "touch", fake_touch)

    payload = {"entry": [{"changes": [{"value": {
        "contacts": [{"wa_id": "919812345678", "profile": {"name": "Kamala"}}],
        "messages": [{"id": "wamid.doc1", "from": "919812345678", "type": "document",
                      "document": {"id": "media-9", "mime_type": "application/pdf",
                                   "caption": "beta ye padho"}}]}}]}]}
    body = json.dumps(payload).encode()
    sig = "sha256=" + hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()

    transport = httpx.ASGITransport(app=webapp.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        r = await c.post("/webhook/whatsapp", content=body,
                         headers={"X-Hub-Signature-256": sig,
                                  "Content-Type": "application/json"})
        assert r.status_code == 200 and r.json() == {"ok": True}

        # The ack comes back before the work is done — that is the point of the
        # detached task, and the reason this needs waiting for at all.
        for _ in range(200):
            if sent:
                break
            await asyncio.sleep(0.01)

        bad = await c.post("/webhook/whatsapp", content=body,
                           headers={"X-Hub-Signature-256": "sha256=deadbeef"})
        assert bad.status_code == 403

    assert sent, "a signed document webhook produced no reply at all"
    assert "too big" in sent[0].lower()
    # The enum coercion, on the real route: nothing may reach `messages` with a
    # kind Postgres would reject. This is what made documents unreachable.
    logged = [p[2] for q, p in conn.calls if "insert into messages" in q and p]
    assert logged and set(logged) <= pipeline.MSG_KINDS


# --- mechanism, not wiring ---------------------------------------------------

def test_a_gate_refuses_an_impossible_ceiling():
    """A gate built with 0 would refuse everything; one built from a bad value
    would fail open on the first comparison. Neither may reach runtime."""
    for bad in (0, -1, None, "2", True):
        with pytest.raises(ValueError):
            backpressure.Gate("x", bad)


def test_a_gate_releases_its_slot_when_the_body_raises():
    gate = backpressure.Gate("x", 1)
    with pytest.raises(RuntimeError):
        with gate.hold():
            raise RuntimeError("boom")
    assert gate.in_flight == 0
    with gate.hold():
        pass


def test_the_parse_pool_is_no_larger_than_the_document_gate():
    """A pool bigger than the gate would let timed-out extractions accumulate as
    CPU-bound threads — the exact thing the gate exists to prevent."""
    assert documents._parse_pool()._max_workers <= settings.saathi_doc_concurrency


def test_the_kinds_we_log_are_the_kinds_the_enum_has():
    """Postgres is the authority. Every inbound document used to abort its
    transaction here — `invalid input value for enum msg_kind: "document"` —
    before the media capability ever ran."""
    schema = (Path(__file__).resolve().parents[1] / "db" / "schema.sql").read_text()
    declared = re.search(r"create type msg_kind as enum \(([^)]*)\)", schema)
    assert declared, "msg_kind is not declared where this test expects it"
    values = {v.strip().strip("'") for v in declared.group(1).split(",")}
    assert pipeline.MSG_KINDS == values
    for wire_kind in ("text", "audio", "image", "document", "video", "sticker",
                      "location", "contacts", "interactive", "button", "unknown"):
        assert pipeline._msg_kind(wire_kind) in values
