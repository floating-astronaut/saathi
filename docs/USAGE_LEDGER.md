# Usage ledger

Status: **vendor hooks live, STT enforcement gate built but disabled by default
(LEDGER-1/2, 2026-07-29)**. LLM, Sarvam STT and WhatsApp template successes now
write content-free usage events. Sarvam STT also has a pre-call reservation path
that can refuse before the vendor call, but it requires the explicit enforcement
flag, `SAATHI_USAGE_LEDGER_MODE=enforce`, and a positive operator-approved INR
paise cap.

The basic PR-15 availability guard is implemented separately in
`saathi.rate_limit`: it bounds inbound-turn frequency before a paid call but
does not know units or money. It is not a substitute for this ledger's
cross-vendor pre-call monetary caps.

Owns: cost attribution, per-user/vendor units, auditability, and the data needed
for PR-15 rate limits. Related: `AI_ROUTING.md` (OpenRouter/Bedrock routing),
`PROD_READINESS.md` PR-15 (rate limiting beyond admission), `DECISIONS.md` D-S.

---

## 1. Decision

Build a Saathi-owned append-only usage ledger. Do **not** make OpenRouter,
Langfuse, LiteLLM, Sarvam's dashboard, Meta's dashboard, or AWS billing the
source of truth for user-level spend.

Those systems can be inputs or dashboards. Saathi still records every paid
vendor call in its own database because only Saathi sees the full attribution:
which elder, household, message, language, feature, reminder, and safety path
caused the spend.

The ledger must cover, from day one of the implementation:

- Bedrock today and OpenRouter once AI-1 lands;
- Sarvam STT, future TTS, future OCR/document digitization, and any Sarvam LLM or
  language-tool calls;
- WhatsApp paid outbound templates;
- paid search later, if Vertex/Gemini search or another paid provider remains in
  the product.

Keyless/free lookups like Open-Meteo and Wikipedia do not need cost rows, though
they can be counted separately for product analytics if that ever matters.

---

## 2. Why not just OpenRouter, Langfuse or LiteLLM?

| System | Use it for | Do not use it as |
|---|---|---|
| OpenRouter | Hard per-account LLM caps and accurate LLM usage/cost returned with model responses. | The cross-vendor ledger. It does not know Sarvam seconds, TTS characters, OCR pages or WhatsApp templates. |
| Langfuse | Optional observability/dashboard sink. It can ingest arbitrary usage and cost details and filter metrics by user/tags. | The authoritative spending gate. If Langfuse is down, Saathi must still know what a user spent and whether to stop. |
| LiteLLM | A future self-hosted LLM gateway if Saathi outgrows OpenRouter or needs provider control OpenRouter cannot give. | The first ledger. It gates LLMs, not Sarvam credits or WhatsApp templates without custom proxy work and another production service. |
| Vendor dashboards | Reconciliation against invoices and credits. | Product attribution. They do not know which Saathi user or feature caused the call. |

Research notes:

- OpenRouter usage accounting returns token counts, cost credits, cache/reasoning
  detail, and BYOK upstream cost in responses or via generation id.
- Sarvam pricing is unit based: STT per rounded audio second, TTS per character,
  document digitization per page, language tools per character, LLMs per token.
- Sarvam rate limits are account-level, not per-user or per-key. Saathi must
  enforce household/user fairness before making Sarvam calls.
- Langfuse usage/cost details can be ingested directly with arbitrary usage
  buckets, which makes it a good mirror for dashboards once the local row exists.

Sources captured during design:

- OpenRouter usage accounting — https://openrouter.ai/docs/cookbook/administration/usage-accounting
- Sarvam pricing — https://docs.sarvam.ai/api/getting-started/pricing
- Sarvam credits and rate limits — https://docs.sarvam.ai/api/getting-started/ratelimits
- Langfuse token/cost tracking — https://langfuse.com/docs/observability/features/token-and-cost-tracking
- LiteLLM budgets and virtual keys — https://docs.litellm.ai/docs/proxy/users

---

## 3. Data model

