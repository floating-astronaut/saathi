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

    Cached, because resolving an SSO profile reads and may refresh the token
    cache on disk — not something to do on every turn.
    """
    global _session
    if _session is None:
        if settings.saathi_bedrock_profile:
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
