# Meta Conversions API Gateway — status and design

> **State (2026-07-30): built and wired for CTWA attribution (CAPI-1).** Saathi now
> captures the `ctwa_clid` and reports a `LeadSubmitted` on onboarding completion —
> `saathi/capi.py`, migration 016, call sites in `pipeline.py` and `onboarding.py`.
> The design below is what shipped. Enabled by setting `SAATHI_CAPI_DATASET_ID`
> (dataset `2038444060213473`, owner Indofolk). Boundary: D-AD.
>
> **The Cloud Run Gateway was torn down on 2026-07-30** — it was a web-pixel path
> this CTWA flow never used. Deleted from GCP project `saathi-ai-503623`: both
> Cloud Run services (`gc05b56ab51771-capig`, `-hub`), the
> `gc05b56ab51771-storage-bucket` (which also held stray `capig-restore-key-*`
> secret files), and the two installer service accounts. Verified gone via the
> Run and Storage APIs. This was infrastructure deletion, so it is recorded here
> rather than in code. One residue only GCP-side cleanup cannot reach: Meta's
> Events Manager still shows a stale "installed" gateway record — clear it there
> when convenient. The sections below are kept as the description of what existed.
>
> Live evidence: a probe with the exact event payload was accepted by the dataset on
> every field (endpoint, token, `action_source`, `messaging_channel`, `user_data`
> shape) and rejected *only* a synthetic `ctwa_clid` with `"Messaging Event Invalid
> Ctwa Clid"` — the wiring is correct; only a real ad click's id is needed.

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

## The actual goal: Click-to-WhatsApp (CTWA) attribution

Clarified by the operator: the point of all this is **WhatsApp attribution** —
knowing which Meta ad drove a person into a WhatsApp conversation and eventually to
convert. That is a specific, documented Meta flow, and it changes the design away
from a generic web-pixel Gateway.

**How CTWA attribution works** (Meta docs, verified 2026-07-30):
1. A person taps a Facebook/Instagram *Ads that click to WhatsApp* creative and
   lands in a chat with the business number.
2. Their **first inbound message** carries a `referral` object, and inside it a
   **`ctwa_clid`** — the click-to-WhatsApp click ID that ties this conversation to
   that ad click.
3. When the person converts, you send a **Conversions API event** carrying that
   `ctwa_clid`, and Meta attributes the conversion back to the ad.

Saathi already receives step 2's payload — `pipeline.extract_messages` yields the
whole message dict, so `msg["referral"]["ctwa_clid"]` is *present and simply never
read*. Nothing captures it; there is no column to store it and no code to send it.
That is the entire gap.

### Two models — and the difference is a privacy decision, not a technical one

Meta offers two ways to produce the conversion event:

- **A · Automatic Events API.** You opt in ("Instruct Meta to automatically identify
  order and lead events"), and **Meta runs regex + natural-language processing over
  the customer's WhatsApp message threads** to decide when a lead or purchase
  happened, then fires an `automatic_events` webhook you can forward to CAPI. For an
  elder-privacy product this means **letting Meta analyse elders' conversations** —
  a real concession, and one this product exists to avoid.
- **B · Manual Conversions API (recommended).** Saathi captures `ctwa_clid` on first
  contact, decides its *own* conversion signal — onboarding completion — and sends
  one event. **Meta never sees message content.** What leaves the box is the click
  ID Meta itself minted, an event name, and a timestamp. No elder PII, no thread.

Model B is the fit. It keeps the boundary intact and is simpler. The recommendation
is to **turn the Automatic Events opt-in OFF** in Business Suite (Settings →
WhatsApp accounts → Privacy and data sharing) so Meta is not analysing threads, and
send our own events.

### The event, exactly (Meta CAPI for business messaging)

```
POST https://graph.facebook.com/v21.0/{DATASET_ID}/events?access_token={SYSTEM_USER_TOKEN}
{
  "data": [{
    "event_name": "LeadSubmitted",           // our signal = onboarding complete
    "event_time": <unix seconds>,
    "action_source": "business_messaging",    // required for WhatsApp
    "messaging_channel": "whatsapp",          // required
    "user_data": {
      "whatsapp_business_account_id": "<WA_BUSINESS_ACCOUNT_ID>",  // already in the secret
      "ctwa_clid": "<captured from the inbound referral>"
    }
  }]
}
```

Note what is **absent**: no phone number, no email, no hashed PII. With CTWA the
`ctwa_clid` is the match key, so attribution needs nothing about the elder at all —
which is exactly why this is the model to use.

### The Gateway you deployed is probably not needed for this

A CAPI Gateway is a web-pixel appliance — a self-hosted relay for browser/website
events. **CTWA business-messaging events go directly to the dataset endpoint above**
with the system-user token, which Saathi already holds (`WA_ACCESS_TOKEN` /
`META_SYSTEM_USER_TOKEN`, both carry `ads_management`). So the Cloud Run Gateway and
its GCS bucket add infrastructure and cost without being on this path. Decide
whether to keep the Gateway for a future web funnel or **tear it down** — it has
billed since 2026-07-27 for a flow that does not use it.

Sources: [CAPI for Business Messaging](https://developers.facebook.com/docs/marketing-api/conversions-api/business-messaging/),
[Automatic Events API](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/automatic-events-api),
[Ads that click to WhatsApp](https://developers.facebook.com/docs/marketing-api/ad-creative/messaging-ads/click-to-whatsapp/).

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

Almost everything is already in hand. What is **not**:

- **Confirm Model B** (send our own events; Automatic-Events opt-in OFF). Default
  unless you say otherwise.
- **The dataset ID.** The one identifier we do not have — from Meta Events Manager,
  the dataset connected to the WhatsApp Business Account. (Not a pixel URL, not a
  Gateway URL.)

Already available, no action needed: the system-user token (`WA_ACCESS_TOKEN`, has
`ads_management`), the WhatsApp Business Account ID (`WA_BUSINESS_ACCOUNT_ID` in the
secret), and the `ctwa_clid` itself (arrives in the inbound webhook — we just start
reading it).

## The shape once unblocked (design, not yet built)

Two small pieces, both on this box:

1. **Capture.** In `saathi/pipeline.py`, on a message whose `referral.ctwa_clid` is
   present, persist the click id against the account — a `ctwa_clid` (+ captured-at)
   column on `accounts`, or a tiny `ctwa_attribution` table. Written once, on the
   first ad-originated message; never overwritten by a later organic message.
2. **Convert.** A `saathi/capi.py` that, on **onboarding completion**
   (`saathi/onboarding.py`), POSTs one `LeadSubmitted` event to
   `graph.facebook.com/v21.0/{DATASET_ID}/events` with the stored `ctwa_clid`.
   Fire-and-forget with `metrics.py`'s discipline: **it never raises into a turn**,
   and it carries no message content by construction — the payload has room only for
   the click id, event name and time. Skipped cleanly when there is no `ctwa_clid`
   (organic signups) or no `DATASET_ID` configured.

Config via the runtime secret: `SAATHI_CAPI_DATASET_ID`; the token and WABA id are
already there. Absent `DATASET_ID` → no-op, exactly like `saathi_audio_bucket == ""`
disables media capture. `tests/test_capi.py` asserts the payload never contains
message/turn content and that a Graph outage does not raise.

Neither the GCP SA, the bucket, nor the Cloud Run Gateway appears in this path.
They belong to a web-pixel flow this attribution does not use.

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
