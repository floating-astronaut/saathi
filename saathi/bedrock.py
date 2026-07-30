"""One place that builds Bedrock runtime clients.

Every other AWS client in this codebase uses the ambient credential chain — on
the box, the instance role in account `635860424621`. Bedrock is the exception,
and only until MIGRATION-BEDROCK-1 in `docs/PROD_READINESS.md` closes: model
access has not been granted in that account, so inference borrows a profile into
`559896294326` via `SAATHI_BEDROCK_PROFILE`.

Keeping that borrowing here, rather than in `AWS_PROFILE` on the systemd unit, is
the whole point. Process-wide it also captured S3, Secrets Manager and
CloudWatch, which had already been repointed at the new account — so voice-note
uploads were authenticating as the old account against a new-account bucket and
getting AccessDenied. A credential that wide is not a setting, it is a leak.
"""
from __future__ import annotations

import logging

import boto3

from .config import settings

log = logging.getLogger("saathi.bedrock")

_session = None


def session():
    """The session Bedrock clients are built from.

    Three sources, most durable first:

      1. An explicit key pair. This is the intended path while
         MIGRATION-BEDROCK-1 is open: a Bedrock-invoke-only IAM user in the
         inference account, delivered through the runtime secret like every
         other credential, so a rebuilt box gets it from env-sync.
      2. A named profile, for a human debugging from a shell that already has
         one. Depends on `~/.aws/`, which nothing syncs — fine for a person,
         not something a service should need.
      3. The ambient chain — the instance role. Where this ends up once model
         access is granted in this account and the two settings above go away.

    Cached because resolving a profile reads (and may refresh) the SSO token
    cache on disk, which is not something to do on every turn.
    """
    global _session
    if _session is None:
        if settings.saathi_bedrock_access_key_id and settings.saathi_bedrock_secret_access_key:
            log.warning(
                "bedrock using a static key for a foreign account — "
                "MIGRATION-BEDROCK-1 is open; inference is not in this account"
            )
            _session = boto3.Session(
                aws_access_key_id=settings.saathi_bedrock_access_key_id,
                aws_secret_access_key=settings.saathi_bedrock_secret_access_key,
                region_name=settings.bedrock_region,
            )
        elif settings.saathi_bedrock_profile:
            log.warning(
                "bedrock using borrowed profile %r — MIGRATION-BEDROCK-1 is open; "
                "inference is not in this account",
                settings.saathi_bedrock_profile,
            )
            _session = boto3.Session(profile_name=settings.saathi_bedrock_profile)
        else:
            _session = boto3.Session()
    return _session


def runtime_client():
    """A `bedrock-runtime` client, regional to `bedrock_region`."""
    return session().client("bedrock-runtime", region_name=settings.bedrock_region)
