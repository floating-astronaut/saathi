# AI routing and per-account keys

How a Saathi turn reaches a model, who pays for it, and where the data goes.

Status: **closed 2026-07-27; mint, revoke, backfill, and spend-through proven live.**
The document came before the code (`THE_METHOD.md` §1) and the code now follows
it; §9 lists what has and has not been demonstrated. User turns now resolve the
account key and call OpenRouter when one exists. Live verification on 2026-07-27
resolved account 3's encrypted key and completed a real OpenRouter turn with
token usage returned.

Owns: model routing, per-account key provisioning, spend caps, residency.
Related: `DECISIONS.md` D-D (model choice), D-O (this routing change),
D-S (paid-vendor usage ownership), `USAGE_LEDGER.md` (cross-vendor ledger),
`vendor/` (captured OpenRouter API docs), `PROD_READINESS.md` PR-15 (rate limiting).

---

## 1. Today

Before AI-1, every model call was `boto3` → Bedrock `zai.glm-5` in **ap-south-1**,
using the box's instance role. One credential, no attribution, no per-user cap.

As of 2026-07-27, ordinary chat turns resolve the user's account key and call
OpenRouter Chat Completions when an active key exists. The Bedrock direct path
remains only for code paths that still have no account key in hand, such as the
first moments before the provisioning worker catches up and document text
extraction that has not yet been account-plumbed.

## 2. What changes, and what deliberately does not

