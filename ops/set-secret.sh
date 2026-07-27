#!/usr/bin/env bash
# Put one or more secrets into Secrets Manager, then sync them to .env.
#
#   ops/set-secret.sh WA_APP_ID WA_APP_SECRET
#
# Values are typed at a hidden prompt — never passed as arguments, because
# arguments land in shell history, in `ps` output, and (fatally) in SSM command
# text, which AWS retains and shows in the console forever. Nothing here echoes
# a value; the confirmation is length plus a SHA-256 prefix, which is enough to
# tell two secrets apart and useless to anyone reading over your shoulder.
#
# Writes to `saathi/dev/runtime`, which is where `saathi-env-sync` reads from.
# Editing .env directly would work until the next deploy overwrote it.
set -euo pipefail

SECRET_ID="saathi/dev/runtime"
REGION="ap-south-1"

[ $# -ge 1 ] || { echo "usage: $0 KEY [KEY...]" >&2; exit 2; }

for k in "$@"; do
    case "$k" in
        [A-Z_][A-Z0-9_]*) ;;
        *) echo "refusing key name $k — expected UPPER_SNAKE_CASE" >&2; exit 2 ;;
    esac
done

declare -A VALUES
for k in "$@"; do
    # -s: no echo. -r: a backslash in a token is a literal, not an escape.
    read -rsp "$k: " v; echo
    [ -n "$v" ] || { echo "empty value for $k — refusing" >&2; exit 1; }
    VALUES["$k"]="$v"
done

# Export for the child rather than interpolating into its source: a value with
# a quote or a backslash in it must not be able to change the program.
for k in "$@"; do export "SETSECRET_$k=${VALUES[$k]}"; done
export SETSECRET_KEYS="$*"

/home/ubuntu/saathi/.venv/bin/python - "$SECRET_ID" "$REGION" <<'PY'
import hashlib
import json
import os
import sys

import boto3

secret_id, region = sys.argv[1], sys.argv[2]
keys = os.environ["SETSECRET_KEYS"].split()

sm = boto3.client("secretsmanager", region_name=region)

# Read–merge–write, because PutSecretValue replaces the whole document. Getting
# this wrong does not corrupt one key, it erases every other credential the box
# runs on.
current = json.loads(sm.get_secret_value(SecretId=secret_id)["SecretString"])
before = set(current)

for k in keys:
    current[k] = os.environ[f"SETSECRET_{k}"]

missing = before - set(current)
if missing:                       # belt and braces; the merge above cannot drop keys
    sys.exit(f"refusing to write: would drop {sorted(missing)}")

try:
    sm.put_secret_value(SecretId=secret_id, SecretString=json.dumps(current))
except sm.exceptions.ClientError as exc:
    if "AccessDenied" in str(exc):
        sys.exit(
            "AccessDenied: this box may read the secret but not write it.\n"
            "Set the values from the dev box or the AWS console, then run\n"
            "saathi-env-sync here.")
    raise

print(f"wrote {len(keys)} key(s) to {secret_id}; "
      f"{len(before)} existing key(s) preserved")
for k in keys:
    v = current[k]
    digest = hashlib.sha256(v.encode()).hexdigest()[:12]
    print(f"  {k}: {len(v)} chars, sha256 {digest}…")
PY

echo
saathi-env-sync
echo
echo "Restart to pick them up:  sudo systemctl restart saathi-web saathi-worker"
