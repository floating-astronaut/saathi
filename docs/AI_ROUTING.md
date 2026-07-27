# AI routing and per-account keys

How a Saathi turn reaches a model, who pays for it, and where the data goes.

Status: **designed, not built.** Nothing routes through OpenRouter today. This
document exists before the code, because the change touches inference location,
cost and a third-party processor — see `THE_METHOD.md` §1.

Owns: model routing, per-account key provisioning, spend caps, residency.
Related: `DECISIONS.md` D-D (model choice), D-O (this routing change),
`vendor/` (captured OpenRouter API docs), `PROD_READINESS.md` PR-15 (rate limiting).

---

## 1. Today

Every model call is `boto3` → Bedrock `zai.glm-5` in **ap-south-1**, using the
box's instance role. One credential, no attribution, no per-user cap. `PR-15`
records the consequence: an onboarded user can send unlimited voice notes, each
costing STT minutes and a model turn, and nothing enforces §14's free-tier cap.

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

**One key per paying account/household.** Free users run on the platform default.

### Tier → cap

Unknown tier falls back to the **lowest** cap, never the highest. Fail safe, not
open — the same shape as `tier_cap()` in the MeshPilot implementation this is
modelled on.

## 5. Provisioning, in order

1. **Idempotency first.** Select an active key for the account; if one exists,
   return it and mint nothing. Calling twice must not create two keys or two
   charges.
2. **Refuse if unconfigured.** No master key, or no Fernet key → raise
   `ProvisioningDisabled`. Never mint and hope; never store a plaintext because
   encryption happened to be unavailable.
3. Mint with the tier cap, `workspace_id` = Indofolk AI, `limit_reset: monthly`.
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

    saathi:account:<account_id>:plan:<tier>:env:<env>

Self-describing, because that string is the only join back to a tenant when you
are staring at the OpenRouter dashboard during an incident.

**This org also holds MeshPilot's keys.** `DELETE /keys/{hash}` works on all of
them. So every list, revoke and sync operation **asserts** the `saathi:` prefix
and refuses to act on a key without it. Not a convention — an assertion, in the
code, like `assert_no_forbidden_tools()`. A shared account means the guard
cannot live in the discipline of whoever runs it next.

## 7. Where it runs

Minting happens on the `scheduled_turns` queue as kind `provision_key`. **Never
inside an onboarding turn.** Onboarding is deterministic and makes no model call
on purpose — that property is what makes an open door safe, and a blocking
third-party HTTP call would regress it. The first turns run on the platform
default; the account's own key takes over when it exists.

## 8. No silent fallback

Resolution raises stable machine codes rather than degrading quietly:

| Condition | Code |
|---|---|
| Account has no key and no platform default | `runtime_ai_not_configured` |
| Key row exists but ciphertext is missing | `runtime_ai_byok_missing` |
| Bedrock unavailable and fallbacks disabled | upstream error, surfaced |

A quiet downgrade to a shared key is how you find out at the end of the month.

## 9. Open

- **Credits are 0** on the OpenRouter account. Keys will mint and then fail on
  first use — provisioning succeeds, spending does not. Fund before any real
  user depends on it.
- Whether free users get a shared platform key or no key at all.
