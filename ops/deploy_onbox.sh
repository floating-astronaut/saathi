#!/usr/bin/env bash
# The on-box half of a deploy: everything that happens *on the ap-south-1 box*.
# Both transports run this one file, from the tree they are installing:
#
#   remote  ops/deploy.sh          dev box -> tar -> S3 -> SSM -> this script
#   local   ops/deploy.sh --local  runtime box -> sudo -> this script
#
# There is exactly one copy of the migration-ledger logic and it is below.
# Two copies would drift, and the copy that drifts is the one nobody tested.
#
# Runs as root: SSM runs commands as root, and local mode invokes it under
# sudo. It drops to `ubuntu` for anything that touches the app or the database.
#
#   deploy_onbox.sh --from STAGED_DIR [--repo DIR] [--no-test]
#
#     --from   a staged tree (no .git, no .venv, no .env) to install into --repo
#     --repo   where to install it; defaults to the canonical tree
#     --no-test  skip the on-box test run
#
# --repo anything other than the canonical tree is a REHEARSAL. saathi-env-sync
# and `systemctl restart` are global — they act on the real .env and the real
# units no matter which directory you point this at — so a rehearsal must not
# run them. That decision is bound to the target, not to a flag, so there is no
# way to ask for a production deploy that skips them.

set -uo pipefail

CANONICAL_REPO=/home/ubuntu/saathi
UNITS="saathi-web saathi-worker"

FROM=""
REPO="$CANONICAL_REPO"
RUN_TESTS=1

while [ $# -gt 0 ]; do
  case "$1" in
    --from)    FROM="${2:-}"; shift 2 ;;
    --repo)    REPO="${2:-}"; shift 2 ;;
    --no-test) RUN_TESTS=0; shift ;;
    *) echo "deploy_onbox: unknown argument: $1" >&2; exit 2 ;;
  esac
done

die() { echo "$*" >&2; exit 1; }

[ "$(id -u)" = "0" ] || die "deploy_onbox: must run as root (SSM does; local mode uses sudo)"
[ -n "$FROM" ] || die "deploy_onbox: --from is required"

FROM=$(cd "$FROM" 2>/dev/null && pwd -P) || die "deploy_onbox: --from is not a directory"
[ -n "${REPO:-}" ] || die "deploy_onbox: --repo cannot be empty"
REPO=$(cd "$REPO" 2>/dev/null && pwd -P) || die "deploy_onbox: --repo does not exist: install target must already be there"

