# Runbook

## Where things are

| | |
|---|---|
| AWS account | `559896294326` (Mesh Pilot Dev) |
| Region | **ap-south-1** (Mumbai) |
| Instance | `i-01b2c27883acb25ca` · t3.large · Ubuntu 26.04 · 60 GB gp3 encrypted |
| Elastic IP | `15.252.75.191` (`eipalloc-095dc7178aceb1f5c`) |
| Public URL | `https://saathi.n8nworld.store` |
| Security group | `sg-0f805961424175e66` — **zero inbound rules** |
| Access | **SSM only.** No SSH key exists; port 22 was never opened. |
| Repo on box | `/home/ubuntu/saathi` |
| Database | `saathi` on local Postgres 18.4, role `saathi` |
| Secrets | Secrets Manager `saathi/dev/runtime` (ap-south-1) |
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

Code ships via S3 (there is no SSH key by design):

1. tar the repo, upload to `s3://saathi-dev-artifacts-559896294326/saathi.tar.gz`
2. presign a GET, fetch it on the box over SSM, extract to `/home/ubuntu/saathi`
3. `uv sync`
4. `systemctl restart saathi-web saathi-worker`

## Secrets

Never put a secret in an SSM command — command text is retained and visible in
the console. Instead:

```bash
saathi-env-sync    # on the box; pulls saathi/dev/runtime into .env (0600)
```

The instance role `saathi-dev-box` has `GetSecretValue` on that ARN only, plus
`AmazonSSMManagedInstanceCore` and an inline `bedrock-invoke`.

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

## Known gaps

- Postgres is on default local-only config with **no backup**. Must move to
  managed (RDS/Aurora ap-south-1) before external users.
- No TTS yet; replies are text only.
- No onboarding or consent flow yet.
