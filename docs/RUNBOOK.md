# Runbook

## Where things are

| | |
|---|---|
| AWS account | `559896294326` (Mesh Pilot Dev) |
| Region | **ap-south-1** (Mumbai) |
| Instance | `i-01b2c27883acb25ca` · t3.large · Ubuntu 26.04 · 60 GB gp3 encrypted |
| Elastic IP | `15.252.75.191` (`eipalloc-095dc7178aceb1f5c`) |
| Public URL | `https://saathi.n8nworld.store` |
| Security group | `sg-0f805961424175e66` (`saathi-dev`) — **one inbound rule**: TCP 22 from `207.219.25.137/32`, described *"operator Mac SSH dev only"*. It is the only SG on the instance. |
| Access | **SSM, plus SSH from the operator's Mac only.** Key `tejas-mac-saathi-ai` (ED25519, `SHA256:yvQAXHc7/QSKYDImQL8j0a5uG8n0aGZLJLcGpB102tg`) is the sole entry in `authorized_keys`. `passwordauthentication no`. |
| Repo on box | `/home/ubuntu/saathi` |
| Database | `saathi` on local Postgres 18.4, role `saathi` |
| Secrets | Secrets Manager `saathi/dev/runtime` (ap-south-1) |
| WhatsApp number | **+91 8071 581 944** — `phone_number_id 1266402176549539` |
| WABA | `1687148075730227` — display name **"Indofolk AI"**, currency **INR** |
| Business | `ayurpetofficial` (`935287898727459`) — legal entity **INDOFOLK WELLNESS PRIVATE LIMITED**, verified 19 Feb 2026, GSTIN `07AAHCI7432A1ZV` |
| Retired number | +1 437-539-7958 — `phone_number_id 1127963600410973`, WABA `1023945910495878`. Kept, not deleted; its four templates remain approved there. |

> **Re-verifying the Indian number.** It is a Vobiz DID and is **voice-only** —
> every Indian DID in their inventory has `sms: false`, so an SMS code never
> arrives. Use `code_method: VOICE`, and route the number somewhere audible
> first: attach it to a Vobiz XML application whose answer URL returns
> `<Response><Dial callerId="+918071581944"><Number>+91…</Number></Dial></Response>`.
> `callerId` **must** be a Vobiz-owned number or the outbound leg is refused.
> Detach the application afterwards — see `LANDMINES.md` on why deleting the
> answer URL alone does not stop it.
>
>     POST /v21.0/{phone_number_id}/request_code  {"code_method":"VOICE","language":"en"}
>     POST /v21.0/{phone_number_id}/verify_code   {"code":"NNNNNN"}
>     POST /v21.0/{phone_number_id}/register      {"messaging_product":"whatsapp","pin":"…"}
>
> The two-step PIN is `WA_TWO_STEP_PIN_IN` in Secrets Manager.

> **Two IP pins, both silent when they break.** The SSH rule is bound to the
> operator's Mac at `207.219.25.137/32`, and the Cloudflare token
> `saathi-box-canonical` is bound to the EIP `15.252.75.191/32` (PR-13). A
> residential IP reassignment locks you out of SSH; changing the EIP breaks the
> box's Cloudflare access. Neither announces itself — you find out when the
> thing you were about to do stops working.
| Tunnel | `saathi-dev` `d4e9e4ad-04ca-4ebf-92af-d39c7cb5f831` |
| Artifacts | `s3://saathi-dev-artifacts-559896294326` |

The us-east-2 MeshPilot box holds only a git checkout, used for SSH-signing and
pushing. It runs no Saathi service and has no Saathi database.

## Connect

```bash
aws ssm start-session --target i-01b2c27883acb25ca --profile mp-dev --region ap-south-1
```

## Services

```bash
systemctl status saathi-web saathi-worker cloudflared-saathi
journalctl -u saathi-worker -f
```

- `saathi-web` — uvicorn on `127.0.0.1:3130`
- `saathi-worker` — `python -m saathi.worker`, reminder scheduler, 30 s poll
- `cloudflared-saathi` — tunnel, token from `/etc/cloudflared-saathi.env` (0600)

## Deploy

```bash
ops/deploy.sh              # package, migrate, test on the box, restart, verify
ops/deploy.sh --no-test    # skip the on-box test run
ops/deploy.sh --check      # verify only, change nothing
```

It **refuses to deploy a dirty tree or a branch other than `main`**, because a
deploy that does not correspond to a commit cannot be reproduced or rolled back,
and nobody can tell afterwards what is actually running.

Why an artifact rather than editing on the box, or running an agent there: the
box has **no SSH by design** (SSM only), and every commit must be SSH-signed
with a key that lives on the dev box. Authoring on the box would mean copying
that key onto a second machine or committing unsigned. So the sequence is
author and sign here, ship an artifact, restart there.

Under the hood: tar → `s3://saathi-dev-artifacts-559896294326/saathi.tar.gz` →
presigned GET fetched over SSM → migrations → `saathi-env-sync` → `uv sync` →
tests → restart → verify.

## Secrets

Never put a secret in an SSM command — command text is retained and visible in
the console. Instead:

```bash
saathi-env-sync    # on the box; pulls saathi/dev/runtime into .env (0600)
```