Add a normalized append-only table. JSON is used only for vendor-specific unit
and cost fields; the join keys and grouping dimensions stay typed columns.

```sql
create type vendor_usage_status as enum (
  'success', 'error', 'skipped', 'rate_limited'
);

create table vendor_usage_events (
    id              bigserial primary key,
    created_at      timestamptz not null default now(),

    user_id         bigint references users(id) on delete set null,
    message_id      bigint references messages(id) on delete set null,
    conversation_id bigint references conversations(id) on delete set null,

    vendor          text not null,
    service         text not null,
    operation       text not null,
    model           text,

    request_id      text,
    status          vendor_usage_status not null,
    units           jsonb not null default '{}',
    cost            jsonb not null default '{}',
    metadata        jsonb not null default '{}',

    latency_ms      integer,
    error_code      text
);

create index vendor_usage_events_user_time
    on vendor_usage_events (user_id, created_at desc);

create index vendor_usage_events_vendor_time
    on vendor_usage_events (vendor, service, created_at desc);

create unique index vendor_usage_events_request_once
    on vendor_usage_events (vendor, request_id)
    where request_id is not null;
```

Do not store prompts, transcripts, document text, raw image/audio bytes, phone
numbers, API keys, URLs containing secrets, or full vendor responses in this
ledger. The row is an accounting record, not another copy of user content.

---

## 4. Canonical dimensions

`vendor` values:

| Vendor | Meaning |
|---|---|
| `bedrock` | Direct AWS Bedrock calls, while the current path remains. |
| `openrouter` | OpenRouter-routed model calls once AI-1 lands. |
| `sarvam` | Sarvam STT, TTS, OCR/document digitization, language tools, or LLMs. |
| `whatsapp` | WhatsApp Cloud API paid sends, especially templates. |
| `vertex` | Paid Google/Vertex search or model calls, if used later. |

`service` values:

| Service | Typical unit |
|---|---|
| `llm` | input/output/cache/reasoning tokens |
| `stt` | audio seconds, rounded audio seconds |
| `tts` | characters |
| `ocr` | pages |
| `language_tool` | characters |
| `template` | template messages |
| `search` | requests, tokens, or provider-specific units |

`operation` is narrower and should name the actual operation, for example
`chat_completion`, `speech_to_text`, `text_to_speech`, `document_digitization`,
`send_template`, `web_search`.

---

## 5. Unit and cost examples

OpenRouter / LLM:

```json
{
  "vendor": "openrouter",
  "service": "llm",
  "operation": "chat_completion",
  "model": "z-ai/glm-5",
  "units": {
    "input_tokens": 1200,
    "output_tokens": 180,
    "cached_tokens": 0,
    "reasoning_tokens": 0
  },
  "cost": {
    "currency": "USD",
    "credits": 0.0031,
    "upstream_inference_cost": 0.0028
  }
}
```

Direct Bedrock / LLM, before OpenRouter lands:

```json
{
  "vendor": "bedrock",
  "service": "llm",
  "operation": "converse",
  "model": "zai.glm-5",
  "units": {"input_tokens": 1200, "output_tokens": 180},
  "cost": {"currency": "INR", "estimated_paise": 0}
}
```

For direct Bedrock, populate token units from the Converse `usage` block. If the
exact INR cost is not calculated in code yet, store tokens and mark cost as
estimated/unknown rather than inventing precision.

Sarvam STT:

```json
{
  "vendor": "sarvam",
  "service": "stt",
  "operation": "speech_to_text",
  "model": "saaras:v3",
  "units": {"audio_seconds": 26.4, "rounded_seconds": 27},
  "cost": {"currency": "INR", "estimated_paise": 23}
}
```

Sarvam TTS:

```json
{
  "vendor": "sarvam",
  "service": "tts",
  "operation": "text_to_speech",
  "model": "bulbul:v2",
  "units": {"characters": 312},
  "cost": {"currency": "INR", "estimated_paise": 47}
}
```

Sarvam OCR/document digitization:

```json
{
  "vendor": "sarvam",
  "service": "ocr",
  "operation": "document_digitization",
  "model": "document-digitization",
  "units": {"pages": 2},
  "cost": {"currency": "INR", "estimated_paise": 100}
}
```

