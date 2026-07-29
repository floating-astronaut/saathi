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

### Source rule before deploy

Deploy only merged `main`. Agent work starts on `agent/<task>` in a source
checkout, opens a GitHub PR, merges to `main` after the agent verifies the diff
and tests, and only then deploys. `/home/ubuntu/saathi` is the runtime artifact;
never use it as the source branch for a deploy.

**Two transports, one deploy.** Which one you use depends only on which box you
are sitting on. Everything that happens *on the target* is in
`ops/deploy_onbox.sh` and `ops/deploy_verify.sh`, and both transports run those
same two files — so "deployed" and "verified" mean the same thing either way.

From the **dev box** (us-east-2):

```bash
ops/deploy.sh              # package, migrate, test on the box, restart, verify
ops/deploy.sh --no-test    # skip the on-box test run
ops/deploy.sh --check      # verify only, change nothing
```

From the **runtime box itself** (this box), add `--local`:

```bash
ops/deploy.sh --local          # same deploy, no S3 and no SSM
ops/deploy.sh --local --check  # verify only; makes no AWS call at all
```

`--local` skips the tar/S3/presign/SSM transport and **nothing else**: same
clean-tree gate, same `uv sync`, same tests, same ledgered migrations with the
same abort semantics, same restart, same verification. It needs `sudo` (it drops
to `ubuntu` for anything touching the app or the database, exactly as the SSM
path does, because SSM also runs as root).

You do not choose the mode wrong twice: `--local` is checked against the
instance ID from IMDS and refuses if this is not `i-01b2c27883acb25ca`, and the
default transport refuses *on* the box rather than returning `AccessDenied:
ssm:SendCommand`, which reads like a broken setup and is not.

Both modes **refuse a dirty tree or a branch other than `main`**, because a
deploy that does not correspond to a commit cannot be reproduced or rolled back,
and nobody can tell afterwards what is actually running. `--local` additionally
refuses a source with no git remote naming saathi, and refuses to deploy
`/home/ubuntu/saathi` onto itself — see the warning below about the `.git` in
there.

Why an artifact at all, from the dev box: the box has **no SSH by design** (SSM
only), and every commit must be SSH-signed with a key that lives on the dev box.
Authoring on the box would mean copying that key onto a second machine or
committing unsigned. So the sequence is author and sign there, ship an artifact,
restart here.

Under the hood, remote: tar →
`s3://saathi-dev-artifacts-559896294326/saathi.tar.gz` → presigned GET fetched
over SSM → `ops/deploy_onbox.sh` from the unpacked artifact. Local: the same
staged tree, handed to the same script directly. Then, identically: snapshot →
install → migrations → `saathi-env-sync` → `uv sync` → tests → restart → verify.

Migrations are ledgered in `schema_migrations` and only applied once; anything
that fails there prints `MIGRATION ABORT` and stops the deploy **before** the
restart, so the services are never brought up against a schema they do not
match. A failing test run, a failed `uv sync`, a failed `saathi-env-sync` and a
failed `chown` now stop it in the same place, which they did not before
2026-07-27.

**The verification at the end can fail, and a failure means something specific.**
`ops/deploy_verify.sh` asserts rather than prints: every unit `active`, healthz
reporting `"ok":true`, no `traceback`/`critical` in the last 90 seconds; and
`deploy.sh` additionally asserts 200 through the tunnel and 403 on an unsigned
webhook. Any of those failing exits **1** with `VERIFY FAILED`.

That exit code **prevented nothing**. By the time verification runs, the deploy
has already installed, migrated and restarted — there is nothing left to stop.
Read it as "the box you just changed is not serving", not as "the deploy was
blocked". The response is to put the previous tree back, below.

### Putting the previous tree back

Every install first writes `/home/ubuntu/saathi.prev/<utc>.tar.gz` (0600, newest
three kept) and prints the restore command:

```bash
sudo tar xzf /home/ubuntu/saathi.prev/<utc>.tar.gz -C /home/ubuntu
sudo saathi-env-sync                       # .env is excluded from the snapshot
sudo systemctl restart saathi-web saathi-worker
```

**That is the code and only the code.** It does not undo a migration, and two of
them are backfills that cannot be undone. If the deploy that broke things also
migrated, read `PROD_READINESS.md` PR-35 before you restore.

### Rehearsing a deploy without deploying

```bash
ops/deploy.sh --local --target /tmp/rehearsal
```

