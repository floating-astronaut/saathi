#!/usr/bin/env bash
# Deploy main to the ap-south-1 box. One command, same sequence every time.
#
# Two transports, one deploy. Everything that happens *on the box* lives in
# ops/deploy_onbox.sh and ops/deploy_verify.sh, and both transports run those
# same two files. This script only decides how the tree gets there.
#
#   remote (default) — from the dev box, over S3 + SSM. Why an artifact rather
#     than editing on the box: the box has no SSH by design (SSM only), and
#     every commit must be SSH-signed with a key that lives on the dev box.
#     Authoring there would mean copying the signing key onto a second machine
#     or committing unsigned. So: author and sign there, ship an artifact.
#
#   --local — from the runtime box itself, for the session that is already
#     standing on the target. It skips the tar/S3/presign/SSM transport and
#     nothing else. It does not skip the clean-tree gate, dependency sync, the
#     tests, the migrations, the restart or the verification, because those are
#     the deploy.
#
#   ops/deploy.sh                  remote: sync, migrate, test, restart, verify
#   ops/deploy.sh --no-test        skip the on-box test run
#   ops/deploy.sh --check          verify only; change nothing
#   ops/deploy.sh --local          the same deploy, run on the box
#   ops/deploy.sh --local --check  verify only, and no AWS call at all
#   ops/deploy.sh --local --target DIR
#                                  rehearsal against a scratch tree: real
#                                  install, migrations, uv sync and tests, but
#                                  no env-sync and no restart. See
#                                  ops/deploy_onbox.sh for why that is bound to
#                                  the target rather than to a flag.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
INSTANCE=i-03a4911f2f7de793d
BUCKET=saathi-dev-artifacts-635860424621
REGION=ap-south-1
PROFILE=mcc-dev
CANONICAL_REPO=/home/ubuntu/saathi

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { echo "$*" >&2; exit 1; }

RUN_TESTS=1
CHECK_ONLY=0
LOCAL=0
TARGET=""
# `shift 2` on a flag given last shifts nothing. Here `set -e` would end the run
# rather than spin, but silently and with no message, which is the same failure
# to say what is wrong. Check the value is present before consuming it.
need_value() { [ "$1" -ge 2 ] || die "$2 needs a value"; }
while [ $# -gt 0 ]; do
  case "$1" in
    --no-test) RUN_TESTS=0; shift ;;
    --check)   CHECK_ONLY=1; shift ;;
    --local)   LOCAL=1; shift ;;
    --target)  need_value $# --target; TARGET="$2"; shift 2 ;;
    *) echo "unknown flag: $1" >&2; exit 2 ;;
  esac
done

# --- which box am I on? ------------------------------------------------------
# The mode is an explicit flag, not a guess — but the flag is checked against
# the box, and a disagreement stops the deploy. Both wrong directions cost
# somebody an afternoon:
#
#   remote mode on the runtime box — "AccessDenied: ssm:SendCommand", which
#     reads as a broken setup rather than as "you are standing on the target".
#   local mode on the dev box — would install the tree over a checkout that is
#     not the runtime tree and restart units that do not exist there.
#
# So `--local` needs *positive* identification. An unreadable instance ID is
# not permission to continue; only the affirmative claim has to be proved.
#
# Retried once. Failing closed is right, but the moment --local matters most is
# an incident, and one blip on the token PUT should not turn "deploy the fix"
# into "refusing --local".
imds_once() {
  local tok
  tok=$(curl -sS -m 3 -X PUT http://169.254.169.254/latest/api/token \
          -H 'X-aws-ec2-metadata-token-ttl-seconds: 60' 2>/dev/null) || return 1
  [ -n "$tok" ] || return 1
  curl -sS -m 3 -H "X-aws-ec2-metadata-token: $tok" \
       http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null
}
this_instance() {
  local id
  id=$(imds_once) && [ -n "$id" ] && { printf '%s' "$id"; return 0; }
  sleep 2
  id=$(imds_once) && [ -n "$id" ] && { printf '%s' "$id"; return 0; }
  return 1
}
IID=$(this_instance || true)

if [ "$LOCAL" -eq 1 ]; then
  if [ "$IID" != "$INSTANCE" ]; then
    echo "refusing --local: this box is not the deploy target." >&2
    echo "  target:   $INSTANCE" >&2
    echo "  this box: ${IID:-<instance id unreadable>}" >&2
    echo "--local installs a tree into $CANONICAL_REPO and restarts saathi-web" >&2
    echo "and saathi-worker. It has to be certain where it is; it is not." >&2
    exit 1
  fi
