#!/usr/bin/env bash
# Deploy main to the ap-south-1 box. One command, same sequence every time.
#
# Why an artifact rather than editing on the box or running an agent there:
# the box has no SSH by design (SSM only), and every commit must be SSH-signed
# with a key that lives on the dev box. Authoring there would mean copying the
# signing key onto a second machine or committing unsigned. So: author and sign
# here, ship an artifact, restart there.
#
#   ops/deploy.sh              full deploy: sync, migrate, test, restart, verify
#   ops/deploy.sh --no-test    skip the on-box test run
#   ops/deploy.sh --check      verify only; change nothing
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTANCE=i-01b2c27883acb25ca
BUCKET=saathi-dev-artifacts-559896294326
REGION=ap-south-1
PROFILE=mp-dev
export AWS_PROFILE="$PROFILE" AWS_REGION="$REGION"

RUN_TESTS=1
CHECK_ONLY=0
for a in "$@"; do
  case "$a" in
    --no-test) RUN_TESTS=0 ;;
    --check)   CHECK_ONLY=1 ;;
    *) echo "unknown flag: $a" >&2; exit 2 ;;
  esac
done

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

ssm() {  # run a script on the box and stream back its output
  local script="$1" timeout="${2:-900}"
  local params
  params=$(python3 -c "
import json,sys
json.dump({'commands': open(sys.argv[1]).read().split(chr(10))}, sys.stdout)" "$script")
  local cid
  cid=$(aws ssm send-command --instance-ids "$INSTANCE" \
        --document-name AWS-RunShellScript --timeout-seconds "$timeout" \
        --parameters "$params" --query 'Command.CommandId' --output text)
  local st
  for _ in $(seq 1 90); do
    st=$(aws ssm get-command-invocation --command-id "$cid" \
         --instance-id "$INSTANCE" --query Status --output text 2>/dev/null || echo Pending)
    case "$st" in Success|Failed|TimedOut|Cancelled) break ;; esac
    sleep 6
  done
  aws ssm get-command-invocation --command-id "$cid" --instance-id "$INSTANCE" \
      --query StandardOutputContent --output text
  if [ "$st" != "Success" ]; then
    echo "--- stderr ---" >&2
    aws ssm get-command-invocation --command-id "$cid" --instance-id "$INSTANCE" \
        --query StandardErrorContent --output text >&2
    return 1
  fi
}

# --- refuse to deploy something that is not committed ------------------------
# A deploy that does not correspond to a commit cannot be reproduced or rolled
# back, and nobody can tell later what is actually running.
if [ "$CHECK_ONLY" -eq 0 ]; then
  cd "$REPO_DIR"
  if [ -n "$(git status --porcelain)" ]; then
    echo "refusing: working tree is dirty. Commit first — a deploy that does not" >&2
    echo "match a commit cannot be reproduced or rolled back." >&2
    git status --short >&2
    exit 1
  fi
  BRANCH=$(git rev-parse --abbrev-ref HEAD)
  [ "$BRANCH" = "main" ] || { echo "refusing: on '$BRANCH', not main" >&2; exit 1; }
  SHA=$(git rev-parse --short HEAD)
  say "deploying $SHA from main"
fi

if [ "$CHECK_ONLY" -eq 0 ]; then
  say "package + upload"
  TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
  cp -r "$REPO_DIR" "$TMP/saathi"
  rm -rf "$TMP/saathi/.git" "$TMP/saathi/.venv" "$TMP/saathi/.env" "$TMP"/saathi/.env.bak.*
  tar czf "$TMP/saathi.tar.gz" -C "$TMP" saathi
  aws s3 cp "$TMP/saathi.tar.gz" "s3://$BUCKET/saathi.tar.gz" --only-show-errors
  URL=$(aws s3 presign "s3://$BUCKET/saathi.tar.gz" --expires-in 1800)

  cat > "$TMP/remote.sh" <<REMOTE
set -uo pipefail
REPO=/home/ubuntu/saathi
rm -rf /tmp/s && mkdir -p /tmp/s
curl -fsSL -o /tmp/s/s.tgz "$URL" || { echo "FETCH FAILED"; exit 1; }
tar xzf /tmp/s/s.tgz -C /tmp/s && cp -r /tmp/s/saathi/. \$REPO/
chown -R ubuntu:ubuntu \$REPO
DSN=\$(grep -m1 '^SAATHI_DB_DSN=' \$REPO/.env | cut -d= -f2-)
if [ -z "\$DSN" ]; then
  echo "MIGRATION ABORT: no SAATHI_DB_DSN in \$REPO/.env — refusing to guess a database"
  exit 1
fi

# -X on every psql below is load-bearing, not tidiness. su - ubuntu is a login
# shell, so psql would read ~ubuntu/.psqlrc, and the ledger read below is parsed
# on its field separator. A single pset of fieldsep or format in that file makes
# every version look unrecorded, so all six migrations re-apply and 003/005
# re-run their backfills — the exact corruption this loop exists to prevent.
# No such file exists on the box today; -X is what keeps that from mattering.
# (No backticks in this heredoc, either: it is unquoted, so they would run.)