OpenRouter becomes the **router and meter**. It is not a new inference location.

    turn ─▶ Saathi ─▶ OpenRouter ─▶ BYOK "Indian Box" ─▶ Bedrock ap-south-1 ─▶ zai.glm-5
                          │
                          └─ (fallback to OpenRouter's own providers) ── DISABLED

**The model does not change.** `z-ai/glm-5` on OpenRouter is the same model as
`zai.glm-5` on Bedrock. D-D chose it on a measured Hinglish entity-accuracy
bakeoff — 8/8 on times and medicine names where the ₹16 option scored 3/8, and
the failure mode that separated them was Hindi fractional time words (`sawa`,
`saade`, `paune`), where being wrong means a missed cardiac dose. **That
measurement still holds because the model is the same.** Re-run it if the slug
ever changes.

**The region does not change.** The BYOK credential (`amazon-bedrock`, named
"Indian Box", `sort_order: 0`, `is_fallback: false`) points at the same Mumbai
`ap-south-1` account Saathi already uses. Inference stays in India, which was
half of D-D's reasoning.

## 3. Residency — stated precisely

D-D's claim was *"inference stays in India."* After this change that remains
true, and a second, narrower claim becomes necessary:

> Inference runs in Mumbai. **The prompt transits OpenRouter's infrastructure**
> to get there.

Both must be said — and **the privacy policy already says exactly this**,
checked 2026-07-27:

> models are served by Amazon across multiple regions rather than only India, and
> where that applies your message text may be processed outside India during the
> reply. Your stored data — messages, transcripts, reminders and remembered facts
> — stays in India.

Stored data in India; message text may transit. That is the accurate pair, it was
written before OpenRouter was considered, and it covers this change without
amendment. **Settled — not an open question.** See D-O.

### The setting that makes it enforceable

Every request **must** carry:

```json
"provider": { "allow_fallbacks": false }
```

Per the OpenAPI spec: *"false: use only the primary/custom provider, and return
the upstream error if it's unavailable."*

Without it, a Bedrock hiccup silently reroutes an elder's medication
conversation to a US provider, and nothing in any log says so. With it, the
request **fails**, Saathi surfaces an error, and residency is a property of the
system rather than of the weather.

This is a **constant in the client, not a configuration option** — the same
reasoning that makes the safety classifier a regex rather than a prompt
instruction (D-F). A deterministic guarantee must not depend on someone
remembering to set a flag.

Also set, for the same reason: `allowed_models: ["z-ai/glm-5"]` on the BYOK
credential, so a minted key structurally cannot spend on a model nobody chose.
Capability defined by absence, as everywhere else in this product.

## 4. Why per-account keys at all

One master **provisioning key** mints a capped sub-key per paying account. Spend
becomes attributable and hard-capped: a runaway loop burns one household's cap,
not the platform balance. That is PR-15's fix, and it is why this is worth the
extra moving part.

### The tenant is the account, never the handle

Saathi's identity model already separates these: a phone number is a **revocable
handle**, not the account. India recycles numbers after ~90 days, which is why
dormant handles re-verify at 60. A key per WhatsApp handle would mean thousands
of upstream key objects, a rate-limited mint on a path an elder is waiting on,
and a key stranded every time a number changes hands.

**One key per account/household**, free ones included — see D-T. A free account
gets its own key with a one-time $5 on it, which is what makes the spend
attributable from the first turn rather than only after someone pays.

### Tier → cap

Unknown tier falls back to the **lowest** cap, never the highest, and to **no
reset**, never a renewing one. Fail safe, not open — the same shape as
`tier_cap()` in the MeshPilot implementation this is modelled on. A typo must
produce spend that stops, not spend that renews.

## 5. Provisioning, in order

1. **Idempotency first.** Select an active key for the account; if one exists,
   return it and mint nothing. Calling twice must not create two keys or two
   charges.
2. **Refuse if unconfigured.** No master key, or no Fernet key → raise
   `ProvisioningDisabled`. Never mint and hope; never store a plaintext because
   encryption happened to be unavailable.
3. Mint with the tier cap and `workspace_id` = Indofolk AI. `limit_reset` is
   **omitted for a one-time grant** and set to `monthly` only for tiers meant to
   renew — omitting it makes the cap a lifetime total. See D-T; this is the
   difference between "$5 free" and "$5 a month forever".
4. On upstream failure: write the audit row with the error text, **then**
   re-raise. "Did this account ever get a key, and why not" must be answerable
   months later.
5. Encrypt the plaintext immediately. It never outlives the function, never
   reaches a log line, not even a prefix.
6. Insert the key row, then the audit row with the success.

The log line carries account, tier and cap. No key material.

### Response-shape quirk, carried over

`POST /keys` returns **either** `{key, data:{hash,…}}` **or** flat
`{key, hash, …}`. Tolerate both, and if the hash is still missing, re-read
`GET /keys` and match on `name`. **Without the hash the key can never be rotated
or revoked** — this fallback is not paranoia.

## 6. Naming, and the guard that matters

    saathi:account:<account_id>:plan:<tier>:env:<env>[:ws:<workspace-prefix>]

Self-describing, because that string is the only join back to a tenant when you
are staring at the OpenRouter dashboard during an incident. The workspace suffix
is included when configured, because revoked names remain unique in Saathi's DB
and a workspace correction must be able to remint.

**This org also holds MeshPilot's keys.** `DELETE /keys/{hash}` works on all of
them. So every list, revoke and sync operation **asserts** the `saathi:` prefix
and refuses to act on a key without it. Not a convention — an assertion, in the
code, like `assert_no_forbidden_tools()`. A shared account means the guard
cannot live in the discipline of whoever runs it next.

## 7. Where it runs

Minting happens on the `scheduled_turns` queue as kind `provision_key`. **Never
inside an onboarding turn.** Onboarding is deterministic and makes no model call
on purpose — that property is what makes an open door safe, and a blocking
third-party HTTP call would regress it. The first turns may still run on the platform
default while the queue catches up; the account's own key takes over when it exists.

## 8. No silent fallback

Resolution raises stable machine codes rather than degrading quietly:

| Condition | Code |
|---|---|
| Account has no key and no platform default | `runtime_ai_not_configured` |
| Key row exists but ciphertext is missing | `runtime_ai_byok_missing` |
| Bedrock unavailable and fallbacks disabled | upstream error, surfaced |

A quiet downgrade to a shared key is how you find out at the end of the month.

## 9. Open

- ~~**Credits are 0** on the OpenRouter account.~~ **Not a blocker — corrected
  2026-07-27.** Routing is BYOK onto our own Bedrock credential (§2, D-O), so a
  minted key spends on our AWS bill and never on an OpenRouter balance.
  `total_credits: 0` is the expected steady state. This document, PR-38 and the
  AI-1 lane all treated it as the gating item; none of them should have.
- ~~Whether free users get a shared platform key or no key at all.~~
  **Settled 2026-07-27 (D-T): every user gets their own key with $5 on it,
  once.** The cap is not the interesting half — the *reset* is. Minted with no
  `limit_reset`, the $5 is a lifetime total; minted with `limit_reset: monthly`
  it would be $5 every month forever, which with an open door is a standing
  invitation. `TIER_RESET["free"]` is `None` and that is the whole paywall
  today. `beta` renews monthly for testers an operator granted deliberately.

  Minting fires when **onboarding completes**, not at first contact, because the
  grant is real money and a number that probes once and never answers should
  cost nothing. It is still queued rather than called inline, so onboarding
  keeps its no-model-call, no-third-party-call property.

### Built, 2026-07-27 — and what is still unproven

Migration 008 adds `accounts`, `users.account_id`, `ai_keys` and
`ai_key_events`. Migration 011 queues provisioning for already-onboarded accounts
that predate the trigger. Migration 012 is a one-time operator backfill for every
account already present in the live table, including users still mid-onboarding;
live verification showed all 7 accounts with active key rows carrying both hash
and ciphertext. `saathi/openrouter.py` mints, revokes, resolves and
runs Chat Completions through the account key; `saathi/crypto.py` holds the
Fernet wrapper; `provision_key` is a registered `scheduled_turns` kind;
`saathi.admin.grant` is the operator command.

Verified: the migration is idempotent under a second run on a scratch copy; the
database itself enforces one active key per account (partial unique index), so
"calling twice mints once" survives a race rather than merely a tidy caller; the
`saathi:` prefix guard, refuse-if-unconfigured, and the lowest-cap fallback all
go red when removed from the production path.

**Proven live:** real keys were minted for all 7 accounts, the mis-tiered beta key
was revoked, the response carried hashes, and a real OpenRouter turn completed
through account 3's resolved key with token usage returned. Unit coverage asserts
the runtime request carries `allow_fallbacks: false`, `provider.zdr: true`, and
the fixed `z-ai/glm-5` slug.

---

## 10. Features considered, and refused

Surveyed 2026-07-27. OpenRouter's surface is wide; most of it duplicates a
decision Saathi has already made or asks us to hand one to a third party. Written
down so the feature list is not re-litigated from the marketing page.

### Adopt

| Feature | Why |
|---|---|
| **ZDR** (`zdr` per-request) | The mitigation for §3's residual. Routes only to endpoints with zero-retention policies, and **blocks** rather than silently degrading when none exists. OpenRouter itself does not store prompts unless logging is opted into. Set alongside `allow_fallbacks: false` — together they mean *our Mumbai Bedrock or nothing, and never retained in transit*. |
| **Zero-completion insurance** | Empty completions are not billed. Free. |
| **App attribution** (`HTTP-Referer`, `X-OpenRouter-Title`) | Trivial hygiene; identifies the caller in their dashboards. |

### Considered, deferred

**Structured outputs.** Could firm up slot extraction — but D-D measured *this*
model's entity accuracy through *this* path. Changing the output contract means
re-measuring, and PR-33 already says the existing measurement is thin.

**ORI eval.** Interesting for PR-9 and PR-33. See `PATTERNS_TO_BORROW.md`.

**Guardrails / classifiers.** Only ever as a *second* layer. The priority-0 regex
is not replaceable: a forwarded scam can argue with a model-based classifier; it
cannot argue with a function that has already returned. Putting a model in front
of it would be a regression dressed as an upgrade.

**Response caching.** Note what it is: **full response caching**, not prompt
caching. It returns a stored identical answer; it does not reuse a cached prefix.
**So D-D's prefix budget stands** — cost remains linear in prompt size and
`SAATHI_PREFIX_TOKEN_BUDGET` keeps its job.

Its upside here is small — Saathi's turns are nearly all unique — and it carries a
hazard: if two users ask the same question, does the second receive the first's
cached answer? For elder health conversations that would be a cross-user leak.
**Verify cache scoping before ever enabling it**, and do not enable it for the
small win alone.

### Refused

| Feature | Why not |
|---|---|
| **Input/output logging**, **broadcast** | Already `false` on the workspace and must stay so. Elder health content must not be logged to a third party — PR-29's lesson, learned the same day. |
| **Web-search plugin** | Search already runs on Vertex `asia-south1`. PR-20 was fought precisely to get it into Mumbai; their plugin routes through their providers. |
| **Server tools / fusion** | Server-side tool execution moves the decision away from `provenance.allowed_tools()`. Same objection as the Agent SDK. |
| **LangChain integration** | Saathi has its own loop, deliberately. |
| **Response healing** | D-F already strips markdown in code, because a deterministic transformation must not depend on instruction-following. Healing is the same bet we refused. |

### The Agent SDK, and why the loop stays ours

The Agent SDK is **TypeScript-only**, so it is not available to a Python
codebase. It would be wrong even if it were: its selling point is that the SDK
executes tools and tracks conversation state, and that is precisely the decision
`provenance.allowed_tools()` and `assert_no_forbidden_tools()` exist to make.
PR-23 was this exact shape — a path reaching state-changing behaviour without
passing the provenance check.

The **Python client SDK** is fine and is used for provisioning: it is generated
from their OpenAPI spec, so it is authoritative where the prose docs are wrong by
omission — `workspace_id`, `limit_reset` and `expires_at` are all real parameters
the docs page does not mention. Its dependencies are `httpx` and `pydantic`, both
already present. Inference stays on plain `httpx`.


OpenRouter workspace correction verified 2026-07-27: `OPENROUTER_WORKSPACE_ID` is set to `718e8438-6c5a-48f9-85c9-f8909f2e4c47`; all seven active Saathi keys list under that workspace with limit 5 and no reset; Default workspace lists no Saathi keys; account 1 completed a real OpenRouter turn returning `workspace route ok` with token usage.


Future provisioning guard: `openrouter.mint()` now raises `ProvisioningDisabled` if `OPENROUTER_WORKSPACE_ID` is unset, so a config drift cannot silently mint into OpenRouter Default again.

Future-signup guard: `openrouter.mint()` refuses to mint unless `OPENROUTER_WORKSPACE_ID` is set, and every create-key request includes that workspace id. Verified on-box after deploy.
