# Engineering Supervisor — Saathi

Append-only lane log. **Evidence, not intentions.** A lane is not closed until
the contract docs are updated and evidence is recorded here.

---

## 2026-07-26 — Lane SAATHI-0: from PRD to a live webhook

Opened against `PRD-whatsapp-elder-agent.md` v0.1. Closed with the product
reachable on the public internet and 82 tests passing.

### Shipped

- **Infrastructure.** `i-01b2c27883acb25ca` (ap-south-1, t3.large, Ubuntu 26.04,
  encrypted EBS, IMDSv2 required), zero inbound rules, SSM-only access, no SSH
  key. Postgres 18.4, Python 3.14.4, ffmpeg 8.0.1, uv 0.11.32.
- **Schema.** 11 tables owned by the `saathi` role; extensions split from schema
  because `pg_trgm` is untrusted and applying it all as `postgres` would have
  left every table owned by the wrong role.
- **Agent.** Tool loop on `zai.glm-5`, 10 tools, prefix budget enforced in code.
- **Memory.** Facts + the ASR entity-bias vocabulary; hard erasure.
- **Speech.** ffmpeg both directions, Saaras `indic-en`, local correction pass.
- **Safety.** Deterministic pre-LLM classifier, Hindi + English + Hinglish.
- **Reminders.** RRULE, timezone-correct, Postgres `SKIP LOCKED` queue.
- **Channel.** WABA `1023945910495878` (`Saatih AI APP`), phone
  `1127963600410973` — CLOUD_API, VERIFIED, CONNECTED, displays as "Saathi AI".
- **Public.** `https://saathi.n8nworld.store` via Cloudflare tunnel; two systemd
  units plus cloudflared, all enabled.

### Evidence

- Queue claims exactly once: synthetic due fire → `claimed=1`, immediate
  re-claim → `second_claim=0`. Synthetic rows deleted.
- Live pipeline against real Postgres and real GLM-5 (send stubbed): reminder
  created at **08:15** from "sawa aath" with correct RRULE and queue row;
  replayed webhook → `skipped: duplicate`, no send; "seene mein dard" → safety
  fired, **agent never ran**, event logged.
- ffmpeg round trip in-process: OGG/Opus → WAV16k → OGG/Opus.
- Entity correction on live Saaras output: `bomlodipin` → `Amlodipine`.
- Webhook through Cloudflare: correct verify token → `200 CHALLENGE-OK`; wrong
  token → 403; correctly signed POST → `200`; tampered / wrong / absent
  signature → 403.
- Box Cloudflare token verified **from the box**: `active`, zones listable, R2
  listable.

### Measured, and it changed decisions

- **`zai.glm-5` 8/8** on Hinglish time + medicine extraction where the cheaper
  models scored 3–7/8. Regional ap-south-1 endpoint, so inference stays in India.
- **LLM cost ≈ ₹60/user/month**, not the PRD's ₹135 — measured at ~1,750 input
  tokens/turn, prefix ~1,330 of a 3,000 budget.
- **`codemix` returns Devanagari**, which makes entity correction structurally
  dead. `indic-en` is the correct mode. PRD §9 was wrong.
- **API-side keyword boosting is noise** — changed 1 of 3 transcripts, not for
  the better. The local correction pass is the mechanism.
- **Templates**: `session_resume`, `daily_checkin` APPROVED/UTILITY;
  `reminder_fire_v2`, `reminder_nudge_v2` submitted UTILITY after the first pair
  came back MARKETING at 7.5× the price.

### Bugs found by running it, not by reading it

1. **ffmpeg pipe WAV header** — `0xFFFFFFFF` length fields; Sarvam rejected 2.5 s
   of audio as ">30 seconds". Every voice note would have failed in production
   while `ffmpeg -version` looked healthy.
2. **Model published its chain of thought** as the user-facing reply, in English,
   then failed to call the tool. Prompt now forbids visible workings.