# The ledger, plus the one-time baseline of everything applied before it
# existed. Idempotent; see db/schema_migrations.sql for why it is not itself a
# migration.
if ! su - ubuntu -c "psql -X '\$DSN' -q -v ON_ERROR_STOP=1 -f \$REPO/db/schema_migrations.sql" 2>&1; then
  echo "MIGRATION ABORT: could not establish the schema_migrations ledger"
  exit 1
fi

# One read of the ledger: "version|checksum" per line, checksum empty when the
# row was baselined. Both fields are whitespace-free (a filename we control and
# a hex digest), which is what lets the word-split loop below work.
if ! APPLIED=\$(su - ubuntu -c "psql -X '\$DSN' -qtA -v ON_ERROR_STOP=1 -c 'select version, checksum from schema_migrations'"); then
  echo "MIGRATION ABORT: could not read schema_migrations"
  exit 1
fi

for m in \$REPO/db/migrations/*.sql; do
  # An empty or missing db/migrations leaves the glob unexpanded. It already
  # fails safe — psql cannot open a file called '*.sql' — but says so as a
  # migration error, which sends the reader looking for the wrong thing.
  if [ ! -e "\$m" ]; then
    echo "MIGRATION ABORT: no migration files at \$REPO/db/migrations/*.sql —"
    echo "the artifact is incomplete, not the database. Services not restarted."
    exit 1
  fi
  b=\$(basename "\$m")
  sum=\$(sha256sum "\$m" | cut -d' ' -f1)
  if [ -z "\$sum" ]; then
    echo "  migration \$b: could not checksum the file"
    echo "MIGRATION ABORT: an empty checksum would be recorded as a string, not a"
    echo "NULL, and would read back for ever as an unverifiable baselined row."
    exit 1
  fi
  known=0; have=""
  for line in \$APPLIED; do
    case "\$line" in "\$b|"*) known=1; have=\${line#*|} ;; esac
  done
  if [ "\$known" = "1" ]; then
    if [ -z "\$have" ]; then
      echo "  migration \$b already applied (baselined, checksum unknown)"
    elif [ "\$have" = "\$sum" ]; then
      echo "  migration \$b already applied"
    else
      echo "  migration \$b CHECKSUM MISMATCH"
      echo "    recorded \$have"
      echo "    on disk  \$sum"
      echo "  The file changed after it was applied, so the database is not what"
      echo "  db/migrations says it is. Write a new migration instead; if the edit"
      echo "  really was a no-op, update the recorded checksum by hand and say so."
      echo "MIGRATION ABORT: services not restarted"
      exit 1
    fi
    continue
  fi
  echo "  migration \$b applying"
  if ! su - ubuntu -c "psql -X '\$DSN' -q -v ON_ERROR_STOP=1 -f \$m" 2>&1; then
    echo "  migration \$b FAILED — psql error above"
    echo "MIGRATION ABORT: services not restarted; they would run against a schema"
    echo "they do not match. Fix the migration and redeploy."
    exit 1
  fi
  if ! su - ubuntu -c "psql -X '\$DSN' -q -v ON_ERROR_STOP=1 -v ver=\$b -v sum=\$sum -f \$REPO/db/record_migration.sql" 2>&1; then
    echo "  migration \$b applied but NOT RECORDED — it will be attempted again"
    echo "MIGRATION ABORT: services not restarted"
    exit 1
  fi
  echo "  migration \$b ok"
done
saathi-env-sync
su - ubuntu -c "cd \$REPO && ~/.local/bin/uv sync --quiet --extra dev"
if [ "$RUN_TESTS" = "1" ]; then
  su - ubuntu -c "cd \$REPO && ~/.local/bin/uv run pytest -q 2>&1 | tail -2"
fi
systemctl restart saathi-web saathi-worker
sleep 9
REMOTE
  say "sync, migrate, test, restart"
  ssm "$TMP/remote.sh"
fi

# --- verify: active is not the same as working -------------------------------
say "verify"
VERIFY=$(mktemp); trap 'rm -f "$VERIFY"' EXIT
cat > "$VERIFY" <<'REMOTE'
for u in saathi-web saathi-worker cloudflared-saathi postgresql; do
  printf '  %-20s %s\n' "$u" "$(systemctl is-active $u)"
done
echo -n "  healthz              "; curl -s --max-time 8 http://127.0.0.1:3130/healthz; echo
echo "  worker kinds         $(journalctl -u saathi-worker --since '90 seconds ago' --no-pager | grep -o "scheduled kinds:.*" | tail -1)"
ERR=$(journalctl -u saathi-web -u saathi-worker --since '90 seconds ago' --no-pager | grep -ciE 'traceback|critical' || true)
echo "  errors since restart $ERR"
REMOTE
ssm "$VERIFY" 300

say "public surfaces"
printf '  %-34s %s\n' "healthz (through tunnel)" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 https://saathi.n8nworld.store/healthz)"
printf '  %-34s %s\n' "webhook unsigned (want 403)" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -X POST https://saathi.n8nworld.store/webhook/whatsapp -d '{}')"
printf '  %-34s %s\n' "site" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 https://n8nworld.store/)"

say "done"
