## 2026-07-30 — Gujarati/Malayalam users had no priority-0 safety net; added native patterns (SAFE-LANG-1)

Symptom: LANG-2 shipped Gujarati and Malayalam as user languages, but the priority-0
deterministic safety classifier (medical emergencies, self-harm, scams — matched
*before* any model call) only covered Hindi/English/Hinglish. A native-script
Gujarati/Malayalam "I have chest pain", "I want to die", or "send money now or your
account is blocked" was **not** caught deterministically — it fell through to the
model, without the priority-0 guarantee. That was the documented gap from D-AF.

Closed it: added native-script gu/ml patterns to every family — emergency (chest
pain, heart attack, breathlessness, a fall, unconsciousness, stroke, heavy
bleeding), hypoglycemia, self-harm, medical-advice, and native pressure phrases for
scam/suspicious (electricity-cut and courier/customs threats, "send money"/"account
blocked", warrant/arrest). The mechanical scam markers — OTP, PIN, CVV, KYC, AnyDesk,
UPI brand names — are Latin and were already caught for every language. Non-Latin
scripts are case-less, so the existing normalise/`re.I` path handles them unchanged.

Verified live: 16 representative gu/ml sentences across all families each fire the
right trigger, and benign gu/ml sentences (weather, hunger, tea, a routine doctor
visit) do not. 25 new tests, 665 total. **The patterns are a first pass and still
want a native-speaker review** (flagged in the classifier) — but this is a real
priority-0 net where there was none, following the "prefer a false positive over a
false negative" rule.

## 2026-07-30 — widened the tool-use eval to 38 real questions, still 100% (AGENT-1)

Grew the agent tool-use eval from 13 to **38** cases across 10 categories: health/
medicine (side effects, doses, normal BP/sugar — must look up, not guess), general
knowledge, live data (gold rate, petrol price, cricket, tomorrow's London weather),
conversions, translation, drafting, time/date, and more actions (list reminders,
create reminder, add to list). Deliberately includes stress cases — current office-
holders that must be *looked up* not recalled ("President of India" → Murmu). Live
run: **100% answered well, 100% right-tool, 0% give-up** across all 38. Added a guard
test so a typo'd `expect_tool` in a future case fails loudly. Eval-only change — no
runtime/serving-path impact.

## 2026-07-30 — measured the agent's tool-use: 100% answered well (AGENT-1, increment 2)

Capability was anecdotal ("it couldn't tell the temperature"). Now it's measured.
`saathi/eval/agent.py` runs a fixed set of real questions through the actual agent
loop against the live model and scores each: did it call the required tool, did the
answer contain the expected text, did it give up. It's side-effect-free — a fake DB
and a dry-run tool handler run `look_up` for real but stub the state-mutating tools,
so the eval reads what the model *reached for* without writing a row or sending
anything.

First live run: **100% answered well** across 13 cases (weather, facts, web,
arithmetic, conversation, and actions like reminder/remember/list) — 100% right-tool,
0% give-up. Building it also caught a scorer bug: the give-up detector flagged
"insulin kaam nahi kar paati" (a correct explanation of diabetes) as a surrender
because of a bare "kar pa"; tightened to genuine give-ups and pinned with a test.
Run it with `python -m saathi.eval.agent`. 8 new tests. AGENT-1 closes: the agent
reliably reaches for tools and answers, and there's now a harness to keep it honest.

## 2026-07-30 — the agent gave up instead of reaching for its tools (AGENT-1, increment 1)

Symptom: "what's the temperature in Toronto" got "couldn't find it" — a question
Google answers trivially. The weather bug (LOOKUP-1) was one cause; the deeper one
is that the agent **surrendered** after one failed look_up instead of trying web
search. The capability was never missing: live, our Google-grounded web search
already answers Toronto's temperature, the PM of Canada, USD→INR, etc. The gap was
reliability, not power.

First increment (more under lane AGENT-1):
- **Deterministic fallback:** `look_up` with kind `weather` now tries the forecast
  provider *then web search*. A place the forecaster can't resolve is answered by
  Google rather than failing the turn — no reliance on the model choosing to retry.
- **Prompt:** the weather in another city is a normal thing to answer, not to
  refuse; if one look_up returns nothing, try kind `web` before giving up; "I
  couldn't find it" on a Google-answerable question is a failure, not humility.
- **Tool description:** clearer — "answer a question about the world using live
  search… reach for it rather than saying you can't help"; and pass a bare place
  ("Toronto") to weather, not a sentence.

1 new test, 633 total. Remaining in AGENT-1: a measured tool-use/QA eval set and
broader hardening. **Scope note:** this makes Saathi *reliably answer and act*; it
does NOT add code execution or unbounded actions — capability-by-absence (no money,
no OTP, no account access) is the elder-safety boundary and stays.

## 2026-07-30 — onboarding is now voiced for voice users (VOICE-2)

A person who talks to Saathi by voice was still onboarded in silent text — the
worst case being an elder who can barely read. Now, if someone has ever sent a
voice note, every onboarding message (welcome, consent detail, the name/reminders/
training questions, "all set!") is **also** sent as a voice note in their chosen
language, on top of the text + buttons.

- **Detection needs no new state:** `_voice_user()` checks the `messages` log for
  any inbound voice note. So a voice user is recognised across the tap-driven
  steps, not just on the message they happened to speak.
- **Additive + best-effort:** buttons/lists can't ride a voice note, so text stays
  the primary and the voice is an accessibility layer; a TTS failure never breaks
  onboarding.
- **Boundary intact:** this does not violate "onboarding never calls the model" —
  TTS is a Sarvam vendor call on our *own fixed copy*, not the LLM, and the fixed
  strings hit the phrase-bank cache so it's nearly free. The language-picker
  message stays visual (a list to tap); voicing begins at the welcome.

4 new tests, 632 total.

## 2026-07-30 — "temp in Toronto" got "couldn't find it" (or the wrong city) (LOOKUP-1)

Symptom: asked the weather for Toronto, Saathi answered it couldn't find it. Two
bugs in `lookup/weather.py`, both reproduced live:

1. **The stored home city overrode the named city.** `city = ctx.get("city") or
   query` meant a Mumbai user asking "temp in Toronto" got *Mumbai's* weather —
   the wrong-city answer the module's own docstring calls worse than "I don't
   know". (If they had no stored city, it fell through to #2.)
2. **Phrases didn't geocode.** Open-Meteo needs a bare place name; the model often
   passes "temp in Toronto" / "toronto ka temperature", which returned no hits →
   "couldn't find it". (Also, multi-word cities like "New York" were never URL-
   encoded, so they broke too.)

Fix: a place **named in the question wins** over the stored home city, which is
now only the fallback for a bare "aaj mausam?". Geocoding tries the raw query,
then a filler-stripped version ("temp in Toronto" → "Toronto"), then the home
city; names are URL-encoded. Verified live: Toronto/New York now answer correctly,
and a bare "aaj mausam" still uses the home city. 4 new tests, 628 total.

## 2026-07-30 — voice notes sounded muddy and robotic; fixed the engine + encode (VOICE-1)

Symptom: TTS was enabled, the round-trip worked, but the voice sounded bad —
muddy and robotic. Root cause was two-fold and had nothing to do with the TTS
vendor: we were on `bulbul:v2` at **22050 Hz**, then crushing it to **32 kbps**
Opus after a forced resample (Opus is a 48 kHz codec, so 22050 → 48000 happened
badly), with **no preprocessing** so English words and numbers in code-mixed text
("Amlodipine 5mg") were mispronounced.

Fixed, all within Sarvam (no vendor change, D-AE holds):
- **`bulbul:v3`** — newer, higher quality, emits native **48 kHz** over REST, so
  no resample. Verified live our key serves it at 48 kHz.
- **`enable_preprocessing: true`** — normalises English/numeric tokens in mixed
  text. Critical for Saathi's Hindi/English mixing.
- **Opus encode** → 48 kHz (soxr), `application audio`, mono, **48 kbps** (was a
  muddy 32 kbps phone-call-grade encode). All config-driven.
- **Per-language voices** (`speech.TTS_SPEAKER_BY_LANG`): a single voice sounds
  off across languages, so each gets its own v3 speaker — Hindi/Hinglish `ritu`,
  Gujarati `priya`, Malayalam `kavitha`, English `neha`. v3 has a different
  speaker roster than v2, so the old `anushka` default is retired.

2 new tests, 624 total. Researched against Sarvam's docs and how Pipecat/LiveKit
wrap the same API (they use the WebSocket streaming mode for live calls; Saathi's
async voice notes are the HTTP batch case, which is what we use).

## 2026-07-30 — Gujarati and Malayalam added as full languages (LANG-2)

Saathi now offers five languages at signup: Hindi, Hinglish, English, **Gujarati**,
and **Malayalam**. (Onboarding already asked language first — that part didn't need
building; adding the languages did.)

- **Picker is now a WhatsApp list, not buttons.** Five languages exceeds WhatsApp's
  3-quick-reply limit, so the language step uses an interactive list. New
  `wa.send_list` / `Channel.send_list`; `context.button_id` reads `list_reply` too.
- **Localised everywhere:** onboarding, ack/snooze, command replies, paywall, the
  "already onboarded" copy, and the model's reply-script rule all gained gu/ml. The
  gu/ml strings are a first draft flagged for native review.
- **Fixed a latent bug found on the way:** STT was hardcoded to `hi-IN` for *every*
  user — a Gujarati or Malayalam (or English) speaker's voice note was transcribed
  as Hindi. Now the user's `lang_pref` picks the Sarvam code (via `speech.sarvam_lang`),
  and TTS uses the same map. Verified live that Sarvam serves gu-IN/ml-IN.
- **Safety gap, documented not hidden (D-AF):** the priority-0 deterministic
  classifier still matches Hindi/English/Hinglish only, so native-script gu/ml
  emergencies/scams aren't caught deterministically yet (they fall through to the
  model; forwarded Hindi/English scams still catch). Operator chose to ship the
  languages with the gap recorded; native-verified patterns are lane SAFE-LANG-1.

8 new tests, 622 total (was 614). No migration — `lang_pref` is unconstrained and
unknown values fall back to Hindi, so the change degrades safe.

## 2026-07-30 — a voice-first product that only wrote back can now speak (PR-8)

Symptom: PR-8 was the biggest felt gap — Saathi is voice-first, elders talk to it,
and it answered only in text. Now, when enabled, it replies with a Sarvam Bulbul
voice note.

- **Provider: Sarvam Bulbul** (`bulbul:v2`), chosen by the operator over Google
  TTS. This reverses D-S (Sarvam was STT-only for lack of per-account capping) —
  now legitimate because the usage ledger can meter and cap it, the exact reversal
  condition D-S named. Recorded as **D-AE**. Verified live our key has TTS access
  and the API contract (`docs/vendor/sarvam/text-to-speech.md`); live testing
  caught the `inputs ≤ 3 per request` cap, so long replies batch and concatenate.
- **Trigger: voice-in → voice-out**, the operator's start policy. It maps onto the
  `users.voice_reply_pref='auto'` default that already existed; `always`/`never`
  honoured; onboarding stays text-only. Whole feature behind `SAATHI_TTS_ENABLED`,
  **off by default** — no live behaviour change until enabled.
- **Additive and best-effort:** the voice note is sent *after* the text reply, so a
  TTS failure, cap refusal, or Sarvam outage can never break a turn. Policy lives
  in `core/context.should_voice`, mechanism in the channel (`send_voice`), so SMS
  degrades to text. Most of the delivery path (`wav_to_ogg_opus`, `upload_media`,
  `send_audio`) already existed; the new work is synthesis + a swappable provider +
  a phrase-bank cache for the fixed strings.
- **Metered like STT:** each synthesis writes a content-free `sarvam/tts` ledger
  event (character count) and, under the global enforcement flag, reserves before
  the call. TTS input is Saathi's own reply text (never user content) and stays
  in India, preserving the inference-in-India rule.

12 new tests (614 total, was 602). Proven end to end: real Sarvam call → OGG/Opus
voice note, single- and multi-chunk. Remaining: the *live-in-prod* send to a real
thread happens at enable time (flag off); and Sarvam's per-char TTS price is a
labelled estimate until reconciled against an invoice (PROD_READINESS PR-8-TTS).

## 2026-07-30 — STT accuracy was unmeasured against real elders; built the harness to measure it (PR-9)

Symptom: every entity-accuracy number Saathi has ever quoted was measured on
**TTS-generated speech** — a machine reading a clean sentence into a clean mic.
A 70-year-old on a 2G line with the television on is a different acoustic
universe, and synthetic audio is not just cleaner, it is *differently* distorted.
So R1 (mishearing the one word that matters — the medicine name) was the product
risk and it was unmeasured against reality.

You cannot fabricate the fix: real accuracy needs real recordings, and generating
synthetic voice notes would be the exact `ffmpeg -version` trap this lane names.
So this change ships the **measurement infrastructure**, not a number:

- `saathi/eval/` — a loader (`corpus.py`, fails loudly on a malformed manifest
  rather than silently shrinking the eval), pure scoring (`metrics.py`,
  `score.py`), and a runner/CLI (`run.py`).
- The metric is **entity accuracy, not WER** (PRD §15: WER "will actively mislead
  you"). Entities are matched with the *same* normalisation and 0.78 fuzzy
  threshold the product uses (`speech/correct.py`), so the eval never reports
  accuracy the pipeline can't deliver. Scored at two stages (raw vs corrected) so
  the correction pass's real-world lift finally gets a number.
- The honesty gate: an **empty corpus yields no accuracy figure** — the runner
  prints "0 real samples → no accuracy claim" and exits 0. A number appears only
  when real audio is behind it.
- `docs/STT_EVAL.md` — the collection + transcription + consent (DPDP) protocol
  and the manifest schema. `evals/corpus/` ships empty and git-ignored.

15 new tests (602 total, was 587). Remaining (PR-9's open tail, a data task):
collect 50–100 consented real elder voice notes per language and run the harness
to get the first real number — before the next model-version decision.

## 2026-07-30 — tore down the unused Meta Conversions API Gateway

The Cloud Run Gateway the operator had stood up on 2026-07-27 was a web-pixel path
that CTWA attribution (CAPI-1) never used — Saathi sends conversion events directly
to the dataset. It had been billing since install. Deleted from GCP project
`saathi-ai-503623`: both Cloud Run services (`gc05b56ab51771-capig`, `-hub`), the
`gc05b56ab51771-storage-bucket` (107 objects, including stray `capig-restore-key-*`
secret files), and the two installer service accounts. Verified gone via the Run
and Storage APIs — the project now has zero Cloud Run services and zero buckets.

Infrastructure deletion, so there is no code change; the record lives in
`docs/CAPI_GATEWAY.md` and here. Only residue is a stale "installed" gateway record
in Meta's Events Manager (GCP-side cleanup cannot reach it), to be cleared there.

## 2026-07-30 — docs reconciled: runtime box now signs, migration marked complete

Symptom: the signing contract was self-contradictory across the tree. After the
runtime box was given its own SSH signing key (registered on GitHub + GitLab,
`allowedSignersFile` set, `%G?` = `G`), four docs still asserted the opposite —
`README.md`, `CLAUDE.md`, `CONTRIBUTING.md` and `DECISIONS.md` D-L all said the
runtime box "cannot sign / is unsigned by necessity" and that `%G?` is unusable.
Same tree still described the box migration as *in progress* and named the retired
box `i-01b2c27883acb25ca`.

Fix (docs only, no code):
- `DECISIONS.md` D-L: appended a 2026-07-30 update — runtime box signs now; the
  "pushes unsigned" line is superseded; PR-22 blast-radius point sharpened (this
  box now holds a signing key *and* forge write creds).
- `CLAUDE.md`: box table + migration blockquote updated to the successor box
  `i-03a4911f2f7de793d` / acct `635860424621`; signing guardrail and execution
  rule corrected.
- `CONTRIBUTING.md`: "Every commit" section — signed on both boxes; `%G?` usable.
- `README.md`: migration marked complete; worker kinds, Postgres 18.4 updated.

Verified on the box: `git log -1 --format='%G?'` = `G`; `aws sts
get-caller-identity` = `635860424621` / `IndofolkDevBoxRole`; `pg_lsclusters` = 18.

## 2026-07-30 — saathi-env-sync is in the repo now, so deploys stop aborting (RUNTIME-ENVSYNC-1)

Symptom: every `ops/deploy.sh --local` on the successor box aborted at
`saathi-env-sync: command not found` (ops/deploy_onbox.sh), before restarting
services. The helper that pulls Secrets Manager into `~/saathi/.env` and
`~/saathi-gcp-sa.json` had only ever existed in `/usr/local/bin` on the *original*
box — it was never in the repo, so the hand-built successor box never had it, and
`.env` had to be maintained by hand.

Root cause under it: the runtime secret was **not the full source of truth**. The
box's `.env` carried 8 keys that were only in `.env` and not in the secret —
including `SAATHI_DB_DSN`, which holds the database password. A naive "rewrite
`.env` from the secret" would have dropped the DB connection and broken the app,
which is likely why env-sync was quietly skipped here.

Fix:
- Moved those 8 keys into `saathi/dev/runtime` (value-blind; the DB password now
  lives in Secrets Manager, not just on disk). The secret is now the complete
  45-key source of truth, so a rewrite is lossless — verified: the regenerated
  `.env` is a superset of the old one, no key dropped, no value changed.
- Added `ops/saathi-env-sync` to the repo: reads both secrets via the instance
  role (no profile, no key material on disk), writes `.env` (0600) and
  `~/saathi-gcp-sa.json` (0600) atomically, value-blind. Backs up the previous
  `.env` first.
- `ops/deploy_onbox.sh` now `install`s it from the repo before the deploy step
  that calls it, so no future box depends on a hand-placed copy.

Verified: env-sync runs clean; `settings` load the DB DSN, audio bucket, CAPI
dataset id, GCP SA path, model and dm_policy from the regenerated `.env`; a full
`ops/deploy.sh --local` now completes through env-sync → uv sync → tests → restart
→ verify with the manual copy removed first, proving the deploy installs it.

## 2026-07-30 — Click-to-WhatsApp attribution (CAPI-1): the click id we were throwing away

Symptom: ad spend on "ads that click to WhatsApp" had no conversion signal, so Meta
could not attribute which ads brought which signups. The data was already arriving
and being discarded — Meta puts a `ctwa_clid` on the first message of an
ad-originated conversation, and `pipeline.extract_messages` passes the whole message
through, so the click id sat in the payload and nothing read it.

Fix (Model B — we send our own event, so Meta never analyses elders' threads):
- Migration 016 adds `ctwa_clid` + `ctwa_captured_at` to `users` (content-free).
- `capi.capture_referral`, called in `pipeline.handle_message` right after identity
  resolve — before the admission/dedupe gates, because an ad click is a fact even
  for a handle that never onboards — stores the click id **write-once**.
- `capi.report_lead`, called at onboarding completion in `onboarding.py`, POSTs one
  `LeadSubmitted` to `graph.facebook.com/v21.0/{DATASET_ID}/events` with
  `action_source: business_messaging` and only the `ctwa_clid` + WABA id in
  `user_data`. No phone, no message content — the click id is the match key, so the
  event carries nothing about the person. Fire-and-forget with metrics.py's
  discipline: it never raises into a turn, and it no-ops for organic signups
  (no click id) and when `SAATHI_CAPI_DATASET_ID` is unset.

Boundary recorded as D-AD: attribution is a one-way signal to Meta; Saathi does not
build a cross-Meta identity graph. The Cloud Run Conversions API Gateway the
operator had stood up is a web-pixel path this flow does not use — teardown
candidate (docs/CAPI_GATEWAY.md).

Verified: 587 tests (10 new) assert the event structurally cannot carry content or
PII, capture is write-once, and a Graph outage returns cleanly. Live: migration
applied to the box; a probe with our exact payload was accepted by dataset
`2038444060213473` (owner Indofolk) on every field and rejected *only* the synthetic
`ctwa_clid` — `"Messaging Event Invalid Ctwa Clid"` — proving the wiring is correct
and only a real ad click's id is needed.

## 2026-07-30 — inference moved onto a Bedrock-only credential that cannot expire

Symptom: nothing failing yet, and a deadline nobody set. Inference ran on
`AWS_PROFILE=saathi`-derived credentials — an Identity Center session renewed from a
refresh token in `~/.aws/sso/cache/`. Nothing on the box can renew that
non-interactively, so whenever the chain finally broke, `converse()` would start
returning an auth error and the symptom would be an assistant that had stopped
answering. It also carried far more authority than inference needs: that profile is
AWSAdministratorAccess in `559896294326`.

Fix: a dedicated IAM user `saathi-bedrock-invoke` in the inference account, reached
with a static key delivered through `saathi/dev/runtime` and consumed only by
`saathi/bedrock.py`, which now prefers an explicit key pair over a named profile over
the ambient chain. The key arrives by env-sync rather than through `~/.aws/`, which
nothing syncs and a rebuilt box would not have — the `~/.aws/credentials` copy made
during setup was deleted so the pair exists in exactly two managed places.

The user's inline policy allows `Converse`/`ConverseStream`/`InvokeModel` on exactly
two model ARNs — `zai.glm-5` and `qwen.qwen3-vl-235b-a22b` — pinned to ap-south-1,
plus an explicit `Deny NotAction: bedrock:*` so no later policy attachment can widen
it. The region pin is doing product work as well as security work: "inference stays in
India" now lives in the credential, so a call routed elsewhere fails rather than
quietly succeeding.

Verified by probe against the new credential — every one denied: S3 `ListBuckets`,
reading the old audio bucket, `GetSecretValue` on `saathi/dev/runtime`, SSM
`send-command` against the old box, `iam:ListUsers`, `ec2:DescribeInstances`,
`cloudwatch:PutMetricData`, Bedrock in us-east-1, and `zai.glm-4.7` (a model outside
the two allowed). Both permitted models return a live "pong". 577 tests pass,
`/healthz` 200 through the tunnel, and the app authenticates as
`arn:aws:iam::559896294326:user/saathi-bedrock-invoke` rather than as an
administrator.

MIGRATION-BEDROCK-1 drops from P0 to P1 — no longer a credential that dies on its
own, still a cross-org dependency. The new trade is recorded as PR-BEDROCK-KEY: a
long-lived key with no rotation, whose real fix is deleting it once model access is
granted on `635860424621`.

Also corrects the record: attaching `AmazonBedrockMantleFullAccess` to the box role
did not and could not unblock the new account. `authorizationStatus` is an
account-level entitlement; `entitlementAvailability: AVAILABLE` means available to
request, not granted. `Operation not allowed` reads like an IAM denial and is not one.

## 2026-07-30 — Postgres 18.4, so recovery is single-headed again

Symptom: nothing was broken, which is what made this worth fixing. This box ran
Postgres **16.14** (the Ubuntu 24.04 default) while the original box ran **18.4**
(the Ubuntu 26.04 default). A custom-format dump from 18 is archive version 1.16
and `pg_restore` 16 refuses it outright — so the documented recovery path pointed
at a file this box could not read. That only surfaces during an incident, holding
a backup that will not open.

Fix: installed 18.4 from PGDG (`apt.postgresql.org`, noble) — the distro has no 18
for 24.04 — and upgraded with `pg_upgradecluster 16 main`. Chose that over a
hand-rolled dump/restore because it carries the cluster globals: the `saathi` role
kept its password and `CREATEDB`, table ownership survived, and it swapped the
ports itself, so the app's `:5432` DSN needed no edit. Downtime was 52 seconds,
taken 6½ hours ahead of the next due reminder rather than at an arbitrary moment.

Verified after: `users=8 messages=262 scheduled_turns=58` and the state histogram
(`acked 12, failed 1, pending 9, sent 25, skipped 11`) unchanged; 26 tables, 14
`schema_migrations` rows, `pg_trgm 1.6`, all 26 tables still owned by `saathi`;
sequences still at the data's max (`users` 21, `messages` 274). `/healthz` reports
`18.4` through the tunnel, the app reads through its own DSN as the `saathi` role,
577 tests pass, zero errors, and a fresh backup dumped and verified by restore on
18.

The claim this was all for, proven rather than assumed: the original box's own 1.16
dump — the exact file that failed under 16 — now lists 26 TABLE DATA entries and
restores 8/262/58 into a throwaway database. Closes MIGRATION-PG-VERSION-1.

The 16 cluster was kept stopped on port 5433 as an instant rollback, then dropped
later the same day at the operator's instruction, along with the
`saathi_preempty_20260730` database left over from the data move (26 tables, zero
rows — schema only, confirmed before dropping). Rollback is therefore
restore-from-backup now rather than a port change. What stands behind it:
`/var/backups/saathi/pre-pg18/` holds the pre-upgrade custom dump and the cluster
globals, `s3://saathi-dev-artifacts-635860424621/backups/postgres/` holds the
6-hourly verified backups, and the original box's database is still intact. A fresh
backup was taken after the drop specifically because the cheap fallback had gone.

## 2026-07-30 — the database finally followed the tunnel

Symptom: `/healthz` was 200 through the tunnel and the box looked cut over, but
this box's Postgres was empty — `users=0 messages=0 scheduled_turns=0` — while the
original box still held `users=8 messages=262 scheduled_turns=58` with its worker
still running. So inbound WhatsApp traffic was being served by a box that had
never seen these 8 people: their memories and reminders were invisible to the
assistant answering them, and the only reason reminders still went out at all was
that the *old* box's worker was quietly dispatching from its own copy. Retiring
that box would have taken 9 pending turns with it, one of them a medication
reminder due the same morning.

Fix: stopped the old worker first so nothing could double-dispatch, dumped, and
restored here. Two things made it not a straight `pg_restore`:

  * **Version drift.** The original box runs Postgres 18.4; Phase 1 installed
    16.14 here. A custom-format dump from 18 is archive version 1.16, which
    `pg_restore` 16 refuses outright ("unsupported version (1.16) in file
    header"). Dumped `-Fp` instead and stripped the single v17+ line the plain
    SQL carried (`SET transaction_timeout = 0`) — nothing else in the schema was
    version-specific.
  * **Ownership.** Restoring `--no-owner` as `postgres` left all 26 tables owned
    by `postgres`, and the app connects as `saathi`. The worker came up and threw
    `InsufficientPrivilege: permission denied for table scheduled_turns` on its
    first poll. Reassigned 26 tables, 21 sequences, 1 view and 12 enum types,
    plus the schema and database, to `saathi`.

Verified: `users=8 messages=262 scheduled_turns=58` and the state histogram
(`pending 9, sent 25, acked 12, failed 1, skipped 11`) match the source exactly;
26 tables, 14 `schema_migrations` rows, `pg_trgm` present; sequences sit at the
data's max (`users` 21, `messages` 274) so the next insert cannot collide. All 9
pending turns were confirmed future-dated before the worker was started — an
overdue set would have fired a burst of stale reminders at real people. Read back
through the app's own DSN as the `saathi` role: 8 / 9 / 262. Zero errors since the
ownership fix. A real backup then ran here: `OK 205152B tables=26 users=8`.

The old box's worker is now `disabled`, not merely stopped, so a reboot cannot
resurrect a second dispatcher against the same reminders. Its database is left
fully intact as the fallback, and the pre-restore empty database is kept aside as
`saathi_preempty_20260730`.

## 2026-07-30 — Saathi's AWS estate moved out of the MeshPilot org account

Symptom: the successor box looked healthy — `/healthz` 200 through the tunnel,
services active — while three things were silently wrong. `cloudwatch:PutMetricData`
was failing every 30 s with AccessDenied, so `WorkerHeartbeat` was not being
emitted by this box at all; the `saathi-worker-heartbeat-missing` alarm still read
`OK` because it was watching the *old* box's datapoints. Audio writes and artifact
reads were AccessDenied for the instance role. And both services carried a systemd
drop-in pinning `AWS_PROFILE=saathi` — an Identity Center profile into
`559896294326` — so every Bedrock call, metric and voice-note upload was crossing
into the MeshPilot org on a borrowed SSO token with hours left on it.

Fix (2026-07-30): moved everything movable into `635860424621` (mcc org),
ap-south-1. Created `saathi-dev-artifacts-635860424621` and
`saathi-dev-audio-635860424621` reproducing the originals' encryption, versioning,
public-access-block and lifecycle (90-day backups, 7-day voice TTL), and copied all
21 objects — verified by ETag manifest, and by SHA-256 for `saathi-repo.tar.gz`
where a multipart upload changes the ETag but not the bytes. Migrated
`saathi/dev/gcp-sa` byte-exactly (`aws --output text` appends a newline; the first
copy was 2369 bytes against the source's 2368, so it was rewritten through boto3).
Recreated the `saathi-alerts` SNS topic and both alarms. Replaced the borrowed
account's grants with five least-privilege inline policies on `IndofolkDevBoxRole`
mirroring the old `saathi-dev-box` role, scoped to the new account's ARNs.
Repointed `SAATHI_AUDIO_BUCKET` in `.env` and in the runtime secret;
`ops/deploy.sh` to the new instance, bucket and profile; and `ops/alerting/saathi-alert`
to the new topic, asking IMDS for the instance id rather than hardcoding it, since
the hardcoded one had gone stale through the move.

Verified with the instance role, no profile: voice-prefix put/get/delete, artifacts
list and `backups/` write, both secrets readable, `PutMetricData` in namespace
`Saathi` accepted. The negative cases deny — a write outside `backups/` and a
`PutMetricData` outside the `Saathi` namespace both return AccessDenied, so the
scoping fails closed. `/healthz` 200 locally and through the tunnel after restart;
`settings.saathi_audio_bucket` resolves to the new bucket; zero AccessDenied lines
since.

**Not moved, and blocking:** Bedrock. Every model in `635860424621` reports
`authorizationStatus: NOT_AUTHORIZED` — the account has never been granted model
access, and `PutUseCaseForModelAccess` refuses with "Your account is not authorized
to perform this action. Please create a support case." So `AWS_PROFILE=saathi`
**still stands** on both units and is the one remaining MeshPilot dependency; it
cannot be removed until AWS enables Bedrock on the new account. See
`docs/PROD_READINESS.md` MIGRATION-BEDROCK-1.

## 2026-07-29 — runtime bring-up Phase 1: app boots on the successor box

Symptom: the successor runtime box (`ip-172-31-41-224`) had no runnable app —
the `.venv` targeted Python 3.14 but symlinked to system 3.12, so `import fastapi`
failed; no Postgres server; no schema.

Fix (on-box provisioning, no application code changed): rebuilt the venv cleanly
on Python 3.13.14 via `uv` (satisfies `requires-python = ">=3.13"`); installed
PostgreSQL 16.14; created the `saathi` role + database to match the existing
`SAATHI_DB_DSN`; applied `db/extensions.sql` (pg_trgm), `db/schema.sql` (base v1
tables) and all 14 migrations (002–015) through the idempotent `schema_migrations`
checksum ledger (26 tables, 14 rows). Separately registered a second SSO profile
(`saathi`, AWSAdministratorAccess in `559896294326`) via device-code flow and
verified read-only reach to the `saathi/dev/runtime` secret (described, not read).

Verified: `GET http://127.0.0.1:3130/healthz` → `{"ok":true,"pg":"16.14
(Ubuntu 16.14-0ubuntu0.24.04.1)","model":"zai.glm-5"}` HTTP 200, 2.3 ms — the
`ops/deploy_verify.sh` success signal. The live webhook on
`saathi.n8nworld.store` was untouched throughout (still served from the original
box).

Phase 2 remains: systemd units, cloudflared connector, live cutover. No
application code changed.

Symptom: `saathi.n8nworld.store` (the WhatsApp webhook host) returned 404/405 for
`/healthz` and `POST /webhook` — i.e. a static site, not the FastAPI app.

Cause: during Cloudflare inspection, `saathi.n8nworld.store` was repointed from
the `saathi-dev` tunnel to the `saathi-site` Pages project. Pages serves a static
Next.js export and cannot receive a webhook or run Python. The webhook host and
the marketing site (`n8nworld.store`) are separate surfaces; only the latter
belongs on Pages.

Fix: reverted the CNAME `saathi.n8nworld.store → saathi-site.pages.dev` back to
the `saathi-dev` tunnel (`d4e9e4ad…cfargotunnel.com`), removed the hostname from
the Pages custom domains, and verified `/healthz` returns the live app payload
again. The marketing site on `n8nworld.store` was never affected.

Docs: recorded the in-progress runtime migration (original box
`i-01b2c27883acb25ca` → successor `ip-172-31-41-224`, ap-south-1) across README,
RUNBOOK, AGENTS/CLAUDE/KIMI, and PROD_READINESS. The webhook hostname and tunnel
are unchanged; only the connector moves. No application code changed.

## 2026-07-27 (AI-1 correction) — key names include workspace when configured

OpenRouter API key creation defaults to the Default workspace when `workspace_id` is omitted. Runtime config was missing `OPENROUTER_WORKSPACE_ID`, so the first live key batch landed in Default. Key names now include `:ws:<workspace-prefix>` when a workspace is configured, allowing a corrected remint even though revoked `ai_keys.name` values remain unique locally.

## 2026-07-27 (AI-1 follow-up) — turns use per-account OpenRouter keys

Focused verification: `uv run pytest -q tests/test_openrouter_keys.py tests/test_onboarding.py tests/test_capabilities.py tests/test_clock.py` — 57 passed.

- User chat turns now resolve `users.account_id` and pass the decrypted active OpenRouter key into the agent loop, so accounts with keys spend through their own capped credential instead of the box instance role.
- The OpenRouter runtime request is implemented through Chat Completions with constant `provider.allow_fallbacks = false`, `provider.zdr = true`, app attribution headers, and the fixed `z-ai/glm-5` model slug. Bedrock Converse remains as the no-key fallback for paths not yet account-plumbed.
- Provisioning dedupe keys are now versioned (`provision:v2:<account_id>`) because `scheduled_turns` keeps `(kind, dedupe_key)` unique forever. Migration 011 enqueues `provision_key` for already-onboarded accounts that have no active key; migration 012 additionally provisions every already-existing active account, including the mid-onboarding users in today's live table. Live verification after deploy: all 7 accounts have active key rows with hash+ciphertext, and a real OpenRouter turn through account 3 returned `route ok` with token usage.

# Changelog

## 2026-07-29 - staged Sarvam STT ledger enforcement (LEDGER-2)

- Added explicit rollout controls for local usage enforcement:
  `SAATHI_USAGE_ENFORCEMENT_ENABLED`, `SAATHI_USAGE_LEDGER_MODE=enforce`, and a
  positive `SAATHI_USAGE_ACCOUNT_CAP_PAISE` are all required before a call can
  be refused.
- Sarvam STT now computes the catalog INR paise estimate before transcription,
  reserves against the account cap before sending audio to Sarvam when
  enforcement is enabled, settles the hold after success, and links the usage
  event to the reservation.
- Reservation cap aggregates are scoped by currency, so USD model accounting
  cannot consume INR speech budget.

## 2026-07-29 - observe-only STT and template usage accounting (LEDGER-2)

- Successful Sarvam transcriptions record exact WAV duration and rounded billed
  seconds; successful WhatsApp templates record after Meta returns a message ID.
- Accounting failures never retry or disrupt an already-successful vendor call.

## 2026-07-29 - observe-only LLM usage accounting (LEDGER-2)

- Successful Bedrock and OpenRouter requests now append Saathi-owned usage
  events with actual input/output tokens, per-request latency and provider IDs.
- Routing, residency controls and user-visible replies are unchanged; a ledger
  write error is logged without failing a successful reply while observe-only.

## 2026-07-29 - vendor usage ledger foundation (LEDGER-1)

- Added migration 015 and the observe-only `saathi.usage` accounting API:
  idempotent account-locked reservations, append-only vendor events, settlement,
  release and auditable expiry. No paid call behavior has changed yet.
- Added `SAATHI_USAGE_LEDGER_MODE=observe` as the safe default. Focused ledger
  tests and the full suite passed before the PR checkpoint.

## 2026-07-29 - stronger deterministic scam shield (LIFE-5)

- Added pre-model coverage for courier/customs/police threats, electricity
  disconnection, fee-based loan/job/pension pressure, guaranteed-return
  investments, urgent UPI collection, and remote-support app requests.
- Lower-confidence pressure patterns return a fixed warning and one safe
  verification step; they do not reach the model. Clear fraud signals retain
  the stronger scam response and 1930 escalation.

## 2026-07-29 - stale WhatsApp handles cannot inherit an elder's account (ID-2)

- A WhatsApp handle silent for 60 days now receives a content-free check-in;
  after 90 days of uninterrupted silence the handle is revoked, not the user.
- A returning stale handle is blocked before conversation/history, message
  logging, transcription, tools, memory or the model. It must explicitly
  continue or request a 15-minute move code for a new number.
- `MOVE <six-digit-code>` works only from a blank new handle; it transfers the
  account, makes the new handle primary, and revokes the old one. Bare digits
  and established accounts cannot consume a move code.

## 2026-07-29 - Meta responder guard (SEC-1)

- Added an hourly systemd guard that fails loudly if Saathi's own WhatsApp
  webhook subscription disappears or Meta Business Agent settings appear.
- The check enters the existing `OnFailure` SNS alert path; it never logs a
  bearer token or callback URL.

## 2026-07-29 - inbound rate and concurrency admission (RATE-1/RATE-2)

### Added

- A process-local inbound-turn gate (default: 8) now bounds all work after
  identity/deduplication and before transcription, media handling, safety
  dispatch, or an agent turn. It refuses rather than queues.
- A Postgres-backed atomic reservation allows each user six inbound turns per
  rolling minute across text, voice, image, and document messages. The
  non-blocking advisory lock prevents concurrent same-user requests from
  over-admitting; duplicates consume no slot.
- Rate-limit and overload replies are bilingual, sent once per reason per ten
  minutes, then silent so an attack does not turn refusals into outbound cost.

### Still open

- This is an availability/fairness guard, not the cross-vendor cost ledger:
  edge/IP limits, multi-process global coordination, and monetary vendor caps
  remain in PR-15 / `docs/USAGE_LEDGER.md`.

## 2026-07-29 - CodeGraph installed for agent code navigation

### Added

- CodeGraph v1.5.0 is installed on the box and wired into Codex and Claude Code
  as a local MCP server.
- The Saathi source checkout now has a local `.codegraph/` index marker; the
  generated database remains untracked and can be regenerated with
  `codegraph init` or `codegraph index`.

### Verified

- `codegraph status` reports 102 Python files, 1,686 nodes, 3,633 edges, and an
  up-to-date index in `/tmp/saathi-main-sync`.
- `codegraph explore` returned line-numbered source and blast-radius output for
  the WhatsApp pipeline and observability paths.

## 2026-07-29 - tracing can export to Logfire project when token is present

**Focused tests passing:** `uv run pytest -q tests/test_observability.py` — 15
passed. Full suite: `uv run pytest -q` — 536 passed. OBS-3.

### Changed

- `observability.init()` now configures Logfire cloud export as
  `send_to_logfire="if-token-present"`, so the project write token decides
  whether spans are sent to Pydantic Logfire.
- The local OTel Collector export remains wired alongside cloud export.
- Privacy constraints are unchanged: `inspect_arguments=False`, fixed
  attribute allow-list, no message text/transcript/name/medicine/query params.

---

## 2026-07-29 - tracing follow-up: span failures cannot affect turns

**Focused tests passing:** `uv run pytest -q tests/test_observability.py` — 14
passed. Full suite: `uv run pytest -q` — 535 passed. OBS-2.

### Fixed

- `observability.span()` now preserves application exceptions exactly. Tracing
  enter/exit failures degrade to no-op behavior instead of replacing or
  suppressing the real turn error.
- The optional tracing stack no longer has a port conflict: the app exports to
  the OTel Collector on `127.0.0.1:4317`, and the collector exports to Jaeger on
  `127.0.0.1:4318`.
- Jaeger OTLP gRPC is bound to `127.0.0.1`, not `0.0.0.0`.
- Cleaned the architecture write-back so tracing and relayed-content rules are
  separate sections.

---

## 2026-07-29 - Phase 2 cutover: saathi.n8nworld.store now served from new dev box

All four services (saathi-web, saathi-worker, cloudflared-saathi, postgresql@16-main)
running on ip-172-31-41-224 (15.206.170.88). Public healthz proving through the
tunnel, Bedrock converse() returning live via SSO-profile AWS_PROFILE=saathi.
Original box cloudflared stopped; web/worker/postgres kept for rollback.

### Added
- ops/saathi-web.service, ops/saathi-worker.service, ops/cloudflared-saathi.service
- AWS_PROFILE=saathi systemd drop-ins for Bedrock/CloudWatch auth

### Verified
- https://saathi.n8nworld.store/healthz 200 (new box pg:16.14)
- /webhook/whatsapp 403 (unsigned, correct)
- uv run pytest -q - 577 passed
- Bedrock converse() returns live response via AWS_PROFILE=saathi
- Worker running with 6 scheduled kinds

## 2026-07-29 - in-region tracing: spans on the critical path, zero PII in telemetry

**Focused tests passing:** 11 passed (test_observability.py). Full suite: 532 passed. OBS-1.

### Added

- saathi/observability.py - privacy-hardened tracing via logfire SDK (OTLP
  exporter to local OTel Collector at 127.0.0.1:4317, Jaeger all-in-one on-box).
  Best-effort init behind SAATHI_TRACING_ENABLED.
- Spans on the critical path: pipeline.handle_message, safety.classify,
  agent.loop.run, every model.call (Bedrock/OpenRouter), and every tool_call.
- ops/saathi-otelcol.service, ops/saathi-jaeger.service, ops/setup-tracing.sh.
- Dependencies: logfire, opentelemetry-exporter-otlp, opentelemetry-sdk.

### Privacy rules

- inspect_arguments=False - hard-disable automatic function-argument capture.
- Fixed attribute allow-list: kind, latency_ms, input_tokens, output_tokens,
  tool_name, hop_count, model_id, error_class, trigger. Never message text,
  transcript, names, medicines, phone numbers, or query parameters.
- All data stays in ap-south-1; no traffic to logfire-us.pydantic.dev.




## 2026-07-28 — returning WhatsApp users do not restart signup

**Focused tests passing:** `uv run pytest -q tests/test_capabilities.py tests/test_language_change.py tests/test_onboarding.py` — 32 passed. Full suite: `uv run pytest -q` — 521 passed. ID-1.

### Fixed

- Old onboarding quick replies from an already-onboarded WhatsApp chat no longer
  restart signup or move `users.onboarding` away from `done`. Language buttons
  still work; consent/name/reminder/improve buttons answer that setup is already
  complete.
- Bare `start`/`hi` greetings from onboarded users remain normal conversation,
  so clicking the WhatsApp chat entrypoint does not create a second signup path.

---

## 2026-07-28 — forwarded content summarizes before asking what next

**47 focused tests passing.** `tests/test_provenance.py`, `tests/test_lookup.py`,
`tests/test_relayed_commands.py`, `tests/test_prefix_budget.py`. LIFE-1c.

### Changed

- Forwarded content now defaults to: skim and summarise first, flag obvious risk,
  extract amount/date/place/person/action when visible, then ask one question:
  what would you like me to do with this?

### Boundary

The question is only a follow-up. It does not imply Saathi acted on the forward;
mutating tools are still withheld and commands still require trusted text.

---

## 2026-07-28 — captionless media explains by default

**61 focused tests passing.** `tests/test_vision.py`, `tests/test_media_limits.py`,
`tests/test_provenance.py`. LIFE-1b.

### Fixed

- A bill, notice or screenshot sent as a single image with no caption now uses
  the document/daily-life reading prompt by default. The user does not have to
  send a second text message saying "please explain this".
- Captionless PDFs already behaved this way; the image intent classifier now
  matches that product expectation.

### Boundary

Medicine-specific interpretation still requires a medicine-shaped caption such
as dawa/tablet/medicine. Captionless media is read/explained; it still does not
act on instructions inside the media.

---

## 2026-07-28 — forwarded content now asks for one safe next step

**47 focused tests passing.** `tests/test_provenance.py`, `tests/test_lookup.py`,
`tests/test_relayed_commands.py`, `tests/test_prefix_budget.py`. LIFE-1.

### Added

- Relayed/forwarded content now carries explicit daily-life instructions to the
  model: explain what it says, extract amount/date/place/person/action when
  present, flag scam pressure, and end with exactly one safe next step.
- The global prompt now states the same rule for forwarded messages, bills,
  notices, screenshots and PDFs.

### Boundary

This does not allow forwarded content to act. Mutating tools are still withheld
for `RELAYED` turns, deterministic commands still require trusted text, and the
new tests keep the original prompt-injection defence in place.

---

## 2026-07-28 — cart building now produces India-first handoff links

**9 focused tests passing.** `tests/test_commercial_actions.py`,
`tests/test_prefix_budget.py`. CAP-2.

### Added

- `build_cart` still returns the plain numbered list as the contract, but now
  also returns visible provider handoff links for India-first surfaces: Blinkit,
  Zepto, BigBasket, Swiggy Instamart by default, with food/events/travel variants.
- The handoff builder is pure code: no vendor HTTP call, no paid API, no cookies,
  no account state, no checkout flow.
- OTP/card/account-shaped item text is omitted from URLs while staying visible
  in the readable list, so prompt-injected or secret-like cart text does not
  become a provider query.

### Boundary

The prompt and tool schema now say list/link handoff is allowed, but ordering,
booking, reserving, payment and account access remain absent.

---

What changed in the code, and — more usefully — **what broke and how we found
out**. Most of the entries below were discovered by running the thing, not by
reading it, and several looked healthy right up until they didn't.

Conventions:
- Newest first. One heading per working session, dated.
- **Broke / Fixed** entries name the *symptom first*, because that is what you
  will be searching for at 2am.
- Every behaviour change should have a test; where one exists it is named.
- Infrastructure and third-party facts live in `docs/RUNBOOK.md` and
  `docs/LANDMINES.md`; this file is for the Python.

---

## 2026-07-27 (night) — the button said हिंदी and the answer came back in Latin

**506 tests passing** (434 → 506). `tests/test_devanagari.py`. D-W, PR-44.

### Broke

- **Choosing हिंदी got you romanised Hindi.** The onboarding button has always
  been written in Devanagari; everything after it said "Namaste! Main Indofolk
  AI hoon". A promise broken in the first interaction.

  Two causes. Every deterministic string in this repo was romanised — that part
  is just text. The other was the prompt: *"Reply in the user's language and
  script. If they write Hinglish, reply in simple Hinglish."* That made the model
  **mirror** whatever it was sent, and an older adult with an English keyboard
  types "dawai" rather than "दवाई" regardless of what they read comfortably. So
  it mirrored Latin, forever, for everyone.

- **The commands were Latin-only**, which the conversion turned into something
  worse than cosmetic. Our own consent screen tells a Hindi reader to type
  "सब कुछ भूल जाओ" to erase their data — and `commands.parse` matched nothing
  for it. **The privacy policy promises erasure on request; that promise was
  kept only in Latin.** Same for "शुरू करें" and "चालू करो".

- **`chalu karo` never matched either, and that one predates today.**
  `r"\bchalu kar\b"` needs a non-word character after "kar", and "o" is a word
  character. The stop message tells people to say exactly that to resume, so
  RESUME was unreachable by its own advertised words.

- **Saathi called herself male in the safety replies.** "main aapki baat sun
  raha hoon" (self-harm) and "main salah nahi de sakta" (medical advice) —
  masculine forms, in the two most sensitive strings in the product, against a
  SYSTEM rule that says never to switch.

### Fixed

- **Script is a stored choice, stated every turn** (`prompt.script_line`), never
  inferred from the last message. Reading and typing are different skills.
- **Three options, not two**: हिंदी, Hinglish, English — which is also
  WhatsApp's hard limit of three quick replies. `hi-en` becomes first-class
  rather than legacy, because it would otherwise have fallen through `COPY` to
  `hi` and switched existing Hinglish users to Devanagari without asking.
- Devanagari patterns for every command, in all three scripts, plus the
  `chalu karo` fix.
- Feminine forms throughout the safety copy.

### What it costs

**Devanagari tokenises at ~1.77x Latin** — measured, not assumed: the welcome
message is 77 tokens romanised, 136 in Devanagari. No prompt caching, and
replies re-enter as history, so it compounds against the $5 grant (D-T).

Numerals stay international. 112, 108 and 1930 are dialled, and १०८ on an
emergency line is a hazard rather than a nicety.

### Not fixed, and it is the important one

**Reminders still arrive romanised** (PR-44). `reminder_fire_v2`,
`reminder_nudge_v2` and `daily_checkin` carry romanised Hindi in Meta-approved
body text. A template cannot be edited — it needs a new name, and Meta holds a
deleted name for four weeks. So the one message that matters most is the one
still in the wrong script, and a user now gets Devanagari onboarding followed by
a romanised reminder every morning.

### Tests

Six existing tests failed and were **re-expressed rather than loosened** — the
contracts are opt-in reminders, sugar-before-ambulance, and a restart phrase
that actually restarts. That last one now extracts the quoted phrase from
whatever the copy says and asserts it parses, so it cannot rot the next time the
script changes.

One of my own new tests was green for the wrong reason: `"Devanagari" in
p.system` passed with `script_line` deleted from `build_prefix` entirely,
because SYSTEM's own explanation contains the word. Found by deleting the call
and noticing the suite stayed green. Replaced with an assertion on the whole
line, plus one that the three scripts cannot collapse into the same prompt.


## 2026-07-27 (night) — the paywall, and the one thing it must never become

**429 tests passing** (411 → 429). `tests/test_paywall.py`. D-U.

### Added

- **An in-thread paywall.** Operator decision, overriding my recommendation to
  collect via a link-out: a WhatsApp-native product that sends people to a
  browser has broken its own premise for exactly the users least able to follow
  the detour. Migration 009 adds `accounts.status`, `psp_customer_id` and
  `account_payments`; `saathi/payments.py` builds and sends the invoice.

### The boundary, and what happened to it

Saathi's promise was that it **never transacts**, and the scam it exists to
blunt is not a stolen transfer — it is a trusted voice asking an elder to pay.
After this, Saathi can ask for money. That is a real reduction and it is not
worth describing as anything softer.

What bounds it is that the reduction is one deterministic path:

- **No payment tool exists.** `send_invoice`, `request_payment`,
  `order_details`, `charge`, `refund` are all in `FORBIDDEN_TOOL_NAMES`. The
  model cannot invoice, cannot be argued into it, and cannot be prompt-injected
  into it — the capability is absent, not guarded. Same argument as the safety
  regex at priority 0.
- **One caller, one price.** No amount is ever derived from something that read
  user text.
- **Priority 88** — above the agent, below everything deterministic. An account
  out of allowance keeps safety, onboarding, data erasure, reminder
  acknowledgement, and every command including STOP. Those are rights, not
  features to sell back to someone.
- **Reminders keep firing.** They run from the worker and never enter the chain.
  An unpaid bill is not a reason to stop telling someone to take their heart
  medication.

Razorpay collects; they will not take payment without a phone number or email,
so payer identity stays with them and we keep only the join. Off by default.

### The trap this design walked into and out of

`Handler.matches` is **synchronous** — `dispatch` calls `if not h.matches(ctx)`.
The first version of `_paywall_matches` was `async`, which returns a coroutine,
which is truthy. It would have matched every message and put the **entire user
base** behind the paywall, silently, on the first deploy. Caught before it ran,
by reading `dispatch` rather than by a test. Account status is now resolved once
in the pipeline onto `MessageContext`, the same way `onboarding` already was,
and a test pins the matcher as sync.

### A weak test, caught by red-checking it

`test_an_unconfigured_install_says_so_but_sends_no_invoice` passed with the
`saathi_payments_enabled` check **deleted from the source**, because the fixture
also left the merchant id blank — so `_assert_configured` still raised, for the
wrong reason. Added `test_the_kill_switch_alone_stops_the_invoice`, which
configures the gateway fully and toggles only the flag. That one does go red.
This is the sixth time green has agreed with a bug here; the difference is that
this time the deletion was tried before the test was believed.

### Inert on purpose, for now

**Nothing marks an account exhausted** (PR-42) — `mark_exhausted` has no caller,
so the paywall cannot fire yet. And **the payment webhook is not handled**
(PR-43): a user who pays would stay paywalled. `SAATHI_PAYMENTS_ENABLED` must
not be turned on before PR-43 exists.


## 2026-07-27 (night) — one captionless image broke that user's next four conversations

**411 tests passing** (405 → 411). `tests/test_blank_history.py`.

### Broke

- **Four turns died with no reply at all**, 08:05 to 08:28:
  `ValidationException: The text field in the ContentBlock object at
  messages.N.content.0 is blank.` The exception escaped the whole turn, so the
  user received nothing — no answer, no apology, no fallback. For an eldercare
  assistant, silence is indistinguishable from being ignored.

  **The `N` varied — 0, 1, 2 — and that was the clue.** It was not the incoming
  message that was blank; the agent capability already refuses to run on empty
  text (`lambda c: bool(c.text.strip())`). It was a row in the **history**
  loaded ahead of it.

  `messages.id = 55`: user 15 sent an image with no caption at 08:02:17, stored
  with `body_text = ''`. `conversation.history` filtered on `is not null` — and
  an empty string is not null. Every turn that user took for the next
  twenty-six minutes loaded that row, built `{"text": ""}`, and had the whole
  request rejected. It stopped when the row aged out of the twelve-message
  window, which is why it looked intermittent.

### Fixed

Two guards, because there were two failures — the row should not have been
written, *and* it should not have been loaded:

- `conversation.history` now filters `btrim(...) <> ''`, not `is not null`.
  Rows like 55 already exist, so filtering on read is the one that matters today.
- `log_message` normalises blank body/transcript to `NULL` at the write path,
  so the row cannot be created again.

### A wrong diagnosis, recorded because it was nearly shipped

I first blamed `pipeline`'s else-branch, which yields `ctx.text = ""` for any
unhandled message type, and built a capability to catch empty turns before the
agent. **An existing test failed and was right to** —
`test_empty_text_does_not_call_the_model` already asserted that empty text never
reaches the model, and it passes because the agent's matcher excludes it. The
fix was reverted. The `N > 0` in the error message had been visible from the
start and named the history rather than the message; I read it as noise.

### Why it matters more this week

WhatsApp Payments went live on this WABA (`1687148075730227` — the same number
Saathi answers), which adds `order` and `payment` to the inbound types that
arrive with no text body. Those would have joined captionless images as sources
of blank rows. See D-U.


## 2026-07-27 (evening) — per-account AI keys, and an account to hang them on

**405 tests passing** (384 → 405). `tests/test_openrouter_keys.py`. AI-1.

### Added

- **An account tenant.** Migration 008: `accounts`, `users.account_id`,
  `ai_keys`, `ai_key_events`. There wasn't one — the closest thing was `users`,
  which is a person reached through a handle. Spend cannot hang off a handle:
  India recycles numbers after ~90 days, so the next holder would inherit the
  bill, and every number change would strand a vendor key.

- **`saathi/openrouter.py`** — mint, revoke, resolve. One master provisioning
  key mints a capped sub-key per account, so spend is attributable per household
  and a runaway loop burns one tester's $5 rather than the platform balance.

- **`saathi/crypto.py`** — Fernet at rest. A minted key never sits in a table as
  plaintext and never reaches a log line, not even a prefix.

- **`provision_key`** as a `scheduled_turns` kind, and **`saathi.admin.grant`**
  as the operator command: `--tier beta` promotes an account and *enqueues* the
  mint rather than doing it, because the queue already owns retries, idempotency
  and the audit trail.

### The decisions worth arguing with later

- **Every user gets $5, once** (D-T, operator). Superseded the same day's
  earlier posture, in which free minted nothing. The cap is not the decision —
  **the reset is.** Minted with no `limit_reset` the $5 is a lifetime total;
  with `limit_reset: monthly` it would be $5 every month forever, and admission
  is deliberately open. `TIER_RESET["free"] is None` is the entire paywall
  today. Minting fires when onboarding *completes*, not at first contact, so a
  number that probes once and never answers costs nothing.
- **An unknown tier gets the lowest cap, never the highest.** A tier added to
  the enum and forgotten in `TIER_CAPS` must cost nothing rather than
  everything.
- **A broken account key never downgrades to the shared one.** Resolution raises
  `runtime_ai_byok_missing`. A quiet downgrade is how you learn on the invoice,
  a month later, about a tenant whose spend was never attributed.
- **The `saathi:` prefix is asserted, not assumed.** This OpenRouter org also
  holds MeshPilot's keys and `DELETE /keys/{hash}` works on all of them.
  MeshPilot serves live customers from another box.

### Proven, and not

Verified: 008 is idempotent under a second run on a scratch copy (2 accounts
before and after); the *database* enforces one active key per account via a
partial unique index, so "calling twice mints once" survives a race and not just
a tidy caller; a revoked key may coexist with a new active one, so rotation
works. The admin CLI was exercised against a real schema, not a fake connection.

Red-checked by deletion from the production path: the prefix guard (1 failure),
refuse-if-unconfigured (1), lowest-cap fallback (1).

**Superseded later on 2026-07-27:** a real key was minted and revoked, and runtime
routing was wired afterward. At the time of this entry, no real key had yet been
observed and every test stopped at the HTTP boundary.

### What this opens, and does not close

- **There is no paywall — only a key that stops working** (PR-40). When the $5
  is gone the turn fails and the person is told nothing useful. An elder whose
  assistant goes silent mid-conversation cannot tell that the reason is money.
  The exhausted-state reply is also the one turn that certainly cannot be
  generated by the model, so it has to be deterministic.
- **The grant is mintable by anyone who completes onboarding** (PR-41). The only
  thing between a stranger and $5 is answering a few buttons. It does not renew,
  which bounds the loss per number rather than per attacker.

### Also

- **Sarvam is STT-only** (D-S), because its spend cannot be attributed to a
  household — one key serves everyone, and there is no sub-key. STT is the one
  path whose cost is bounded by something already measured, the length of an
  audio file. PR-39.

---

## 2026-07-27 (evening) — the same nudge, four times, every one of them a success

**384 tests passing** (376 → 384). `tests/test_turn_settle.py`.

### Broke

- **A live user received the same nudge four times.**
  `"Sone ka samay ho gaya hai 😴"` at 15:55:59, 15:56:29, 16:11:29 and 16:26:30,
  and it would have gone on every fifteen minutes until the attempt budget ran
  out. Every one of those sends was a genuine WhatsApp `200 OK`. Nothing failed,
  nothing raised, and the log line that did appear —
  `turn 6 (nudge) was stuck claimed-but-unsent` — described the *symptom* as
  though it were the cause.

  `sweep_stuck` reclaims any turn left in `state='sent'` with a null
  `wa_message_id`, because that is exactly what a worker dying mid-send looks
  like. `nudge()` called `_handle()` and **discarded its return value**, so a
  perfectly delivered nudge was indistinguishable from an abandoned one. Every
  sweep found it, reset it to pending, and sent it again. `checkin()` had the
  identical hole.

  The bitter detail: `reminder()` did it correctly *and carried a comment
  explaining precisely this hazard* — "Left as 'sent', a paused user's reminder
  would be reclaimed and retried forever." The defence was understood, written
  down, and then simply not applied to two of the three senders. That is the
  same failure shape as the `messages.kind` bug: one path got the care, its
  siblings got copied without it.

### Fixed

- **`_settle(conn, turn_id, mid)` is now the shared last step of every sender**,
  and all three call it. Not a tidy-up: the previous design required each new
  handler to *remember* an invariant that only one of them documented. Three
  outcomes, all distinguishable — delivered (record the id), chose not to send
  because the user is paused or has no active handle (mark skipped), crashed
  (leave it for the sweep, which is the one case that should retry).

- **`MAX_ATTEMPTS` 5 → 3.** Operator decision: five deliveries felt like too
  many on the receiving end. Note it only ever governs *undelivered* messages —
  with the write-back fixed, a healthy reminder is sent exactly once and the
  sweep never sees it again. Three is a floor chosen against "would an older
  adult still want this dose flagged?", not a round number.

### How the tests were checked

Each guard was removed from the production path and the suite required to go
red: nudge discarding its id → 3 failures, checkin → 2, `MAX_ATTEMPTS` back to
5 → 1. The assertions are deliberately per-handler rather than one test of
`_settle`, because what needs guarding is not that the helper works — it is
that no sender is left out of it.

---

## 2026-07-27 — the agent had no idea what day it was

**376 tests passing** (366 → 376). `tests/test_clock.py`.

### Broke

- **"5 minute baad sone ki yaad dila dena" produced no reminder.** Reported from
  the live number with a screenshot: a voice note asked for a reminder in five
  minutes, and the agent asked for a wall-clock time — twice — then the
  conversation ended with nothing scheduled.

  The symptom looks like bad instruction-following. It is not. **The prefix
  contained no date, no time and no timezone**, and nothing else in the loop
  supplied one: `grep -n "datetime\|now(\|ZoneInfo" saathi/agent/prompt.py`
  returned nothing at all. "Five minutes from now" is not a phrasing problem
  when the model has no *now* — it is not a computable request, and asking for
  an absolute time was the only correct move left to it.

  The quieter half of the same defect: `create_reminder` takes
  `recurrence: once` plus a `date`, and a model with no clock can only **guess**
  that date. A guess lands on the wrong day and nothing looks broken — no error,
  no log line, a reminder cheerfully scheduled for the wrong Tuesday.

### Fixed

- **One line of clock in the prefix**, in the user's own zone:
  `Now, where the user is: Mon 27 Jul 2026, 14:05 (Asia/Kolkata).` Sixteen
  tokens; a realistic prefix goes 1,639 → 1,655 of the 3,000 budget. It is one
  line and not a block on purpose — there is no prompt caching on `zai.glm-5`,
  so this is paid on every turn, roughly 300 times per user per month. IANA zone
  names rather than "IST": the model reasons better about `Asia/Kolkata` than
  about three overloaded letters, and it is the same string the user would have
  to say back to correct it.

- **No clock means no `create_reminder`.** `Prefix.has_clock` is false when the
  caller has no user timezone (the document-reading path genuinely has no user),
  and `loop.run` then withholds the tool rather than trusting the model to
  notice it is guessing. Capability by absence, same argument as PRD §12: an
  absent tool cannot be talked into firing on the wrong day. `snooze_reminder`
  is deliberately *not* withheld — it takes a relative offset and never needs a
  date, which is exactly the shape `create_reminder` should grow next (PR-37).

- The prompt now also says to mention a remembered fact only when it is relevant.
  The same transcript had the agent padding a reminder request with
  "Aapne mujhe banaya hai".

### Not fixed — see PR-37

`create_reminder` still has no relative-offset parameter, so the arithmetic is
the model's to do. And `users.tz` is still trusted absolutely: user 15 is stored
as `Asia/Kolkata` while the handset showed UTC−4, so a 10pm request would have
been delivered at half past noon. **No reminder has yet been proven to arrive
end-to-end from a voice note** — these tests prove the tool is offered, not that
the message lands.

### How the tests were checked

Both guards were deleted from the *production path* — `if not prefix.has_clock`
replaced with `if False`, and `clock_line(now_local)` dropped from the assembled
text — and the suite required to go red: 2 failures and 1 failure respectively.
Five separate bugs have now shipped here with tests that agreed with the bug, so
a green test that has never been seen red is not evidence.

---

## 2026-07-27 (deploy) — the box could not deploy itself, and a red suite shipped anyway

**366 tests passing** (unchanged; no application code was touched). PR-28.

### Broke

- **`ops/deploy.sh` did nothing but fail when run on the box it deploys to.** It
  exports `AWS_PROFILE=mp-dev` and calls `ssm send-command`; on the runtime box
  there is no such profile and `ssm:SendCommand` is denied to `saathi-dev-box`,
  correctly. So a session standing on the target could not deploy, and the
  2026-07-27 deploy of `117896b` was done by copying four modules in by hand —
  the exact hand-rolling `CONTRIBUTING.md` warns against, chosen because the
  alternative was leaving a live forwarded-command vulnerability in place.

  Fixed with `ops/deploy.sh --local`, which skips the tar/S3/presign/SSM
  transport and nothing else. Everything that happens on the target moved into
  `ops/deploy_onbox.sh` and `ops/deploy_verify.sh`, which **both** transports
  now run, so there is still exactly one copy of PR-25's migration ledger.

- **A failing test run deployed silently.** `su - ubuntu -c "... uv run pytest
  -q | tail -2"` — `su -` is a login shell without `pipefail`, so the pipeline's
  exit status was `tail`'s, which is always 0. The suite could go red and the
  restart happened anyway. This is the loose end PR-25 named and deliberately
  left; it had to be rewritten here regardless. `uv sync` and `saathi-env-sync`
  were unchecked in the same way and now abort too, all of them before the
  restart.

  Proved by committing a deliberately failing test to a scratch checkout and
  watching the deploy stop: `1 failed, 366 passed` → `ABORT: tests failed on the
  box. Services not restarted.`

- **The post-restart verification could not fail.** It printed `is-active` and
  healthz and always exited 0, so a deploy that left `saathi-web` in `failed`
  still ended with `== done`. Byte-identical to the old inline block, so not a
  regression — but verification that cannot fail is skipped by another name. It
  now asserts every unit active, healthz `"ok":true`, a zero
  `traceback`/`critical` count, 200 through the tunnel and 403 on an unsigned
  webhook, and exits 1 if any of those is wrong. The message says plainly that
  the exit code prevented nothing: the restart already happened, so it is an
  outage report, not an abort. Proved by pointing a copy at a closed port and at
  a 404 route and watching both surface, without skipping the public-surface
  probes on the way.

- **A flag given without its value hung the deploy instead of refusing it.**
  `--repo` last means `$#` is 1, `shift 2` shifts nothing, and with no `set -e`
  in `deploy_onbox.sh` the `while` loop re-read the same argument for ever. Over
  SSM that is a 900-second `TimedOut` that reads like a sick box. Pre-mutation,
  so never dangerous — just the exact opposite of failing loudly, in the file
  whose thesis is failing loudly. `deploy.sh` had the same shape, where `set -e`
  exited but said nothing.

- **`chown -R ubuntu:ubuntu` was the one unchecked command left**, and it is the
  one that decides whether the services can read the code they are about to be
  restarted into. A partial chown leaves a half-root-owned tree that imports
  fine as root and fails as `ubuntu`. Now aborts before the restart.

- **A migration deleted from `db/migrations` stays on the box for ever** and is
  still picked up by the migration loop, because a deploy merges files in and
  never takes any out. Found while verifying this change, not fixed here — it is
  what a deploy *is*, and changing it is a different lane. `PROD_READINESS.md`
  PR-36. The live tree has no stale files today, but this branch deletes
  `worker/send_reminder.py` and `worker/reminder_scheduler.py`, which are on the
  box; after the next deploy they will still be there, in a `worker/` whose
  `main` version does not contain them. Harmless at runtime — nothing
  auto-discovers them — and recorded so the next reader is not misled by them.

### Fixed — one deploy, two transports (PR-28)

- `--local` is checked against the instance ID from IMDS and refuses if this is
  not `i-01b2c27883acb25ca`; an unreadable ID also refuses, because only the
  affirmative claim needs proof. The default transport refuses *on* the target
  instead of returning an IAM error that reads like a broken setup.
- Local mode is gated harder than remote, not less: git checkout, clean tree, on
  `main`, plus a remote naming saathi and a source that is not the deploy target
  — the last two aimed at the vestigial three-commit `.git` inside
  `/home/ubuntu/saathi`, which reports `main`, has no remotes, and misled a
  session into believing the box was full of hand-edits.
- A `--repo` other than the canonical tree is a **rehearsal**: real install,
  migrations, `uv sync` and tests, but no `saathi-env-sync` and no restart. Bound
  to the target rather than to a flag, so it cannot be used to skip those on a
  real deploy.
- Every install now snapshots the tree it is about to overwrite to
  `<repo>.prev/<utc>.tar.gz` (0600, newest three, `.env` excluded so runtime
  secrets do not accumulate in tarballs) and prints the restore command. Code
  only — migrations do not come back. `PROD_READINESS.md` PR-35.
- The SSM heredoc went from ~120 `\$`-escaped lines to five containing no
  dollar signs and no backticks at all. It is unquoted and expands on the
  authoring box; a previous session put backticks in a comment in it and the
  heredoc ran `su - ubuntu` on the *dev* box at generation time and hung.
- `--repo /` passed every containment check — `/` is not "inside" anything — and
  would have tarred the filesystem into `/.prev` and copied the staged tree over
  it. System directories are now named and refused.
- `--check --target` contradicted itself and the target was silently ignored;
  it now refuses. The IMDS lookup gets a second attempt, because failing closed
  is right but the moment `--local` matters most is an incident, and one blip on
  the token PUT should not turn "deploy the fix" into "refusing --local".

No Python changed. Verified against a scratch target directory and a scratch
Postgres database — never the live tree, the live database or the live `.env`;
the deployed tree was confirmed byte-identical to its commit before and after.
`--local --check`, which is read-only, was run against production and passed.
The real restart, `saathi-env-sync` and the SSM transport can only be proven by
a real deploy and were not.

## 2026-07-28 (hardening) — an inbound document had no limit, and never arrived

**366 tests passing** (337 before). PR-26.

### Broke

- **Every inbound document failed before it reached the reader.** Send a PDF and
  nothing comes back — no reply, no refusal, just a `failed handling wamid.…`
  in the web log. `handle_message` logs the message before it dispatches, and it
  logged WhatsApp's wire type: `insert into messages … kind = 'document'`, which
  Postgres answers with `invalid input value for enum msg_kind: "document"`.
  The transaction aborts and the whole turn unwinds, so the media capability at
  priority 30 never ran. The `msg_kind` enum has six values and `document` is
  not one of them.

  Not caught by the suite for the reason `LANDMINES.md` already records: the
  fake connection records the SQL string and never parses it. Confirmed against
  the real database instead — `select 'document'::msg_kind` errors.

  Fixed by coercing the wire type at the single write path (`_msg_kind`), which
  logs a warning and records `text`. The row exists for dedupe and for the
  transcript, and both survive the coercion. `MSG_KINDS` is asserted against
  `db/schema.sql` by a test, so the two cannot drift.

- **A timed-out `pdftoppm` was not killed, only abandoned.** `wait_for` cancels
  *our wait*, not the renderer, so an overrunning rasteriser kept a core on a
  two-core box and nothing was left holding a reference to it. It is now killed
  and reaped, and the test asserts the child's exit status is `-9` rather than
  asserting our exception — a shrug and a kill produce the same exception.

- **A killed render left the sender's PDF and a partial PNG in `/tmp`.** Cleanup
  only ran on the success path, and only for the one filename it guessed right.

- **A `.docx` was sent to the vision model as if it were a photograph** — one
  model call spent to produce nothing, and then silence for the user.

- **The rendered page was briefly world-readable.** `pdftoppm` creates the PNG
  itself, under our umask, so someone's prescription or bank letter sat in
  `/tmp` at 0644 until we deleted it. Both files now live in a `mkdtemp` 0700
  directory, which also makes the cleanup one call that cannot miss one.

### Fixed — resource limits on inbound media (PR-26)

Onboarding is open, so "a valid sender" is a low bar. Every limit below is a
bound on what *one* message may cost a box with 2 vCPU and 8 GiB that is also
running the reminder worker.

- **A byte cap before and during the download, not after.**
  `wa.client.fetch_media` now takes `max_bytes` with **no default** — a new call
  site must say what it can afford — and checks three times, cheapest first:
  Meta's own `file_size` from the metadata call (so a 90 MB PDF costs no
  bandwidth at all), `Content-Length`, and then the bytes as they stream, which
  is the only one of the three we supply ourselves. A size we could not
  determine is not treated as small. 8 MiB for PDFs, 5 MiB for photographs —
  which is the vision model's own ceiling, so the two cannot drift and leave us
  holding a blob we already refuse to use.
- **`pypdf` runs off the event loop**, in a thread pool the same size as the
  document gate, with an 8s wall clock. It was synchronous and inline: a content
  stream that took ten seconds to decode took ten seconds of everybody else's
  turns with it.
- **Page count refused before extraction or rasterisation** (200), and extracted
  text capped per page and in total. Note what this does *not* do, since the
  first draft of this entry claimed it did: counting the pages **is** the page
  tree walk (`len(reader.pages)` → `get_num_pages` → `_flatten`), so the guard
  cannot fire until pypdf has visited every node. Measured: 60,000 pages fit in
  7.07 MiB — under the byte cap — and cost 4.63s and 295 MiB of peak RSS to
  count. The pool, the gate and the 8s clock contain that; the guard buys the
  extraction and the render, not the count.
- **`pdftoppm` gets rlimits from the kernel** — CPU, address space, and file
  size, the last being the only part of this path that writes to disk — plus a
  15s timeout and a kill. `-scale-to` replaces `-r 150`, so the raster is
  bounded by our configuration rather than by the page's declared size. Only
  RLIMIT_CPU and RLIMIT_FSIZE arrive as signals; **RLIMIT_AS does not kill
  anything**, it makes `mmap` return ENOMEM, and pdftoppm then exits 127 without
  loading libm. That path fails closed and the user still gets a message, but
  the comment used to say otherwise.
- **Two backpressure gates** (`saathi/core/backpressure.py`): four **image and
  document** messages in flight process-wide, and **one** document being parsed.
  The second document is refused, not queued — a queue in front of CPU-bound
  work is the same unbounded growth wearing a hat. The document gate covers the
  CPU half only and is released before the model call, which is a 10-45s network
  wait; holding a 1-of-1 slot across that would refuse everyone else's document
  to protect an idle core. Voice notes do **not** pass the media gate — audio
  concurrency is still unbounded, and audio is the primary modality.
- **Every refusal is a message**, bilingual and specific, saying what would work
  instead ("send me a photo of just the page that matters"). There is no longer
  any exit from the media path that drops the turn silently.

Proven by running it, not by reading it: real `pypdf` on a real 250-page PDF,
the real `pdftoppm` for the happy path *and* for the kill *and* for the
`RLIMIT_FSIZE` kill (SIGXFSZ, exit `-25`), the real `httpx` stack for the
streaming cap, and an HMAC-signed document webhook POSTed to the real FastAPI
route — which is a committed test, not a scratch script, because the claim
should stay true after the next change. Each guard was then **deleted from the
production path** and the test that covers it confirmed to go red — nine for
nine. `tests/test_media_limits.py`.

`_render_limits` is worth one line on its own: it runs between `fork()` and
`exec()` in a process that has threads, where an allocation can block on a
malloc lock the fork orphaned. It said "nothing here allocates" while computing
`mb * 1024 * 1024` and two tuple literals. The values are now built in the
parent and only indexed in the child. This is also why
`SAATHI_DOC_CONCURRENCY` is not a throughput knob — at 1, no pypdf thread is
running when we fork. `LANDMINES.md` has the long version.

### Still open

Per-user rate limiting. The gates bound how much runs *at once*; they do not
bound how often one sender may ask. Widened onto `PROD_READINESS.md` **PR-15**
— it belongs with admission control, covers audio and text as well as
documents, and needs state that survives a restart.

Every outbound media reply is stored in `messages` **twice** — `pipeline` inserts
it and `wa.client._send` records it again at the wire path, and the `on conflict
(wa_message_id)` that was supposed to absorb the duplicate never fires because
pipeline's row has a NULL id and NULL never conflicts. Pre-existing on the agent
path and now replicated onto the refusal paths. Not fixed here because the two
rows differ — pipeline's is redacted, the wire path's is not — so deleting the
duplicate silently drops redaction from outbound storage. Written up as PR-34.

---

## 2026-07-28 (deploy) — a failed migration used to restart the services anyway

**337 tests passing.** No Python changed; this is `ops/deploy.sh` and two new
files under `db/`.

### Broke

- **A migration could fail and the deploy would carry on and restart the
  services.** `remote.sh` runs with `set -uo pipefail` and no `-e`, and the loop
  was `psql ... >/dev/null 2>&1 && echo ok || echo FAILED`. The failure printed
  a word and changed nothing else. `saathi-web` and `saathi-worker` then came
  up against a schema they did not match.
- **You could not find out why it failed.** `2>&1` to `/dev/null` threw away
  psql's error. The deploy log said `FAILED` and nothing more.
- **Every deploy silently re-ran every migration**, and two of them are not
  idempotent — which is the part nobody had noticed. `003_admission_control`
  ends with `update user_channels set status='active' where status='pending'`
  and `005_onboarding` with
  `update users set onboarding='done' where onboarding='new' and created_at < now()`.
  Correct once, as backfills. Re-run, they **admit every pending unknown sender
  and mark every half-onboarded user as consented** — the admission gate and
  the consent step, both undone by deploying.

  Measured rather than reasoned about: a schema-only copy of the live database,
  one pending `user_channels` row, one `onboarding='new'` user, put through the
  old loop. Both came out `done / active`, with all six migrations reporting
  "ok". Everything looked healthy. It was not.

### Fixed

`ops/deploy.sh` now aborts before the restart. Any of — empty `SAATHI_DB_DSN`,
ledger unavailable, migration error, ledger write error, checksum mismatch —
prints `MIGRATION ABORT` and exits 1, and psql's stderr goes to the deploy log
instead of `/dev/null`.

New `db/schema_migrations.sql` creates the ledger
(`version, checksum, applied_at, origin, note`) and `db/record_migration.sql`
writes a row after each migration commits. Version is the filename; checksum is
the sha256 of the file as applied, so editing a migration after it ran aborts
the next deploy rather than being skipped in silence.

The six migrations already on the box are **baselined, not assumed**: each is
claimed only if a sentinel object that exists if and only if that file
committed is visible right now. Each migration is a single `begin/commit`, so a
visible sentinel means the whole file landed. Baselined rows are marked
`origin='baselined'` with a **NULL checksum** — nobody watched them run, so we
do not claim to know what ran.

Verified on scratch databases on the box, dropped afterwards; the live database
was only read (`pg_dump --schema-only`). Fresh bootstrap applies six and records
six; second run applies none; pre-ledger database baselines six and leaves the
canary rows at `new / pending`; partially migrated pre-ledger database baselines
002–004 and applies 005–007; edited migration aborts with both checksums shown;
injected failing migration prints the psql error, aborts, records nothing, and
never reaches `systemctl restart`. What could not be tested here is the deploy
end to end — it needs the dev box's AWS profile and SSM permissions. The
generated `remote.sh` was extracted and read instead, and `bash -n`'d.

Every psql call in the loop passes **`-X`**. `su - ubuntu` is a login shell, so
psql would otherwise read `~ubuntu/.psqlrc`, and the ledger read is parsed on
its field separator — one `\pset fieldsep ","` there makes every recorded
version stop matching, and migrations that were already applied get applied
again. Proven both ways against a planted `.psqlrc`: without `-X` the read comes
back `002_identity_and_channels.sql","8146f0…` and the loop starts re-applying
from 002; with `-X` all six still report "already applied". No such file exists
on the box today. `-X` is what keeps it from ever mattering.

Known window, written down in `PROD_READINESS.md` rather than smoothed over:
the ledger insert is a separate statement from the migration's own `commit`, so
a crash between the two leaves a migration applied but unrecorded.

---

## 2026-07-28 (later still, again) — the dead reminder path is gone

**337 tests passing.**

### Broke

- **Reading `worker/` told you a lie about how reminders fire.** Two modules
  sat there describing a queue that no longer exists: `send_reminder.py` and
  `reminder_scheduler.py`, both built around `reminder_fires`. Migration 006
  moved dispatch to `scheduled_turns`; neither module was deleted, and neither
  was imported by anything.
- **The cost was paid in reading, not in runtime.** A previous session read
  `reminder_scheduler.py`, believed it was the live scheduler, and had to
  prove by grep that it was never invoked. Dead code that reads like live code
  is a trap laid for the next person.

### Fixed

Deleted `saathi/worker/send_reminder.py` and
`saathi/worker/reminder_scheduler.py`. Nothing imported either — verified by
grepping the whole tree for `import`/`from` statements naming them, and by
checking `ops/`, the systemd units and `pyproject.toml`. The only surviving
mentions are historical ones in `CHANGELOG.md`, `docs/` and the docstring of
`tests/test_reminder_delivery.py`, which is the test that exists *because* of
this confusion and should keep naming it.

The live path is unchanged: `saathi/worker/__main__.py` imports `turns` for the
side effect of registering kinds, and polls `scheduling.run_once`. After the
deletion `scheduling.registered()` still returns
`['checkin', 'media_purge', 'nudge', 'reminder']`.

---

## 2026-07-28 (later still) — the language can be changed

**337 tests passing.**

### Broke

- **The language was asked once and could not be changed.** No command, nothing
  in the copy saying it was changeable. An elder who mistapped the first button
  was stuck in the wrong language — and mistapping is exactly what this user
  does.
- **Changing it would have un-onboarded them.** `ob:lang:*` routed into
  `_welcome`, which sets `onboarding = 'consent'`. Someone who wanted English
  would have been sent back through the consent flow.
- **Command replies were still bilingual.** Onboarding stopped repeating itself
  on 2026-07-28; `/stop`, `/resume`, `/clear`, `/whatyouknow` and the delete
  confirmation did not.

### Fixed

`/language` — plus `bhasha`, `bhasha badlo`, "change language", "switch to
english", "english mein baat karo" — re-offers the same two buttons, and is
registered with WhatsApp so it shows in the `/` menu. The done-state guard stops
it restarting onboarding. Command replies localised through `CMD_COPY`.

### The pattern held again

The obvious phrasing `\b(english|hindi) mein baat kar` would also match "mera
beta english mein baat karta hai" — a fact about someone's son, which would have
silently switched the language. Tightened to imperative and desire forms only,
and there are tests for the three statement forms. PR-23 was the same mistake in
STOP, and it cost a user's reminders.

---

## 2026-07-28 (later) — a fired reminder can come back

**331 tests passing.**

### Broke

- **Acknowledgement never worked.** Not rarely — never. §15's acknowledgement
  rate was structurally zero. Four independent breaks, none of which raised:
  the template carried no per-message payload so a tap returned only its label;
  the arriving `button` message type was never read; the pipeline routed it to
  the model as text; and `handle_ack` updated `reminder_fires`, the table
  migration 006 stopped writing.
- **Nothing enqueued a nudge.** The handler was registered, tested and dead, so
  an unacknowledged reminder was never followed up.
- **Snooze did not snooze.** It marked the row and booked nothing — the user was
  told "later" by a system that then forgot.

### Fixed

`send_template(payloads=[...])`, `button_id` reading both shapes, the pipeline
treating `button` like `interactive`, `handle_ack` on `scheduled_turns` with the
pending nudge cancelled, snooze re-enqueuing, and a nudge booked at +20 min
dedupe-keyed on the origin turn. Replies localised now that language exists.

### Note

`tests/test_pipeline_order.py` contained a test asserting the **old** behaviour —
`reminder_fires` and `acked`. It was holding the bug in place. That is the fourth
time today a passing test agreed with a bug instead of catching it.

---

## 2026-07-28 — ask the language first, then say it once

**326 tests passing.**

### Broke

- **Every onboarding message was sent twice** — Hindi, then English, in one
  bubble. The welcome was **615 characters**. PRD §2 finds the barrier for this
  user is interface complexity, not device access, and the first thing a
  70-year-old reads while deciding whether to trust this was twice as long as it
  needed to be. Reported from a real handset.
- **The Hindi restart phrase did nothing.** The declined message tells a Hindi
  reader to type *"shuru karein"* — which matched no command. It had been broken
  the whole time and was hidden by the bilingual copy: the same message also said
  *"just say start"*, so an English-capable reader could recover. Making the copy
  single-language turned a soft failure into a dead end, for exactly the users
  this product exists for.

### Fixed

- Onboarding now asks the language first — the **only** bilingual message — then
  speaks one language throughout. Welcome is **299 chars in Hindi (51% shorter)**
  and **221 in English (64%)**.
- Copy moved into per-language tables (`COPY`, `BTN`) with `t()` / `b()` helpers
  that fall back rather than raise, so a missing key degrades to Hindi instead of
  breaking onboarding for a real user.
- `commands.py` START now matches `shuru`, `shuru karein`, `shuru karo`,
  `shuru kariye`. **Anchored, not substring** — PR-23 showed what substring
  matching costs, and `"reminder shuru kar do"` correctly still does not match.
- `consent_log.lang` records the language the consent was actually read in,
  instead of a hardcoded `'hi-en'`.
- `CONSENT_VERSION` → `2026-07-27.v2`, because the consent text changed.

### Tests

`tests/test_onboarding.py` 9 → 13. New: the first message asks only the language;
an English welcome carries no Hindi tail; the choice is stored; and — the one that
would have caught the dead end — **the declined message's restart phrase must
actually parse to a command.**

### Note

The Hindi is Latin-script, as it has always been. Whether an elder reads
Devanagari more comfortably than Latin-script Hindi is a real question this does
not answer, and worth deciding separately.

---

## 2026-07-27 (night) — the commands become visible

No Python changed. Meta-side configuration on `1266402176549539`.

`commands.py` has always parsed eight slash commands. **No user could discover
any of them** — there was no menu, and nothing in the copy mentioned them. They
are now registered with Meta, so typing `/` shows them. The handlers were already
written and tested; this only makes them findable.

Four ice breakers added, in Hinglish, emoji-free (the API rejects emoji):

    Dawa ka reminder lagaayein
    Is photo mein kya likha hai, bataayein
    Mere baare mein kya jaante hain
    Bas thodi baat karni hai

### Checked before configuring, not after

Every ice breaker was run through `commands.parse` and the safety classifier. An
ice breaker that accidentally matched `\bunsubscribe\b` or a self-harm trigger
would be a bad way to greet a first-time user, and STOP already matches
substrings — see PR-23.

That test also changed one of them. "Mere baare mein aapko kya yaad hai" routes
to the **model**; "Mere baare mein kya jaante hain" matches the deterministic
WHAT_YOU_KNOW handler. Asking what a system stores about you is a transparency
feature and should return the actual list, not a generated approximation.

### To test

Ice breakers only appear on a **fresh** thread. Clear All Messages, delete the
chat, then start a new one — see `docs/vendor/meta/conversational-components.md`.

Also from that doc, and now a standing constraint: **a `wa.me` link carrying
pre-filled text dismisses the ice breaker UI.** Ours has no `?text=`. Do not add
one.

---

## 2026-07-27 (night, later) — the assistant is called Indofolk AI

Operator decision: **Indofolk AI** is the name, in chat as well as on the WhatsApp
header. Until now a user saw three: "Indofolk AI" as the sender, "Main Saathi
hoon" in the greeting, and "Saathi" 32 times across the policy pages.

### Changed

- `onboarding.py` WELCOME and `identity.py`'s admission-control message — the
  first words an unknown number and a new user respectively ever read.
- `agent/prompt.py` SYSTEM — how the assistant refers to itself in every
  generated reply.

The Hindi keeps **saathi** as the common noun it actually is — *companion*:

    Namaste! 🙏 Main *Indofolk AI* hoon — aapki saathi.

A literal substitution would have produced "Main Indofolk AI hoon" alone, which
is a company introducing itself in the first person. Using the word for its
meaning rather than as a name keeps the warmth §2 argues for.

**Needs a native-speaker check before real users.** I am confident about the
English and not about the gender agreement in "aapki saathi".

### Deliberately unchanged

- **`metrics.py: NAMESPACE = "Saathi"`.** The IAM grant is conditioned on that
  namespace and both CloudWatch alarms query it. Renaming it would have silently
  broken the alerting proved working hours earlier — the metrics would publish to
  a namespace nothing watches, and `treat_missing_data: breaching` would then
  fire an alarm about a healthy worker.
- Repo, database, box, GCP project, `SAATHI_PREFIX_TOKEN_BUDGET`, the FastAPI
  title and the Wikipedia User-Agent. Internal identifiers no user sees; renaming
  them buys nothing and breaks infrastructure.

Prefix budget re-checked — still inside `SAATHI_PREFIX_TOKEN_BUDGET`.

---

## 2026-07-27 (night) — every outbound message is now recorded

**322 tests passing.**

### Broke

- **The first real user received five messages and none were recorded.** After a
  complete onboarding — consent, name, reminders, improvement — `messages` held
  5 inbound and **0 outbound**. Onboarding calls the transport directly, and only
  `pipeline` and the reminder worker remembered to insert afterwards.

  The sharp edge is consent. `users.consent_at` and `consent_version` said the
  user agreed; nothing recorded *what they were shown*. The text lived only in a
  source constant at some past commit, and `CONSENT_VERSION` is hardcoded in two
  modules (PR-18), so the drift compounds. `messages` is the record the 6-hourly
  backup actually protects, and the first exchange every user ever has was
  outside it.

### Fixed

- `wa/client._send` — the documented "single wire path" — now records every
  outbound message. Deliberately not fixed in `onboarding.py`: patching the one
  caller that forgot leaves the next one free to forget too. `kind`, `body_text`
  and `template_name` are derived from the wire payload rather than passed in, so
  a new send helper cannot skip it either.
- Recording never raises. The send already happened; failing the caller would
  invite a resend of something the user has read. Failures log at ERROR.

### Tests

`tests/test_outbound_record.py` (8). Seven exercise the recorder directly — and
would all stay green if the call were deleted from `_send`. The eighth drives the
wire path with a stubbed transport and fails if it stops recording. Verified by
removing the call: exactly that one goes red.

---

## 2026-07-27 (evening) — Saathi moves to an Indian number

No Python changed. Configuration and Meta-side state only, but it changes what
the product *is*: Saathi now answers on **+91 8071 581 944** as **"Indofolk AI"**,
not on a +1 Canadian number as an unnamed sender.

### Verified live

A real WhatsApp message reached the product end to end: inbound "Hii" at
04:41:50 → `POST /webhook/whatsapp` 200 → user row created → deterministic
onboarding replied with the bilingual consent prompt and three quick-replies,
rendered correctly on the handset. Worker heartbeat kept flowing across the
switch.

### Changed

- `WA_PHONE_NUMBER_ID` → `1266402176549539`, `WA_BUSINESS_ACCOUNT_ID` →
  `1687148075730227`, **in Secrets Manager** — editing `.env` alone would have
  been silently reverted by the next `saathi-env-sync`. Old ids retained as
  `*_OLD_CA` rather than dropped.
- Four templates re-submitted on the new WABA under the **same names**, so no
  code change: `turns.py` references them as string literals. All four came back
  `UTILITY`, not MARKETING — the anchoring wording from the first fight held.

### Found

- **Onboarding never records outbound messages** (PR-31). The first exchange
  every user has, including the consent text, is absent from `messages` — the
  table the backups actually protect. 1 inbound, 0 outbound after a conversation
  the user could see on screen.
- **Template quick-replies return button *text*, not a payload.** `reminder_fire_v2`
  carries `Ho gaya` / `15 min baad` as approved QUICK_REPLY buttons, so
  `pipeline.handle_ack` — which parses `ack:{id}` — can never match. That refines
  PR-4b: the fix is a `button` component with a dynamic payload, or matching on
  the text.
- Vobiz briefly held webhook access to every inbound message (PR-29), removed.

Decision recorded as **D-M**.

---

## 2026-07-27 (later still)

**314 tests passing.**

### Broke

- **A forwarded advert silently stopped someone's medication reminders.** No
  error, no bounce, nothing in the logs — the reminders just never arrived
  again. `commands` runs at priority 22, long before the agent, and matched on
  raw text without asking who wrote it. STOP matches `\bunsubscribe\b` as a
  *substring*, and nearly every forwarded marketing message carries that word in
  its footer. Matching set `users.paused = true`, and `worker/turns._handle`
  silently declines to send to a paused user. It needed no attacker — one
  relative forwarding a promo did it, and it persisted until the user happened
  to say "resume". Found by Codex's security scan (SEC-2); the `unsubscribe`
  substring and the reminder consequence were traced while fixing it.

### Fixed

- `saathi/capabilities.py` — the priority-22 matcher now requires `c.trusted`.
  The check lives in the *matcher*, not the handler: an unmatched capability
  falls through to the agent, which already fences relayed text and withholds
  mutating tools, so the safe behaviour is reused rather than reinvented.
  Relayed text is still read and explained — just never obeyed.
- Priorities 20/21 unchanged: they key on `button_id`, and a tap is first-party.
- Onboarding (10) deliberately **not** guarded — gating it would drop an
  un-onboarded user to the agent and break "onboarding never calls the model",
  which is what makes an open door safe.

### Tests

`tests/test_relayed_commands.py` (9). Verified they fail without the guard —
4 of the 9 go red when it is reverted, so they test the thing they claim to.

---

## 2026-07-27 (later)

Alerting built (PR-3). **305 tests passing.**

### Added

- `saathi/metrics.py` — CloudWatch publisher that never raises. A metrics outage
  must not stop a reminder going out, so `emit` swallows everything and returns
  a bool. It logs at ERROR rather than WARNING, because the heartbeat alarm
  treats missing data as breaching: when this module fails, the alarm starts
  lying, and whoever gets paged needs that line.
- `saathi/worker/__main__.py` — publishes `WorkerHeartbeat` and `TurnsDispatched`
  *after* a successful tick, so the signal means "the worker did its job", not
  "the process exists". Runs in a thread because boto3 is synchronous and
  blocking the loop delays every reminder in the batch.
- `ops/alerting/` — `saathi-alert` (OnFailure publisher), `saathi-metric` (one
  datapoint, for units that are not Python), the systemd template, and an
  idempotent `install.sh`.

### Learned

- **`OnFailure=` barely applies to `saathi-worker`.** It is `Restart=always`
  with `StartLimitBurst=5`, so a crashing worker re-enters `active`, not
  `failed`, and a crash-loop looks alive. The heartbeat alarm is what actually
  catches it. Discovered by reading the unit rather than assuming.
- **`%n` already includes `.service`.** `OnFailure=saathi-alert@%n.service`
  instantiates `saathi-alert@saathi-worker.service.service`. It resolves, but
  `%N` is the suffix-less form and is what you want.
- **A topic with no confirmed subscriber accepts publishes happily.**
  `NumberOfMessagesPublished` goes up, every call returns a MessageId, and
  nobody is told anything. Check `list-subscriptions-by-topic` for
  `PendingConfirmation` before believing alerting works.

### Tests

`tests/test_metrics.py` (4) — pins both directions of the failure mode: a
metrics outage never raises, and it is always logged at ERROR.

---

## 2026-07-27

Control plane adopted; the reminder delivery path fixed. **301 tests passing.**

### Broke

- **A reminder created through the assistant would never fire.** No error, no
  failed row, nothing in the logs — the reminder simply never arrived.
  `_create_reminder` inserted into `reminder_fires`; the worker
  (`worker/__main__.py`) claims only from `scheduled_turns`; and
  `worker/reminder_scheduler.py`, the one module that reads `reminder_fires`,
  is imported by nothing. Migration 006 moved the queue and back-filled the
  existing rows once, but the *creation* path was never moved with it. Latent
  rather than live only because no real reminder existed yet — both tables were
  empty. Found by reading the dispatch path end to end while opening PR-4.
- **A recurring reminder would have fired at most once.** Nothing walked the
  RRULE after the first occurrence. `turns.reminder` now books the next one,
  dedupe-keyed on (reminder, occurrence).
- **A turn claimed by a worker that then died was stranded forever.**
  `claim_due` marks `sent` and commits before the handler runs, so the row is
  never retried (claiming reads only `pending`) and never failed (nothing
  raised). `scheduling.sweep_stuck` reclaims them.
- **`sweep_stuck`'s SQL was invalid Postgres while its unit tests were green.**
  `set state = case ... end` yields `text`; the column is the `turn_state` enum.
  The fake connection accepted it happily. Caught only by running the statement
  against the real database. See `docs/LANDMINES.md`.

### Fixed

- `agent/tools/handlers.py` — `_create_reminder` enqueues onto `scheduled_turns`
  and no longer writes to `reminder_fires`. Registration is imported locally to
  break a cycle, and `enqueue` still refuses an unregistered kind loudly.
- `worker/turns.py` — recurrence rescheduling; a deliberate no-send (paused user
  or no active handle) is marked `skipped`, so the sweep can tell "chose not to
  send" from "the send died".
- `scheduling.py` — `sweep_stuck`, guarded on `wa_message_id is null` so a
  delivered reminder is never resent. `run_once` sweeps before it claims.
- `tests/test_scheduling.py` — the fake's `returning id` match was too broad and
  fed `sweep_stuck` a one-column row. Narrowed to INSERTs.

Tests: `tests/test_reminder_delivery.py` (7 new).

### Known still broken

- **The ack path is unreachable** — lane PR-4b. `wa.send_template` sends no
  button component, so the `ack:`/`snooze:` payloads `handle_ack` parses are
  never produced; `handle_ack` updates `reminder_fires`, which no longer
  receives fires; and nothing calls `enqueue(..., "nudge", ...)`. §15's
  acknowledgement metric is structurally zero, not low.
- Nothing pages a human when dispatch stops (PR-3, blocked on IAM).

---

## 2026-07-26

First working session. PRD → live webhook. **82 tests passing**, 11 commits.

### Added

- `db/schema.sql` — 11 tables. `sessions.window_expires_at` makes WhatsApp's
  24-hour window first-class; `reminders` (RRULE definition) is split from
  `reminder_fires` (queue rows) so ack/snooze/nudge is a state machine on one
  table. `bb16dba`
- `wa/window.py` — the 24-hour gate. `assert_can_send` refuses free-form outside
  the window rather than discovering it from Meta. `bb16dba`
- `worker/reminder_scheduler.py` — Postgres `SKIP LOCKED` queue, 30 s poll,
  claim-and-mark in one statement. `bb16dba`
- `agent/loop.py`, `agent/prompt.py`, `agent/tools/` — tool loop on `zai.glm-5`,
  prefix budget enforced in code. `54dfb16`
- `safety/classifier.py` — deterministic pre-LLM classifier, Hindi + English +
  Hinglish. `tests/test_safety.py`. `54dfb16`
- `speech/audio.py` — ffmpeg both directions. `54dfb16`
- `wa/client.py` — Cloud API; every outbound path funnels through `_send`, which
  calls the window guard first. `54dfb16`
- `memory.py` — facts, ASR entity-bias vocabulary, hard erasure. `1615eb1`
- `agent/stream.py` — ConverseStream; yields complete sentences so TTS can start
  on sentence one instead of queueing behind full generation. `1615eb1`
- Tools `what_you_know`, `forget_everything`, `set_preference`,
  `snooze_reminder`. `1615eb1`
- `speech/correct.py`, `speech/stt.py` — entity correction and Saaras.
  `tests/test_correct.py`. `7cecf59`
- `wa/templates.py`, `scripts/submit_templates.py` — templates as versioned code
  with a local validator. `869dbc1`
- `pipeline.py` — the inbound path end to end. `tests/test_pipeline_order.py`
  asserts the *ordering*, not just the outcome. `161f42a`
- `worker/send_reminder.py`, `worker/__main__.py` — reminders actually fire.
  `161f42a`

### Broke / Fixed

- **`/healthz` returned `AttributeError: module 'saathi.db' has no attribute
  'pool'`.** A `saathi/db/` package and a `saathi/db.py` module both existed; the
  package shadowed the module. Deleted the package — the schema lives in the
  top-level `db/`. `fc496cd`

- **Schema applied but every table was owned by `postgres`, leaving the app role
  unable to write.** Root cause was `psql: Permission denied` on
  `/home/ubuntu/...` (mode 0750) for the `postgres` user, and the obvious fix —
  run the whole file as `postgres` — silently produced the ownership problem.
  Split into `db/extensions.sql` (superuser, `pg_trgm` is untrusted) and
  `db/schema.sql` (run as the owner). `3598f70`

- **Sarvam rejected 2.5 seconds of audio with "exceeds the maximum limit of 30
  seconds".** ffmpeg cannot seek backwards on a pipe, so WAV written to stdout
  carries the `0xFFFFFFFF` streaming placeholder in both the RIFF and `data`
  length fields, and Sarvam read that as near-infinite. **Every inbound voice
  note would have failed in production while `ffmpeg -version` looked perfectly
  healthy.** Output now goes to a temp file so the header is patched.
  Regression test asserts the size fields are real. `0d382b9`

- **The entity-correction pass repaired nothing, ever, with no error.** Saaras
  `mode=codemix` — the PRD's recommended default — returns Devanagari, and the
  correction pass matches Latin tokens against the user's medicine names, so
  there was nothing to match. Default changed to `indic-en`; the same audio then
  gives `bomlodipin` → `Amlodipine`. `0d382b9`

- **The model published its chain of thought as the user-facing reply**, in
  English, and then failed to call the tool: *"Let me parse the time: • sawa
  aath = 8:15"*. Our own clock-word instructions had invited the narration.
  Prompt now forbids visible workings and requires acting over describing.
  `1615eb1`

- **`raat ko paune gyarah` resolved to 08:45 instead of 22:45** — a wrong dose
  time, the highest-severity failure this product has. Added explicit Hindi
  clock-word rules (`sawa` / `saade` / `paune` / `dedh` / `dhai` + part of day).
  Now 8/8 through the full stack. Notably the read-back rule had already caught
  it before it reached a reminder. `1615eb1`

- **Persona gender flipped between turns** — `rakhunga` then `rakhungi` then
  `jaanti hoon`. Disorienting for this audience specifically. Pinned female,
  with a test. `1615eb1`

- **Entity-bias vocabulary stored whole sentences.** `"Priya, Pune mein rehti
  hai"` is worthless as an ASR bias hint; `Priya` and `Pune` are the tokens that
  get mangled. Now extracts proper nouns. `1615eb1`

- **GLM-5 emits `**bold**` regardless of instruction** and WhatsApp renders it
  literally, so an elder sees asterisks. Stripped in code (`wa/format.py`)
  rather than asked for in the prompt — a deterministic transformation should
  not depend on instruction-following. `1615eb1`

- **The agent used the user's name and never stored it**, so a later session
  would not know who it was talking to. The name arrives free on every webhook
  in the contact profile; it simply never reached the prompt. Rendered as its
  own line rather than pushed into `facts`, because the user never asked us to
  remember it. `19d6ec9`

### Test-suite fixes (our tests were wrong, not the code)

- `test_fact_block_renders_and_is_capped` asserted 39 occurrences of `"\n- "`
  for 40 items. The header's trailing newline means all 40 match. `19d6ec9`
- `test_pipeline_order` fakes returned a 3-tuple for the users row after
  `upsert_user` began returning four. `19d6ec9`
- The Hinglish clock eval scored only whether a tool fired on turn 1, which
  **punished the product for confirming** — the read-back behaviour §6.3
  requires. Rewritten to answer the confirmation and score turn 2. Score went
  from 6/8 to 8/8 without touching product code. `0d382b9`

### Changed

- Default model `zai.glm-5`; prompt caching removed as a requirement — it does
  not exist for this model, so the cost lever is a tight prefix instead
  (`SAATHI_PREFIX_TOKEN_BUDGET`, measured ~1,330 of 3,000). See `DECISIONS.md`
  D-D.
- Template names are `reminder_fire_v2` / `reminder_nudge_v2`. The originals are
  burned: Meta holds a deleted template name for up to four weeks. `869dbc1`

---

## 2026-07-26 (later) — identity, channels, admission

**100 tests passing.** The system now has a user model rather than a phone
number, and WhatsApp is one transport rather than the architecture.

### Added

- `db/migrations/002_identity_and_channels.sql` — `user_channels`,
  `channel_link_codes`, `conversations`; `messages` gains `channel`,
  `conversation_id`, `deleted_at`, `redacted_at`. Existing users backfilled a
  verified primary WhatsApp handle.
- `identity.py` — resolve / revoke / link. **A phone number is not an identity**;
  it is a revocable claim on one. Dormant handles (60 d, inside India's ~90-day
  recycling window) return `needs_reverification` so a recycled number cannot
  inherit an elder's medicines, doctor and family.
- `channels/` — `Transport` protocol plus `Capabilities` as *data*
  (`has_session_window`, `max_quick_replies`, `supports_voice_notes`, `markup`).
  Channels differ in ways that change product behaviour, not just wire format —
  WhatsApp has a 24 h window and 3 buttons, Telegram has neither limit — so the
  pipeline asks the transport instead of branching on a channel name.
- `conversation.py` — threads, cross-channel history for prompt context, and
  message deletion. Redaction (`redacted_at`, content nulled, row kept) is
  distinct from erasure (hard delete), so acknowledgement rates and the safety
  audit trail stay honest when a user deletes a message.
- `db/migrations/003_admission_control.sql` + admission gate — **pattern taken
  from OpenClaw's `channels.<name>.dmPolicy: pairing | open`.**

### Changed

- `pipeline.handle_message` takes `channel` and resolves a `Transport`. All
  sends, media fetches and text formatting go through it. Session-window
  handling is now conditional on `capabilities.has_session_window`.
- The agent receives conversation history, so a turn is no longer stateless.

### Security

- **Admission control.** Previously *any* number that messaged us created an
  identity and got a full agent turn — an open cost vector (LLM + STT on our
  bill), a safety surface on an eldercare agent, and junk identities. Unknown
  handles are now `pending`: they get one rate-limited, bilingual, actionable
  reply and no model turn. Default policy is `pairing`, not `open`.

### Test-suite fixes (ours, not the code's)

- Fake cursor lacked `rowcount`; fake conn truncated captured SQL at 60 chars so
  redaction assertions could not see the clauses they were checking.
- Pipeline fakes still patched `pipeline.wa` and returned a 6-column handle row
  after the refactor added `status`.
- `Resolved` briefly had a defaulted field before a non-defaulted one.

---

## 2026-07-26 (evening) — architecture, capabilities, provenance

**224 tests passing.**

### Changed — capabilities register instead of branching

`handle_message` was an if/elif ladder growing a branch per feature. A capability
is now `(priority, matches, handle)` registered in `capabilities.py`, which read
top to bottom *is* the spec of the inbound path. Safety holds priority 0 and a
test asserts it cannot be overtaken; a handler that raises is logged and skipped
rather than killing the turn. Empty text now falls off the end of the chain
instead of needing its own branch.

### Added

- `vision.py` — medicine packs, letters, photos. `qwen.qwen3-vl-235b-a22b`,
  chosen because it is *regional* to ap-south-1: a photograph of a prescription
  must not leave India, and the Anthropic vision models here are global-only.
  Health-adjacent answers carry their disclaimer by construction.
- `documents.py` — PDF text layer first, rasterise page one as fallback.
- `onboarding.py` — deterministic, button-driven, **no model call**, which is
  what makes an open door safe.
- `commands.py` — stop/resume/help/what-you-know/clear/delete, model-free, so a
  DPDP erasure request works even when Bedrock does not.
- `net_policy.py` — SSRF blocking and secret redaction (ported MIT from
  OpenClaw). Root logger filter, so redaction does not depend on anyone
  remembering.
- `provenance.py` — forwarded messages, quoted replies and text lifted from
  media are `RELAYED`: content, never command. State-mutating tools are withheld
  for the turn. Withholding beats filtering because an absent capability does not
  care how the attack is phrased.

### Broke / Fixed

- Transport spy in the onboarding tests captured button **IDs** instead of
  labels, so a length assertion was checking the wrong strings.
- `band karo` did not match STOP: `\bband kar\b` requires a boundary that
  "karo" does not provide.
- `Resolved` briefly had a defaulted field before a non-defaulted one.
- Onboarding tests reached the real `send_buttons` because the spy only patched
  `send_text`, so the window guard raised on a fake connection.


OpenRouter workspace correction verified 2026-07-27: `OPENROUTER_WORKSPACE_ID` is set to `718e8438-6c5a-48f9-85c9-f8909f2e4c47`; all seven active Saathi keys list under that workspace with limit 5 and no reset; Default workspace lists no Saathi keys; account 1 completed a real OpenRouter turn returning `workspace route ok` with token usage.


Future provisioning guard: `openrouter.mint()` now raises `ProvisioningDisabled` if `OPENROUTER_WORKSPACE_ID` is unset, so a config drift cannot silently mint into OpenRouter Default again.

Future-signup guard: `openrouter.mint()` refuses to mint unless `OPENROUTER_WORKSPACE_ID` is set, and every create-key request includes that workspace id. Verified on-box after deploy.