3. **Persona gender flipped** between turns (`rakhunga` → `rakhungi`). Pinned.
4. **Cloudflare BIC 1010** blocked every webhook while `/healthz` passed — and
   made the security probes *look* like they were passing. See `LANDMINES.md`.
5. **`saathi/db` package shadowed `saathi/db.py`**, breaking `/healthz`.

### Mistakes worth recording

- **Deleted two templates to fix their category.** Meta holds the name for up to
  four weeks; both names are burned and the live ones are `_v2`. Never delete a
  template to fix it.
- **Printed a page access token** by `select *`-ing a Graph response, and later
  **printed live HubSpot / Retell / Shopify credentials** by `select *`-ing
  `core.brand_integrations`, where secrets live inside a JSON blob rather than a
  column named like one. Those credentials need rotation. Project columns; never
  `select *` on anything that might carry a credential.
- **Claimed Business Agent needed allowlisting** after probing the wrong host. It
  is `api.facebook.com`, not `graph.facebook.com`, and we are eligible.
- **Called "no WABA exists"** from an inconclusive probe. There were five, under
  a verified business, including one already named for this product.

### Queued

- `WA_APP_SECRET` landed; **register the callback URL with Meta** so real
  messages arrive.
- Managed Postgres before external users — no backups today.
- TTS, onboarding + consent, real eval corpus of elder voice notes.
- Rotate the credentials exposed above.

---

## 2026-07-26 — Lane SAATHI-1: channel live end to end

### Closed

- **Public site.** `https://n8nworld.store` — landing plus `/privacy/`,
  `/terms/`, `/data-deletion/`, the three URLs Meta app review checks. Next.js
  static export on Cloudflare Pages (`saathi-site`), source on the **`site`
  branch** so application pushes never trigger a site build. Deployed by direct
  upload.
- **Operating entity named**: Indofolk Wellness Private Limited, Greater Kailash
  I, New Delhi, GSTIN `07AAHCI7432A1ZV` — matching the business verified in Meta
  BM. An earlier draft named a different entity (a proprietorship); its GSTIN was
  dropped rather than carried over, since reusing another legal person's tax ID
  would have been false.
- **Domain verified with Meta** — TXT added at the apex without disturbing the
  existing SPF or google-site-verification records.
- **Webhook registered.** App `1571039744742551` subscribed to
  `whatsapp_business_account` → `https://saathi.n8nworld.store/webhook/whatsapp`,
  fields `messages, message_template_status_update, account_update`, active.
  WABA `1023945910495878` subscribed to the app.
- **All four templates APPROVED as UTILITY** — including `reminder_fire_v2` and
  `reminder_nudge_v2`, which had first come back MARKETING at 7.5× the price.
  The rewrite (anchoring the body to the user's own prior action) held through
  review. This settles the ~₹20 vs ~₹90/user/month question in our favour.

### Evidence

- `GET /{app}/subscriptions` → object `whatsapp_business_account`, our callback,
  `active: true`.
- Meta called our verify endpoint synchronously during registration and it
  passed — which exercises the tunnel, the Browser-Integrity-Check rule and the
  verify token in one shot.
- Signed webhook POST → 200; tampered, wrong and absent signature → 403.

### 🚩 Open risk found while verifying

`GET /{waba}/subscribed_apps` returns **two** apps:

    MeshPilot        1571039744742551   (ours)
    Business Agent   1143680903703001   (Meta's)

Meta's Business Agent app is subscribed to our WABA's webhooks. Its
`rollout.enabled` is `false`, so it should not be responding — but a subscribed
app plus one toggle is all that stands between us and Meta's model becoming the
primary responder, which would bypass the deterministic §12 safety classifier
(R7). Recommend unsubscribing it. Not done unilaterally: it was not created by
this lane. See `LANDMINES.md`.

### Queued

- Unsubscribe the Business Agent app from the WABA (operator decision).
- Replace the landing page's template waitlist copy with real product copy.
- Managed Postgres before external users — still no backups.
- TTS, onboarding + consent flow, real eval corpus.
