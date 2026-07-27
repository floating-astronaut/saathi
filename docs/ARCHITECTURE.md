# Architecture

```
WhatsApp ──webhook──▶ cloudflared ──▶ saathi-web (FastAPI, 127.0.0.1:3130)
                                          │
                                          ├─ signature check (HMAC, fails closed)
                                          ├─ dedupe on wa_message_id
                                          ├─ window touch (24h timer)
                                          ├─ SAFETY classifier ── deterministic, pre-LLM
                                          ├─ audio? ─▶ fetch media ─▶ ffmpeg ─▶ Saaras
                                          │            └─▶ entity correction (local)
                                          ├─ agent loop ─▶ zai.glm-5 (Bedrock ap-south-1)
                                          └─ Postgres 18
                                               ▲
                       saathi-worker ──────────┘  reminder scheduler,
                                                  poll 30s, SKIP LOCKED
```

Everything runs on `i-01b2c27883acb25ca` in **ap-south-1**. No inbound port is
open to the application — traffic arrives only through the tunnel. The box has
one inbound rule, TCP 22 from `207.219.25.137/32`, for operator SSH. See
`RUNBOOK.md`.

## The boundaries that matter

**Safety is a regex, not a prompt rule.** `safety/classifier.py` runs before the
model is constructed. A forwarded scam message is untrusted input that will try
to argue its way past an instruction; it cannot argue with a function that has
already returned. `tests/test_pipeline_order.py` fails if the agent is ever
reached on an emergency message.

**Capability is defined by absence.** PRD §12's guarantee — that prompt
injection cannot cause harm — lives in `agent/tools/specs.py`, in what is *not*
in the tool list. No tool can move money, read an OTP, or touch a third-party
account. `assert_no_forbidden_tools()` fails the suite if one is added.

**The 24-hour window is a hard gate, not a convention.** `wa/window.py` refuses
free-form sends outside the window. Every outbound path funnels through
`wa/client.py::_send`, which calls the guard first — so it is not possible to
send by forgetting to check.

**Memory serves ASR, not just personalisation.** `facts.surface_forms` is the
entity-bias vocabulary for the correction pass. This is why the product hears
someone better the longer they use it — a retention mechanic, not an accuracy
patch. Bias forms are extracted proper nouns; a whole sentence is worthless as a
bias hint.

**Recurrence and firing are separate tables.** `reminders` holds the RRULE
definition; **`scheduled_turns` is the queue** — one queue for every kind of
scheduled work, since migration 006. Firing a recurring reminder books its own
next occurrence, dedupe-keyed on (reminder, occurrence), because nothing else
walks the RRULE.

`reminder_fires` is the **old** queue and is no longer written or read. It
survives only as the table `pipeline.handle_ack` still updates, which is why the
ack path is currently unreachable — see lane PR-4b. Do not add writes to it.

**A claim is committed before the send.** `claim_due` marks a turn `sent` and
commits, so two workers can never double-send. The cost is that a crash between
claim and send strands the row: never retried, because claiming reads only
`pending`, and never failed, because nothing raised. `scheduling.sweep_stuck`
reclaims those, guarded on `wa_message_id is null` — set only after a send
returns an id, so a reclaimed turn provably never reached WhatsApp.

**Cost is linear in prompt size.** The chosen model has no prompt caching, so
there is no cache to hide a bloated prefix behind. `agent/prompt.py` raises
`PrefixTooLarge` rather than let it creep — the failure mode being guarded
against is silent, not loud.

## Layout

    saathi/web/       FastAPI — webhook (verify + signed receive), healthz
    saathi/wa/        Cloud API client, window guard, templates, text formatter
    saathi/speech/    ffmpeg transcode, Saaras STT, entity correction
    saathi/agent/     tool loop, streaming, prompt + prefix budget, tools
    saathi/safety/    deterministic pre-LLM classifier
    saathi/worker/    reminder scheduler, reminder sender
    saathi/memory.py  facts, bias vocabulary, erasure
    saathi/pipeline.py  the inbound path, start to finish
    db/               extensions.sql (superuser), schema.sql (owner)

## Why Postgres is also the queue

`SKIP LOCKED` holds well past 10k users, and it is the pattern already proven
across ~20 workers on the MeshPilot box. No Redis, no Temporal, no vector DB in
v1 — the fact set per user is tens of rows and fits in the prompt.

Two correctness notes that cost money to learn elsewhere: the row locks only
hold inside an explicit transaction, and claim-and-mark must be a single
statement so there is no window where a row is claimed but unmarked.

## Capabilities are registered, not branched

The inbound path used to be an `if/elif` ladder that grew a branch per feature.
That shape stops being reviewable at about six capabilities: every new one edits
the same function, ordering becomes implicit, and nobody can say what runs
before what without reading all of it. It is the failure mode that breaks
products of this kind at scale.

A capability is now an object with three things:

    priority  — lower runs first; ordering is data, not source order
    matches() — cheap, side-effect-free "is this mine?"
    handle()  — returns a result to claim the message, or None to fall through

`saathi/capabilities.py` read top to bottom *is* the specification of what
happens to an inbound message. Adding web search, weather, or a new document
type is a `register(...)` there — never an edit to `pipeline.handle_message`, and
a test asserts the dispatcher does not name any individual capability.

Priority bands keep the ordering legible as this grows:

| Band | For |
|---|---|
| 0–9 | safety and admission — must not be overtakeable |
| 10–19 | onboarding — a new user is not a general query |
| 20–29 | deterministic commands — unambiguous, model-free |
| 30–49 | media and modality |
| 50–89 | specific capabilities |
| 90–99 | the agent, as the catch-all |

Two properties are enforced by tests rather than convention: **safety is
priority 0** and cannot be overtaken (R7), and **a handler that raises is logged
and skipped** rather than killing the turn — one broken capability must not take
the assistant down for someone asking about their medicine.

## Seeing and reading

`vision.py` uses **`qwen.qwen3-vl-235b-a22b`**, chosen because it is a
*regional* ap-south-1 model: a photograph of someone's prescription must not
leave India, and the Anthropic vision models here are `global.`-only. GLM-5 has
no vision at all.

Health-adjacent answers carry their disclaimer **by construction** — the caller
cannot obtain the text without it, because `Reading.rendered()` attaches it.
PRD §12's line holds: naming what is printed on a pack is information; saying
whether or how much to take is advice, and we never cross it.

`documents.py` tries a PDF's text layer first (most bills, statements and
e-tickets have one, and extraction is exact and free), falling back to
rasterising page one for scans. Page count is bounded — an elder wants the gist
and the deadline, and an unbounded document is an unbounded bill.