WhatsApp template:

```json
{
  "vendor": "whatsapp",
  "service": "template",
  "operation": "send_template",
  "model": "reminder_fire_v2",
  "request_id": "wamid...",
  "units": {"template_messages": 1},
  "cost": {"currency": "INR", "estimated_paise": null},
  "metadata": {"template_category": "utility", "language": "en"}
}
```

Meta's final bill depends on conversation category/country and policy changes;
record the send immediately, then reconcile later if invoice/export data becomes
available. Do not delay the ledger row waiting for billing finality.

---

## 6. Current Saathi integration points

| Paid surface | Current file | Ledger hook |
|---|---|---|
| Direct Bedrock agent loop | `saathi/agent/loop.py::record` and `llm_calls` | Implemented observe-only: insert a `vendor_usage_events` row next to the existing `llm_calls` row. Later make `llm_calls` a view or keep it as model-specific detail. |
| Bedrock streaming | `saathi/agent/stream.py` | Same usage fields arrive in stream metadata; record once at stream end. |
| Sarvam STT | `saathi/pipeline.py::transcribe_voice` | Implemented: measure WAV duration and rounded billed seconds before call, optionally reserve an INR hold before Sarvam, settle and record one success event after transcription. |
| Sarvam TTS | future TTS module | Record characters, model, speaker/voice id in metadata, and whether cache hit avoided a paid call. |
| Sarvam OCR | future document path | Record pages/job id; obey media gates before the paid call. |
| WhatsApp templates | `saathi/wa/client.py::send_template` | Implemented observe-only: record template usage after `wa_message_id` is known; free-form in-window replies are not usage events. |
| Paid search | future Vertex/search wrapper | Record only paid provider calls; Open-Meteo/Wikipedia stay out of cost ledger. |

The implementation should expose one small helper, for example
`saathi.usage.record_event(conn, ...)`, and every paid wrapper calls it. Avoid a
wide decorator that tries to infer meaning from arbitrary functions; the unit and
cost semantics are vendor-specific and should be explicit at the call site.

---

## 7. Charging and gating order

Before a paid call:

1. classify the intended vendor/service/operation;
2. estimate the maximum likely units if possible;
3. check account/user limits using ledger aggregates and configured caps;
4. refuse or degrade before sending bytes/text to the vendor if the cap is hit.

After a paid call:

1. record actual units and vendor request id;
2. record estimated or vendor-reported cost;
3. mirror to Langfuse if configured;
4. let invoice reconciliation correct estimates later, without changing the fact
   that the user caused the usage.

For vendors like Sarvam with account-level rate limits and shared credits, the
pre-call gate is non-negotiable. A Sarvam dashboard can say the account is empty;
it cannot say which elder burned it.

---

## 8. Langfuse mirror

Langfuse is useful after the local row exists:

- send LLM generations with usage/cost details;
- send Sarvam STT/TTS/OCR as observations with explicit `usage_details` and
  `cost_details` buckets;
- tag observations with `user_id`, locale, service, and feature;
- use Langfuse dashboards for debugging and product analysis.

Langfuse is not in the critical path for refusing a request. If Langfuse is down,
Saathi records locally and continues. A background worker can retry exports.

---

## 9. Reconciliation

The ledger has two cost classes:

- **actual**: vendor reported the charge in the response, e.g. OpenRouter credits;
- **estimated**: Saathi calculated from published unit pricing, e.g. Sarvam STT
  seconds or WhatsApp template estimates.

Add invoice reconciliation later as a separate lane if needed. It should append
or annotate reconciliation records rather than rewriting the original usage
causality row.

---

## 10. Tests required when built

- every paid call-site writes exactly one success row on success;
- failed paid calls write either one `error` row or no row by explicit policy,
  but never a success row;
- retries with the same vendor request id do not double-count;
- STT rounds audio seconds the same way Sarvam bills;
- TTS counts Unicode characters using the same contract Sarvam prices on;
- WhatsApp template sends record only templates, not free-form in-window text;
- cap checks refuse before Sarvam/LLM calls when a user is over budget;
- erasure keeps accounting rows but removes message/user content links according
  to the privacy policy and DPDP requirements.