The instance role `saathi-dev-box` has `GetSecretValue` on that ARN only, plus
`AmazonSSMManagedInstanceCore` and an inline `bedrock-invoke`.

**Do not add `EnvironmentFile=` to the unit files.** `config.py` loads `.env`
with `SettingsConfigDict(env_file=".env")`, reading it from disk into process
memory, so no secret ever enters `os.environ`. Measured 2026-07-27: the running
`saathi-web` process has 11 environment variables, all systemd boilerplate.

That matters because we spawn two subprocesses — `ffmpeg` (`speech/audio.py`)
and `pdftoppm` (`documents.py`) — which inherit the parent environment. Today
they inherit nothing worth having. Moving `.env` into the unit "so the service
reads config the normal way" would hand the Meta token and the database URL to
every transcode. If it ever does move, the subprocess calls need an explicit
scrubbed `env=` in the same change. See `PATTERNS_TO_BORROW.md`, hermes-agent.

## Verify (do all of these — "active" is not "working")

```bash
curl -s https://saathi.n8nworld.store/healthz            # 200 + pg version + model
systemctl is-active saathi-web saathi-worker cloudflared-saathi
journalctl -u saathi-worker --since "2 minutes ago"      # watch a real tick
```

Webhook, through Cloudflare rather than on the box — the two differ, and that
difference has hidden a real failure before (see `LANDMINES.md`):

- verify with the **correct** token → `200` echoing `hub.challenge`
- verify with a wrong token → `403`
- correctly signed POST → `200`
- unsigned or tampered POST → `403`

## Cloudflare

Box token `saathi-box-canonical` (`2e4050702dffa824858b899d28d324ab`), minted off
`CLOUDFLARE_MASTER_TOKEN` on the MeshPilot box, **IP-locked to
`15.252.75.191/32`**. Account: Pages, Workers, KV, R2, Tunnel, Stream, Workers
AI. All zones: DNS Write, Zone Read/Settings, Cache Purge, SSL, Workers Routes.

`saathi-zone-config` (`a03fb813b7c7d91fea7975742a4929de`) holds Config Settings
Write, which neither the canonical nor the master token has. It owns the config
rule disabling Browser Integrity Check for this hostname.

**If the EIP ever changes, the box token stops working** — it is IP-locked.

## Alerting

Two mechanisms, because neither sees the other's blind spot.

| | Catches | Blind to |
|---|---|---|
| `OnFailure=saathi-alert@%N.service` drop-ins | a unit entering `failed` | a timer that never fired; a unit that is `active` but wedged |
| CloudWatch alarms → SNS `saathi-alerts` | silence — no heartbeat, no backup | anything faster than the evaluation window |

    ops/alerting/install.sh          # idempotent; run as root on the box
    /usr/local/bin/saathi-alert      # OnFailure publisher
    /usr/local/bin/saathi-metric     # one-shot datapoint, for non-Python units

| Alarm | Fires when | Measured latency |
|---|---|---|
| `saathi-worker-heartbeat-missing` | no `Saathi/WorkerHeartbeat` for 2×300s | **~21 min**, not the 10 the config implies |
| `saathi-backup-stale` | no `Saathi/BackupSuccess` for 8×3600s | not separately measured |

**The heartbeat alarm takes ~21 minutes to fire, not 10.** Measured 2026-07-27:
worker stopped 01:44:05Z, alarm reached ALARM 02:04:59Z. CloudWatch will not
declare a period definitively empty until ingestion for it has settled, which
costs roughly an extra evaluation cycle beyond `Period × EvaluationPeriods`.
Quote the measured number, not the arithmetic one — and if 21 minutes is too
slow for a medication product, tune `Period` down and **re-measure**, because
the same overhead will apply to whatever you choose.

**Both alarms treat missing data as BREACHING.** If the metric pipeline itself
breaks, the alarm fires for a service that is actually healthy. That false alarm
is deliberate — an alarm that goes quiet when its own plumbing breaks is
indistinguishable from a healthy system, which is exactly how a dead worker goes
unnoticed for a week.

**`OnFailure` barely applies to `saathi-worker`.** It is `Restart=always` with
`StartLimitBurst=5`, so it re-enters `active` rather than `failed` on a crash,
and a crash-looping worker looks alive. The heartbeat alarm is what actually
catches that, because the heartbeat is published *after* a successful tick — it
means "the worker did its job", not "the process exists".

**Alerts carry no log content, on purpose.** `journalctl` output is redacted only
inside the Python entrypoints (`net_policy.RedactingFilter`); the backup script
and anything else under systemd are not. An alert is a summons — it names the
unit and the host, and the operator runs `journalctl` themselves.

Recipients are SNS email subscriptions on `arn:aws:sns:ap-south-1:559896294326:saathi-alerts`.
A subscription delivers nothing until the recipient clicks the confirmation
link, so **check `list-subscriptions-by-topic` for `PendingConfirmation` before
believing alerting works.**

## Known gaps

- No TTS yet; replies are text only (`PROD_READINESS.md` PR-8).
- Reminders dispatch and are swept, but acknowledgement is unreachable (PR-4b).
- Postgres is a single instance on the box. Backups are 6-hourly and **verified
  by restoring into a scratch database**, but recovery point is up to 6 hours
  and there is no PITR or failover (PR-7). Managed Postgres before paid users.