else
  if [ "$IID" = "$INSTANCE" ]; then
    echo "refusing: you are on the deploy target ($INSTANCE), and the default" >&2
    echo "transport reaches it over SSM from the dev box. The instance role" >&2
    echo "saathi-dev-box is denied ssm:SendCommand and there is no '$PROFILE'" >&2
    echo "profile here, so this would fail with an IAM error that says nothing" >&2
    echo "about the real problem." >&2
    echo "Use:  ops/deploy.sh --local" >&2
    exit 1
  fi
  export AWS_PROFILE="$PROFILE" AWS_REGION="$REGION"
fi

[ -z "$TARGET" ] || [ "$LOCAL" -eq 1 ] || die "--target only means anything with --local"
[ -z "$TARGET" ] || [ "$CHECK_ONLY" -eq 0 ] || die \
"--check and --target contradict each other: --check installs nothing, so there
is no target to install into. It verifies the box that is running."

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

on_box() {  # run a script on the box, from whichever side of the wire we are
  local script="$1" timeout="${2:-900}"
  if [ "$LOCAL" -eq 1 ]; then
    sudo bash "$script"
  else
    ssm "$script" "$timeout"
  fi
}

# --- refuse to deploy something that is not committed ------------------------
# A deploy that does not correspond to a commit cannot be reproduced or rolled
# back, and nobody can tell later what is actually running.
#
# Remote mode gets this cheaply: the artifact is built from a clean checkout on
# the dev box. Local mode has no artifact and no build step, so the same
# guarantee has to be asserted here — otherwise "deploy from the box" quietly
# becomes "copy whatever is in this directory onto a live elder-care service",
# which is the hand-rolling this lane exists to end. Local mode is therefore
# gated by everything remote mode is gated by, plus two checks that only it
# needs. It deploys the checkout that contains the deploy.sh you invoked; there
# is deliberately no flag for pointing it at some other directory.
VERIFY_SCRIPT="$REPO_DIR/ops/deploy_verify.sh"

if [ "$CHECK_ONLY" -eq 0 ]; then
  cd "$REPO_DIR"
  git rev-parse --git-dir >/dev/null 2>&1 \
    || die "refusing: $REPO_DIR is not a git checkout, so there is no commit to deploy."
  if [ -n "$(git status --porcelain)" ]; then
    echo "refusing: working tree is dirty. Commit first — a deploy that does not" >&2
    echo "match a commit cannot be reproduced or rolled back." >&2
    git status --short >&2
    exit 1
  fi
  BRANCH=$(git rev-parse --abbrev-ref HEAD)
  [ "$BRANCH" = "main" ] || die "refusing: on '$BRANCH', not main"

  if [ "$LOCAL" -eq 1 ]; then
    # /home/ubuntu/saathi has a .git of its own: a three-commit stub with no
    # remotes, predating the application, left behind because deploys unpack a
    # tarball over the tree rather than pulling. It reports branch `main`, and
    # it would pass the two checks above on a freshly deployed tree — so a
    # session that ran ops/deploy.sh --local from inside it would sail through
    # the gate and then install the deployed tree over itself, from a commit
    # that is not the commit anyone thinks is running. Refused twice below, for
    # two independent reasons, because this one has already misled a session.
    git remote -v | grep -qi saathi || die \
"refusing: $REPO_DIR has no git remote naming saathi. The .git inside the
deployed tree is a stub with no remotes; it is not a source to deploy from."
    [ "$REPO_DIR" != "$CANONICAL_REPO" ] || die \