---

## 11. Build plan — direct Bedrock-ready ledger (researched 2026-07-29)

### Goal and non-goals

The ledger is the authoritative *admission* control for paid work. It must let
Saathi route an account directly to Bedrock with a server-held AWS role, without
ever issuing an AWS key to an elder and without relying on OpenRouter's key
budget as the safety boundary. It is not an invoice engine, an analytics
warehouse, or a new proxy service in its first release.

Build it in PostgreSQL beside the existing application state. Do not install
LiteLLM, Bifrost, OpenMeter, ClickHouse, Kafka, or a second database in this
lane. Those may become routing/analytics choices later, but adding a control
plane before Saathi owns correct attribution would enlarge the failure surface.

### Data model v1

Keep `vendor_usage_events` append-only, but add a second table for atomic
pre-call accounting:

```sql
create type usage_reservation_state as enum
  ('held', 'settled', 'released', 'expired');

create table vendor_usage_reservations (
  id bigserial primary key,
  idempotency_key text not null unique,
  user_id bigint references users(id) on delete set null,
  account_id bigint references accounts(id) on delete set null,
  vendor text not null, service text not null, operation text not null,
  currency text not null default 'USD',
  reserved_minor bigint not null check (reserved_minor >= 0),
  state usage_reservation_state not null default 'held',
  expires_at timestamptz not null,
  created_at timestamptz not null default now(), settled_at timestamptz
);
create index vendor_usage_reservations_active
  on vendor_usage_reservations (account_id, created_at)
  where state = 'held';
```

Store money as integer minor units per currency, never floats. A row must also
carry `cost_source` (`vendor_reported`, `catalog_estimate`, `unknown`) and link
to its reservation. Pricing catalog entries are versioned (`vendor`, `service`,
`model`, `effective_at`) so old events stay explainable when a price changes.
No prompt, transcript, phone number, raw URL, API key, or full response enters
either table.

### The atomic state machine

1. Build an idempotency key from the immutable work identity: inbound WhatsApp
   message id plus operation for inbound work; scheduled-turn id plus operation
   for templates. Never use user id plus time.
2. In one transaction, take a transaction-scoped advisory lock for the account,
   expire abandoned holds, sum `settled` actuals plus unexpired `held` amounts
   inside the configured account and global windows, and insert a `held` row
   only when both caps permit it.
3. Commit the reservation **before** calling the vendor. If the database is
   unavailable, refuse paid work; never fail open because an empty ledger is not
   evidence of zero spend.
4. Call the vendor. On success, append one usage event with actual units/cost
   and settle the reservation to actual cost. On a known pre-send failure,
   append an error event and release it. On an ambiguous timeout, keep the hold
   until reconciliation/expiry: retry with the same idempotency key rather than
   risk a double call.
5. A worker sweeps expired holds and alerts on holds beyond the vendor-specific
   timeout. It never silently deletes them.

The reservation estimate must be conservative: Bedrock reserves estimated input
tokens plus requested output maximum; Sarvam STT reserves rounded source audio
seconds before upload; a template reserves one utility send. Actual usage can
refund unused reservation amount but may never make a completed call disappear.

### Enforcement hierarchy

Enforce all of these at reservation time:

1. per-account daily/monthly money cap;
2. per-account per-service unit cap (STT seconds, LLM tokens, templates);
3. global daily vendor cap and global rolling safety reserve;
4. Bedrock model/region request and token rate budget, separate from money.

The existing inbound rate limiter remains earlier in the pipeline. It protects
availability; this ledger protects money. Safety, onboarding, erasure and a
fixed rate-limit message must retain deterministic non-vendor paths when the
cap is exhausted. Reminders already scheduled must use their own template
reservation rather than silently disappearing.

### Exact integration sequence