# Copying a tree onto itself, or onto its own parent, destroys it halfway
# through and there is no useful error at the point it happens.
[ "$FROM" != "$REPO" ] || die "deploy_onbox: --from and --repo are the same directory ($FROM)"
case "$REPO/" in "$FROM"/*) die "deploy_onbox: --repo ($REPO) is inside --from ($FROM)" ;; esac
case "$FROM/" in "$REPO"/*) die "deploy_onbox: --from ($FROM) is inside --repo ($REPO)" ;; esac

# The migration section below is PR-25's, moved out of the SSM heredoc without
# a character changed, because it is the part that was verified against real
# Postgres across seven scenarios. It interpolates $REPO and $m into `su -
# ubuntu -c` strings unquoted. Rather than re-quote verified lines and lose that
# equivalence, refuse the input that would break them. Neither path can contain
# whitespace in practice; a rehearsal target under a temp directory could.
case "$REPO" in *[[:space:]\'\"\\]*) die "deploy_onbox: --repo path contains whitespace or a quote: $REPO" ;; esac
case "$FROM" in *[[:space:]\'\"\\]*) die "deploy_onbox: --from path contains whitespace or a quote: $FROM" ;; esac

REHEARSAL=0
[ "$REPO" = "$CANONICAL_REPO" ] || REHEARSAL=1

if [ "$REHEARSAL" = "1" ]; then
  echo "== REHEARSAL: target is $REPO, not $CANONICAL_REPO"
  echo "   saathi-env-sync and the restart of [$UNITS] will NOT run."
  echo "   Everything else — install, migrations, uv sync, tests — is real."
fi

# --- refuse to install an incomplete tree ------------------------------------
# The old script discovered this halfway through the migration loop, which sent
# the reader looking at the database when the artifact was the problem. Check
# before anything is overwritten.
for f in pyproject.toml uv.lock saathi db/migrations db/schema_migrations.sql \
         db/record_migration.sql ops/deploy_onbox.sh ops/deploy_verify.sh; do
  [ -e "$FROM/$f" ] || die "deploy_onbox ABORT: staged tree is missing $f — refusing to overwrite $REPO with it"
done

# --- snapshot the tree we are about to overwrite -----------------------------
# Code rollback only. It does NOT roll back migrations or data; there is no
# down-migration in this repo and inventing one here would be worse than
# saying so. See docs/PROD_READINESS.md PR-30.
#
# .env is excluded deliberately: a snapshot tarball is a file on disk that
# outlives the deploy, and the runtime secrets should not be sitting in one.
# saathi-env-sync rewrites .env from Secrets Manager anyway, so a restored tree
# is one `saathi-env-sync` away from complete.
SNAPDIR="$REPO.prev"
SNAP="$SNAPDIR/$(date -u +%Y%m%dT%H%M%SZ).tar.gz"
mkdir -p "$SNAPDIR" || die "deploy_onbox ABORT: cannot create $SNAPDIR"
chmod 700 "$SNAPDIR"
if ! tar czf "$SNAP" -C "$(dirname "$REPO")" \
        --exclude=.venv --exclude=.git --exclude=.env --exclude='.env.bak.*' \
        --exclude=__pycache__ --exclude=.pytest_cache \
        "$(basename "$REPO")"; then
  rm -f "$SNAP"
  die "deploy_onbox ABORT: could not snapshot $REPO — refusing to overwrite a tree we cannot put back"
fi
chmod 600 "$SNAP"
# Keep the newest three. Older ones are of no use: the migrations they matched
# have moved on.
ls -1t "$SNAPDIR"/*.tar.gz 2>/dev/null | tail -n +4 | xargs -r rm -f
echo "  snapshot $SNAP"

# --- install -----------------------------------------------------------------
# cp -r of the tree's *contents*, which merges: files deleted from the repo are
# not deleted here. That has always been true of this deploy (it is why an empty
# evals/ still exists on the box) and changing it is not this script's job.
if ! cp -r "$FROM/." "$REPO/"; then
  die "deploy_onbox ABORT: install failed; $REPO may be half-written. Restore: tar xzf $SNAP -C $(dirname "$REPO")"
fi
chown -R ubuntu:ubuntu "$REPO"

# --- migrations ---------------------------------------------------------------
DSN=$(grep -m1 '^SAATHI_DB_DSN=' "$REPO/.env" | cut -d= -f2-)
if [ -z "$DSN" ]; then
  echo "MIGRATION ABORT: no SAATHI_DB_DSN in $REPO/.env — refusing to guess a database"
  exit 1
fi

# -X on every psql below is load-bearing, not tidiness. su - ubuntu is a login
# shell, so psql would read ~ubuntu/.psqlrc, and the ledger read below is parsed
# on its field separator. A single pset of fieldsep or format in that file makes
# every version look unrecorded, so all six migrations re-apply and 003/005
# re-run their backfills — the exact corruption this loop exists to prevent.
# No such file exists on the box today; -X is what keeps that from mattering.

# The ledger, plus the one-time baseline of everything applied before it
# existed. Idempotent; see db/schema_migrations.sql for why it is not itself a
# migration.
if ! su - ubuntu -c "psql -X '$DSN' -q -v ON_ERROR_STOP=1 -f $REPO/db/schema_migrations.sql" 2>&1; then
  echo "MIGRATION ABORT: could not establish the schema_migrations ledger"
  exit 1
fi

# One read of the ledger: "version|checksum" per line, checksum empty when the
# row was baselined. Both fields are whitespace-free (a filename we control and
# a hex digest), which is what lets the word-split loop below work.
if ! APPLIED=$(su - ubuntu -c "psql -X '$DSN' -qtA -v ON_ERROR_STOP=1 -c 'select version, checksum from schema_migrations'"); then
  echo "MIGRATION ABORT: could not read schema_migrations"
  exit 1
fi

for m in $REPO/db/migrations/*.sql; do
  # An empty or missing db/migrations leaves the glob unexpanded. It already
  # fails safe — psql cannot open a file called '*.sql' — but says so as a
  # migration error, which sends the reader looking for the wrong thing.
  if [ ! -e "$m" ]; then
    echo "MIGRATION ABORT: no migration files at $REPO/db/migrations/*.sql —"
    echo "the artifact is incomplete, not the database. Services not restarted."
    exit 1
  fi
  b=$(basename "$m")
  sum=$(sha256sum "$m" | cut -d' ' -f1)
  if [ -z "$sum" ]; then
    echo "  migration $b: could not checksum the file"
    echo "MIGRATION ABORT: an empty checksum would be recorded as a string, not a"
    echo "NULL, and would read back for ever as an unverifiable baselined row."
    exit 1
  fi
  known=0; have=""
  for line in $APPLIED; do
    case "$line" in "$b|"*) known=1; have=${line#*|} ;; esac
  done
  if [ "$known" = "1" ]; then
    if [ -z "$have" ]; then
      echo "  migration $b already applied (baselined, checksum unknown)"
    elif [ "$have" = "$sum" ]; then
      echo "  migration $b already applied"
    else
      echo "  migration $b CHECKSUM MISMATCH"
      echo "    recorded $have"
      echo "    on disk  $sum"
      echo "  The file changed after it was applied, so the database is not what"
      echo "  db/migrations says it is. Write a new migration instead; if the edit"
      echo "  really was a no-op, update the recorded checksum by hand and say so."
      echo "MIGRATION ABORT: services not restarted"
      exit 1
    fi
    continue
  fi
  echo "  migration $b applying"
  if ! su - ubuntu -c "psql -X '$DSN' -q -v ON_ERROR_STOP=1 -f $m" 2>&1; then
    echo "  migration $b FAILED — psql error above"
    echo "MIGRATION ABORT: services not restarted; they would run against a schema"
    echo "they do not match. Fix the migration and redeploy."
    exit 1
  fi
  if ! su - ubuntu -c "psql -X '$DSN' -q -v ON_ERROR_STOP=1 -v ver=$b -v sum=$sum -f $REPO/db/record_migration.sql" 2>&1; then
    echo "  migration $b applied but NOT RECORDED — it will be attempted again"
    echo "MIGRATION ABORT: services not restarted"
    exit 1
  fi
  echo "  migration $b ok"
done

# --- secrets, dependencies, tests ---------------------------------------------
if [ "$REHEARSAL" = "1" ]; then
  echo "  REHEARSAL: skipping saathi-env-sync (it rewrites $CANONICAL_REPO/.env)"
else
  if ! saathi-env-sync; then
    echo "ABORT: saathi-env-sync failed — .env may be stale or partial, and a"
    echo "service restarted against it fails in ways that look like anything else."
    echo "Services not restarted."
    exit 1
  fi
fi

if ! su - ubuntu -c "cd $REPO && ~/.local/bin/uv sync --quiet --extra dev"; then
  echo "ABORT: uv sync failed — the venv does not match uv.lock. Services not"
  echo "restarted; they would import whatever happened to survive."
  exit 1
fi

if [ "$RUN_TESTS" = "1" ]; then
  # Not `| tail -2` on the su line: su runs a login shell without pipefail, so
  # the pipeline's status is tail's, and a red suite deployed silently. The log
  # goes to a file and only the tail is printed, which is all the old form was
  # really buying.
  TESTLOG=$(mktemp)
  if ! su - ubuntu -c "cd $REPO && ~/.local/bin/uv run pytest -q" >"$TESTLOG" 2>&1; then
    tail -30 "$TESTLOG"
    rm -f "$TESTLOG"
    echo "ABORT: tests failed on the box. Services not restarted."
    echo "Deploy anyway with --no-test only if you have read the failures above."
    exit 1
  fi
  tail -2 "$TESTLOG"
  rm -f "$TESTLOG"
fi

# --- restart -------------------------------------------------------------------
if [ "$REHEARSAL" = "1" ]; then
  echo "  REHEARSAL: not restarting [$UNITS]"
else
  if ! systemctl restart $UNITS; then
    echo "ABORT: systemctl restart failed. Restore the previous tree with:"
    echo "  sudo tar xzf $SNAP -C $(dirname "$REPO") && sudo saathi-env-sync && sudo systemctl restart $UNITS"
    exit 1
  fi
  sleep 9
fi

echo "  previous tree: tar xzf $SNAP -C $(dirname "$REPO")   (code only, not the database)"
