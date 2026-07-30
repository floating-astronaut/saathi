# Meta Conversions API Gateway — status and design

> **State: infrastructure up, app disconnected.** A Meta Conversions API Gateway
> is deployed and healthy, but no Saathi code sends it events. This doc exists
> because the missing piece is a *contract* (which events, whose data, to which
> pixel) and the rules say the contract is written before the code. It touches
> privacy and third-party data egress, so it does not get built on a guess.

## What was found (verified 2026-07-30, not assumed)

Someone stood up the raw pieces in the Meta and GCP consoles on 2026-07-27 and
reported "nothing is binded, no events dispatching." That is half true — nothing
dispatches, but the infrastructure is not raw, it is **live**:

- **The Gateway is deployed and healthy.** `app_status.json` in the bucket is the
  installer's own log: Conversions API Gateway **v2.7.0**, Terraform applied and
  **Cloud Run health checks passed at 2026-07-27 18:50:41 UTC**, `messages: []`
  (no errors). It has been running on Cloud Run in GCP project
  `saathi-ai-503623` since then.
- **The bucket is the Gateway's install/backup store, not an event drop-box.**
  `gc05b56ab51771-storage-bucket` (project `saathi-ai-503623`, location
  **ASIA-EAST1** — Taiwan, *not* India) holds `terraform/`, `install/startup.sh`,
  `cloud-init-output.log`, `capig-backup-{44,46}.txt` and
  `capig-restore-key-{44,46}.txt` (Gateway config backups + their restore keys —
  **secrets, left untouched**), and `app_status.json`.
- **The GCP service account can read and write the bucket.**
  `gcp-satthi-ai@saathi-ai-503623.iam.gserviceaccount.com` (from
  `saathi/dev/gcp-sa`) — probe write returned HTTP 200, delete 204.
- **The Meta token can control a pixel/dataset.** `META_SYSTEM_USER_TOKEN` (and,
  notably, `WA_ACCESS_TOKEN` too) is a `SYSTEM_USER` token, valid, `expires_at: 0`
  (never), carrying `ads_management`, `ads_read`, `business_management`,
  `catalog_management`.

So every ingredient the phrase "use the meta token for pixel control and the gcp
SA for the bucket" refers to is present and working. **The only thing absent is a
Saathi-side event source** — there is no code, anywhere in the app, that emits a
conversion event to anything.

## What a CAPI Gateway actually is

It is a self-hosted appliance Meta ships as Terraform. It exposes an endpoint that
speaks the Graph `/events` shape; your server POSTs events to *it*, and it forwards
them to Meta's Conversions API using the pixel/dataset and token configured inside
it at install time. The value over calling Meta directly is that the Gateway does
the batching, ret/dedup and event-matching, and keeps the long-lived Meta token on
the Gateway rather than in every caller.

Consequence for us: Saathi does **not** need the Meta token to send events — it
needs the **Gateway's URL**, the **pixel/dataset ID**, and the Gateway's own access
token. The `ads_management` token matters only for *managing* the pixel, not for
sending events through the Gateway.

## The decision that gates the code — do not skip this

This is an **elder-facing, privacy-first product that never transacts**
(`docs/DECISIONS.md`, PRD §12). A conversions pipeline sends "this person did X" to
Meta's advertising graph. Before any event is wired, one question must be answered
by the operator, not inferred:

**Whose data, and which events?**

1. **Marketing funnel only (recommended).** The only events are acquisition
   signals — e.g. a family completing onboarding becomes a `Lead` /
   `CompleteRegistration` — sent so Meta can attribute and optimise the ads that
   brought them. What leaves the box is a hashed identifier + an event name.
   **No elder chat, health, voice, reminder or message content is ever involved.**
   This is defensible and is the assumption the rest of this doc is written under,
   *pending confirmation*.
2. **Elder-side activity events.** Sending in-app behaviour to Meta. This routes
   vulnerable users' activity into an ad graph and collides head-on with the
   privacy boundary. It would need an explicit `docs/DECISIONS.md` entry and is
   **not** to be built without one.

Either way this is third-party data egress and warrants a `DECISIONS.md` entry and
a line in the privacy policy. Under option 1 the egress is about *prospects who
chose to sign up*, which is ordinary marketing attribution; under option 2 it is
about *the elders themselves*, which is a different product.

## What "finished" needs from the operator

Blocking, and only the operator has them:

- **The decision above** (option 1 unless stated otherwise).
- **The Gateway endpoint URL** — the Cloud Run service URL from the CAPIG console.
  A storage-scoped SA cannot read it; one click in the console can.
- **The pixel / dataset ID** the Gateway forwards to.
- **The Gateway access token** it expects on inbound events (a Gateway-issued
  value, distinct from the Meta system-user token).

## The shape once unblocked (design, not yet built)

Runs on this box, matching how the operator scoped it:

- A `saathi/capi.py` that, given an event name + a hashed identifier, POSTs to the
  Gateway endpoint. Fire-and-forget with the same discipline as `metrics.py`:
  **publishing must never raise into a user turn**, and it carries no message
  content by construction — the function's signature simply has nowhere to put it.
- The single call site under option 1 is onboarding completion in
  `saathi/onboarding.py` — one `CompleteRegistration` per newly onboarded account,
  keyed by a hash of the phone number, nothing else.
- Config via the runtime secret: `SAATHI_CAPI_GATEWAY_URL`,
  `SAATHI_CAPI_PIXEL_ID`, `SAATHI_CAPI_ACCESS_TOKEN`. Absent config → the module is
  a no-op, exactly like `saathi_audio_bucket == ""` disables media capture.
- A `tests/test_capi.py` asserting the payload never contains message/turn content
  and that a Gateway outage does not raise.

The GCP SA and bucket do not appear in this path at all: the bucket is the
Gateway's own storage, and Saathi talks to the Gateway over HTTPS, not through GCS.
The SA's only ongoing relevance is operational (backups/restore of the Gateway),
not part of the event flow.

## Open operational notes (not this lane's job, but spotted)

- **The Gateway's Cloud Run service has been running since 2026-07-27** and is
  billable GCP compute in `saathi-ai-503623`. If the funnel decision stalls, decide
  whether to leave it running or tear it down — it is not free while idle.
- **`WA_ACCESS_TOKEN` carries `ads_management`/`business_management`/
  `catalog_management`.** The WhatsApp messaging path needs none of those; a leak
  of that token could manage ads and catalogs. Worth minting a messaging-scoped
  token separately. Tracked outside this lane.
- The bucket lives in **ASIA-EAST1 (Taiwan)**, outside the India-residency posture
  the rest of the system holds to. Acceptable for Gateway install artifacts;
  noted so it is a conscious exception, not a silent one.
