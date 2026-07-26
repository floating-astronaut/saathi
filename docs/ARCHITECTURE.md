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
open; traffic arrives only through the tunnel.

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
definition; `reminder_fires` is the queue. Ack / snooze / nudge is then a state
machine on one table, and §15's acknowledgement-rate metric falls out for free.

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