**Slice A — foundation — complete 2026-07-29.** Migration 015 provides
content-free append-only event and reservation tables; `saathi.usage` provides
idempotent account-locked holds, settlement/release, expiry and event inserts;
the existing worker sweeps expired holds without deleting their audit rows; and
`SAATHI_USAGE_LEDGER_MODE=observe` is the default. Focused fake-connection
tests prove lock ordering, idempotency, cap refusal and state transitions. No
paid path is wired yet, so the planned seven-day comparison starts only after
Slice B/C introduce events.

**Slice B — LLM — implemented 2026-07-29.** The common agent boundary records
one successful content-free event after every Bedrock or OpenRouter request,
including actual reported input/output tokens, per-request latency, provider
request id and OpenRouter's reported cost when present. An accounting write
failure is logged but cannot turn a successful model reply into an outage while
mode remains observe-only. Streaming, pricing catalog/shadow price and the
seven-day comparison remain follow-up work; OpenRouter routing is unchanged.

**Slice C — speech and templates — implemented observe-only 2026-07-29.** A
successful Sarvam STT call records exact WAV seconds and rounded billable seconds
after transcription; a successful WhatsApp template records only after Meta
returns its message id. A post-success ledger failure cannot cause either call
to retry. Free-form WhatsApp replies are never template events.

**Slice D1 — staged STT enforcement — implemented disabled-by-default
2026-07-29.** Sarvam STT now computes the catalog INR paise estimate from the WAV
before transcription. If and only if `SAATHI_USAGE_ENFORCEMENT_ENABLED=true`,
`SAATHI_USAGE_LEDGER_MODE=enforce`, and `SAATHI_USAGE_ACCOUNT_CAP_PAISE` is
positive, it creates an account-locked INR reservation before Sarvam receives
bytes. Cap exhaustion or missing accounting returns a fixed voice-limit refusal
and never reaches STT. Successful enforced calls settle the hold and link the
usage event to the reservation. The reservation aggregate is currency-scoped, so
USD LLM events cannot consume an INR STT cap.

**Slice D2 — remaining enforcement.** Add LLM/template pre-call reservations,
global vendor caps, and the alert path. Turn on account caps first for internal
accounts, then a small cohort, then all users. Each phase needs a deliberate
rollback flag that switches to observe-only but never deletes reservations/events.
Add global cap last, after its alert path is proven.

**Slice E — direct Bedrock migration.** Route a small allow-listed cohort through
the server's ap-south-1 Bedrock role. Compare actual tokens, latency, throttles,
and ledger settlement for at least seven days. Only then make Bedrock the
default; retain OpenRouter as an explicit fallback behind the same reservation
API, with fallback disabled by default for residency/cost predictability.

### Provider facts that shape the design

Bedrock's `Converse` and `ConverseStream` return token usage, but runtime quotas
are model/region specific and account-level. AWS deducts input plus requested
maximum output at request start, then adjusts while generation runs; Saathi must
therefore reserve before the call, cap requested output, and handle 429 with
bounded retry/jitter—not treat a vendor throttle as an account budget decision.
See [Converse usage](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html),
[runtime quotas](https://docs.aws.amazon.com/bedrock/latest/userguide/quotas-runtime.html),
and [token burndown](https://docs.aws.amazon.com/bedrock/latest/userguide/quotas-token-burndown.html).

OpenMeter, LiteLLM and Bifrost validate that metering/budgets/gateway governance
are established patterns, but each is either broader infrastructure or LLM-only.
Saathi still needs one ledger that sees Sarvam and WhatsApp. Revisit Bifrost only
after Slice D if direct Bedrock needs multi-provider routing; it can become an
LLM caller under Saathi's reservation contract, never replace it.

### Release gates

- a forced over-cap test proves no bytes reach Bedrock/Sarvam/WhatsApp;
- concurrent reservations for one account cannot exceed any cap;
- a timeout/retry produces at most one vendor call or one retained ambiguous
  hold, never two settled charges;
- direct Bedrock and OpenRouter events reconcile to `llm_calls` token totals;
- a synthetic STT and template event is cleaned up after live verification;
- a missing price/cost source refuses enforcement for that operation and alerts,
  rather than treating unknown cost as zero;
- rollback to observe-only preserves all prior events and holds.
