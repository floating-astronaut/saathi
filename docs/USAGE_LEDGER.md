# Usage ledger

Status: **designed, not built**. This is the Saathi-owned source of truth for
paid vendor usage across model, speech, document, messaging and search calls.

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
| Direct Bedrock agent loop | `saathi/agent/loop.py::record` and `llm_calls` | Insert a `vendor_usage_events` row next to the existing `llm_calls` row. Later make `llm_calls` a view or keep it as model-specific detail. |
| Bedrock streaming | `saathi/agent/stream.py` | Same usage fields arrive in stream metadata; record once at stream end. |
| Sarvam STT | `saathi/speech/stt.py::transcribe` | Measure audio duration/rounded seconds before call; record success/error after call. |
| Sarvam TTS | future TTS module | Record characters, model, speaker/voice id in metadata, and whether cache hit avoided a paid call. |
| Sarvam OCR | future document path | Record pages/job id; obey media gates before the paid call. |
| WhatsApp templates | `saathi/wa/client.py::_send` / `send_template` | Since `_send` is the single wire path and already records outbound messages, insert template usage there after `wa_message_id` is known. |
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