"refusing: $REPO_DIR is the deploy target itself. Deploy from a real checkout —
the tree on the box is not one."
  fi

  SHA=$(git rev-parse --short HEAD)
  if [ "$LOCAL" -eq 1 ]; then
    say "deploying $SHA from main — local, on $INSTANCE, into ${TARGET:-$CANONICAL_REPO}"
  else
    say "deploying $SHA from main — remote, to $INSTANCE"
  fi

  TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT

  # The staged tree is built identically in both modes, so both install exactly
  # the same bytes and run exactly the same on-box script. Only the transport
  # between here and the box differs.
  say "stage"
  cp -r "$REPO_DIR" "$TMP/saathi"
  rm -rf "$TMP/saathi/.git" "$TMP/saathi/.venv" "$TMP/saathi/.env" "$TMP"/saathi/.env.bak.*
  chmod +x "$TMP/saathi/ops/deploy_onbox.sh" "$TMP/saathi/ops/deploy_verify.sh"
  VERIFY_SCRIPT="$TMP/saathi/ops/deploy_verify.sh"

  if [ "$LOCAL" -eq 1 ]; then
    # An array, so a --target with an odd character in it cannot become two
    # arguments. Remote mode never carries one: --target requires --local, so
    # the string built for the heredoc below is always the constant path.
    ONBOX_ARGV=(--repo "${TARGET:-$CANONICAL_REPO}")
    [ "$RUN_TESTS" -eq 1 ] || ONBOX_ARGV+=(--no-test)

    say "install, migrate, test, restart"
    sudo bash "$TMP/saathi/ops/deploy_onbox.sh" --from "$TMP/saathi" "${ONBOX_ARGV[@]}"
  else
    ONBOX_ARGS="--repo $CANONICAL_REPO"
    [ "$RUN_TESTS" -eq 1 ] || ONBOX_ARGS="$ONBOX_ARGS --no-test"

    say "package + upload"
    tar czf "$TMP/saathi.tar.gz" -C "$TMP" saathi
    aws s3 cp "$TMP/saathi.tar.gz" "s3://$BUCKET/saathi.tar.gz" --only-show-errors
    URL=$(aws s3 presign "s3://$BUCKET/saathi.tar.gz" --expires-in 1800)

    # This heredoc is unquoted, so it expands on *this* box. Only $URL and
    # $ONBOX_ARGS are meant to, and nothing else in it contains a dollar sign or
    # a backtick — which is the cheapest way to keep it that way, now that the
    # 120 delicate lines that used to live here are a file the box runs instead.
    # A previous session put backticks in a comment here and the heredoc ran
    # su - ubuntu at generation time, on the dev box, and hung on a password
    # prompt.
    cat > "$TMP/remote.sh" <<REMOTE
set -uo pipefail
rm -rf /tmp/saathi-deploy && mkdir -p /tmp/saathi-deploy
curl -fsSL -o /tmp/saathi-deploy/s.tgz "$URL" || { echo "FETCH FAILED"; exit 1; }
tar xzf /tmp/saathi-deploy/s.tgz -C /tmp/saathi-deploy || { echo "UNPACK FAILED"; exit 1; }
exec bash /tmp/saathi-deploy/saathi/ops/deploy_onbox.sh --from /tmp/saathi-deploy/saathi $ONBOX_ARGS
REMOTE
    say "install, migrate, test, restart"
    ssm "$TMP/remote.sh"
  fi
fi

# --- verify: active is not the same as working -------------------------------
# Deliberately not `set -e`'d away: a failure here must not skip the public
# surfaces, because which of the two is broken is the first thing you want to
# know. The status is carried to the end instead.
say "verify"
BAD=0
on_box "$VERIFY_SCRIPT" 300 || BAD=1

say "public surfaces"
TUNNEL=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 https://saathi.n8nworld.store/healthz || true)
HOOK=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 -X POST https://saathi.n8nworld.store/webhook/whatsapp -d '{}' || true)
SITE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 https://n8nworld.store/ || true)
printf '  %-34s %s\n' "healthz (through tunnel)" "$TUNNEL"
printf '  %-34s %s\n' "webhook unsigned (want 403)" "$HOOK"
printf '  %-34s %s\n' "site" "$SITE"
# The first two are Saathi and are asserted. `site` is the `site` branch on
# Cloudflare Pages — informational here, and not something this deploy changed.
[ "$TUNNEL" = "200" ] || { BAD=1; echo "  FAIL: healthz through the tunnel returned $TUNNEL, not 200"; }
[ "$HOOK" = "403" ] || { BAD=1; echo "  FAIL: an unsigned webhook POST returned $HOOK, not 403"; }

if [ "$BAD" -ne 0 ]; then
  say "VERIFY FAILED"
  if [ "$CHECK_ONLY" -eq 1 ]; then
    echo "Nothing was changed by this run — --check only looks." >&2
  else
    echo "The deploy already installed, migrated and restarted. This is a report" >&2
    echo "on the box you have just changed, not a deploy that was prevented." >&2
    echo "Putting the previous tree back: docs/RUNBOOK.md, and the snapshot path" >&2
    echo "printed above. It restores code only — migrations do not come back." >&2
  fi
  exit 1
fi

say "done"
