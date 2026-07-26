# Landmines

Traps already paid for. Each one cost real time to find, and every one of them
*looked fine* from the outside — that is what makes them worth writing down.

Read this before touching **Meta**, **Cloudflare**, or **audio**.

---

## Audio: ffmpeg to a pipe writes a broken WAV header

**Symptom:** Sarvam rejects 2.5 seconds of audio with
`"Audio duration exceeds the maximum limit of 30 seconds"`.

**Cause:** WAV stores its length in the RIFF and `data` chunk headers. ffmpeg
cannot seek backwards on a pipe, so it writes the `0xFFFFFFFF` streaming
placeholder. Sarvam reads that as a near-infinite duration.

**Why it is nasty:** `ffmpeg -version` is healthy, the byte count is right, and
the file plays locally. **Every inbound voice note fails in production.**

**Fix:** write to a temp file so the header is patched (`speech/audio.py`).
`tests/test_audio.py` asserts the size fields are real.

---

## Speech: `codemix` returns Devanagari, which silently disables entity correction

**Symptom:** the correction pass repairs nothing, ever. No error.

**Cause:** the correction pass matches Latin tokens against the user's medicine
and people names. Under a Devanagari transcript there is nothing to match.

**Fix:** `mode=indic-en`. Same audio then gives `bomlodipin` → `Amlodipine`.
The PRD's recommended `codemix` is wrong for this product.

---

## Meta: never delete a template to fix it

**Symptom:** `"You can't change the category for this message template while
the existing English content is being deleted"` — for 24 retries over 12 minutes.

**Cause:** Meta holds a deleted template name for **up to four weeks** and
refuses a category change while the old content is deleting.

**Cost:** the names `reminder_fire` and `reminder_nudge` are burned. The live
templates are `reminder_fire_v2` / `reminder_nudge_v2`.

**Fix:** to change a template, **submit a new name**. Never delete first.

---

## Meta: utility templates get recategorised as MARKETING (7.5× the price)

**Symptom:** submitted `UTILITY`, came back `MARKETING`. At ₹0.8631 vs ₹0.115
this took the highest-volume template from ~₹10 to ~₹78/user/month.

**Cause:** Meta reads `"Namaste! {{1}} ka time ho gaya hai"` as an unsolicited
notification. UTILITY requires the body to visibly follow from something **the
user themselves requested**.

**Fix:** anchor the copy to the user's own prior action —
`"Aapne jo reminder set kiya tha — {{1}} ka time ho gaya hai."` Both then
classified UTILITY on submission.

---

## Meta Business Agent is provisioned on our number and must stay disabled

`GET api.facebook.com/{phone_number_id}/agent_config/settings` shows an agent
with `rollout.enabled = false` but `ai_audience: EVERYONE` and
`followup: {enabled: true, 3600s}`.

**Enabling it makes Meta's model the primary responder**, so inbound messages
never reach the deterministic §12 safety classifier — risk R7, the one
non-negotiable gate. Its knowledge model is business-scoped (a storefront
schema: delivery, returns, payment) with no per-user memory, which is the whole
of this product.

We *are* eligible (`is_eligible: true`). It is simply the wrong architecture
here. It is a strong fit for MeshPilot's ecommerce brands.

**Worse than it first looked:** `GET /{waba}/subscribed_apps` shows the Business
Agent app (`1143680903703001`) is *already subscribed to our WABA's webhooks*,
alongside ours. Only `rollout.enabled = false` keeps it quiet. A subscribed app
plus one toggle is all that separates us from Meta's model answering first.
Check this list after any Business Manager change.

---

## Cloudflare: Browser Integrity Check 1010-blocks webhooks, and fakes a passing security test

**Symptom:** `/healthz` returns 200 through the tunnel, but every webhook call
returns 403.

**Cause:** `browser_check: on` for the zone. Meta's calls are server-to-server
with no browser signature, so BIC rejects them with error 1010.

**Why it is genuinely dangerous:** the wrong-token and unsigned-POST probes
*also* returned 403 and looked exactly like the app correctly rejecting them.
The security checks appeared to pass while proving nothing. Only comparing
on-box (`200 CHALLENGE-OK`) against through-Cloudflare (`403 server=cloudflare`)
exposed it.

**Fix:** a config rule scoped to the hostname (`http_config_settings`,
`bic: false`) rather than disabling BIC zone-wide. Needs a token with **Config
Settings Write** — neither the canonical box token nor the master token has it.

**Rule to keep:** when a security check passes, confirm it passed *for the
reason you think*. Test the positive case too.

---

## Bedrock: model access is per-account, and the "availability" field is not the gate

`get-foundation-model-availability` reported `NOT_AVAILABLE` for a model that
invoked perfectly, and `AVAILABLE` for one that returned `AccessDenied`. The
real gate for Anthropic models is the one-per-account use-case form.

Requesting new model access can also move an account off a grandfathered
entitlement onto the form-required path, breaking models that worked minutes
earlier. It did, in the dev account.

---

## AWS: never put a secret in an SSM command

SSM `RunShellScript` command text is retained and visible in the console. Any
secret embedded in a command leaks into the audit trail permanently.

**Fix:** Secrets Manager + the instance role. The box fetches its own secrets
(`/usr/local/bin/saathi-env-sync`); nothing sensitive crosses SSM.