A `--target` that is not `/home/ubuntu/saathi` is a **rehearsal**: real install,
real migrations against whatever `SAATHI_DB_DSN` that target's `.env` names, real
`uv sync`, real tests — but no `saathi-env-sync` and no restart, because those
two are global and would hit production from a scratch directory. That is bound
to the target, not to a flag, so there is no way to ask for a production deploy
that skips them. Point it at a scratch database, not the live one.

> **The `.git` inside `/home/ubuntu/saathi` is a stub. Ignore it.**
> Deploys unpack a tarball over the tree; nothing there ever pulls or commits.
> Its `.git` is three commits from before the application existed, with **no
> remotes**, and `git status` in that directory reports ~70 modified and
> untracked files that are simply the deployed code it has never heard of. It
> is not evidence of hand-edits, and it says `main` while being nothing of the
> kind. It cost a session an afternoon on 2026-07-27.
>
> To find out what is actually deployed, compare the tree to a commit — do not
> ask its `.git`:
>
> ```bash
> git -C ~/saathi-checkout archive <sha> | tar x -C /tmp/at-sha
> diff -rq --exclude=__pycache__ /tmp/at-sha/saathi /home/ubuntu/saathi/saathi
> ```
>
> Deleting the stub would be an improvement and nobody has, because nothing
> depends on it either. `ops/deploy.sh --local` refuses to treat it as a source.
>
> Same reason `evals/` exists there and in no commit: a deploy copies files in
> and never takes any out. See PR-36.
>
> **It is still where work gets lost.** On 2026-07-27 a session wrote two
> operator decisions (D-Q, D-R) and two vendor notes straight into that tree.
> Nothing there is under version control, and because a deploy *merges* rather
> than replaces, the next one would have overwritten them without a conflict, an
> error, or a diff. Recovered in `2a11443`. Edit the checkout, never `~/saathi`.

## Pushing to GitLab — "HTTP Basic: Access denied" with a valid token

`git push gitlab main` can fail with `HTTP Basic: Access denied` while
`glab auth status` reports a healthy login and `glab api user` succeeds. The
token is fine. The problem is the **username**: `glab auth login` stores an
OAuth token, and GitLab only accepts those over HTTPS with the literal username
`oauth2`, but glab's credential helper offers the account name instead. The
`glab auth git-credential: "erase" is an invalid operation` line printed
alongside is a symptom of the same helper, not the cause.

Push with the username corrected, taking the token from the helper so it is
never typed, echoed or stored anywhere new:

```bash
git -c credential.https://gitlab.com.helper= \
    -c credential.https://gitlab.com.helper='!f(){ [ "$1" = get ] || exit 0; echo username=oauth2; /usr/bin/glab auth git-credential get | grep "^password="; }; f' \
    push gitlab main
```

The empty first value is required: git *appends* helpers, so without it the
broken one still runs first. Making this permanent means the same two lines in
`git config --global`, which is worth doing and has not been done.

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

## In-region tracing (OBS-1)

### Units

- saathi-otelcol - OpenTelemetry Collector, listens on 127.0.0.1:4317 (gRPC).
  Receives spans from the web and worker processes and exports them to Jaeger
  on 127.0.0.1:4318.
- saathi-jaeger - Jaeger all-in-one. Badger storage at /opt/saathi-jaeger/data,
  7-day TTL, 4 GiB disk cap. OTLP gRPC on 127.0.0.1:4318; query UI on
  127.0.0.1:16686.

### Querying

From the Mac, open a tunnel then visit http://localhost:16686:
  ssh -L 16686:localhost:16686 saathi-ai

Select service "saathi" in the Jaeger UI. Spans appear as:
- pipeline.handle_message (root span per inbound WhatsApp message)
- safety.classify (deterministic pre-LLM check)
- agent.loop.run (the model turn)
- model.call (each Bedrock/OpenRouter call within a turn)
- tool_call (each tool the agent invokes)

### Enabling

Tracing is disabled by default. To enable:
  sudo sed -i "/Environment=/a Environment=SAATHI_TRACING_ENABLED=1" /etc/systemd/system/saathi-web.service
  sudo sed -i "/Environment=/a Environment=SAATHI_TRACING_ENABLED=1" /etc/systemd/system/saathi-worker.service
  sudo systemctl daemon-reload
  sudo systemctl restart saathi-web saathi-worker

### Troubleshooting

- No spans in Jaeger: journalctl -u saathi-otelcol -f and journalctl -u saathi-jaeger -f
- Disk usage: du -sh /opt/saathi-jaeger/data (capped at 4 GiB, 7-day TTL)
- Collector unreachable: app logs "tracing initialisation failed" and continues
