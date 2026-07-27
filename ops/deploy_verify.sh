#!/usr/bin/env bash
# On-box verification, run after every deploy and by `ops/deploy.sh --check`.
# Read-only: it starts nothing, stops nothing and writes nothing.
#
# Both transports run this same file — remote mode ships it over SSM, local
# mode runs it directly — so "verified" means the same thing either way.
#
# `active` is not the same as `working`, which is the point of the healthz and
# journal checks; and a check that cannot fail is not a check, which is the
# point of the exit code.
#
#   exit 0  every assertion below passed
#   exit 1  at least one did not
#
# **A non-zero exit prevents nothing.** By the time this runs the deploy has
# already installed, migrated and restarted; there is nothing left to stop. It
# is the loudest available statement that the box you just changed is not
# serving, and the signal to put the previous tree back — not an abort.
set -u

FAIL=0
fail() { FAIL=1; echo "  FAIL: $*"; }

for u in saathi-web saathi-worker cloudflared-saathi postgresql; do
  st=$(systemctl is-active "$u" 2>/dev/null || true)
  printf '  %-20s %s\n' "$u" "${st:-unknown}"
  [ "$st" = "active" ] || fail "$u is ${st:-unknown}, not active"
done

HEALTH=$(curl -s --max-time 8 http://127.0.0.1:3130/healthz || true)
echo "  healthz              ${HEALTH:-<no response>}"
case "$HEALTH" in
  *'"ok":true'*) ;;
  *) fail "healthz did not report ok:true — a unit can be active and the app still be broken" ;;
esac

# Informational, not asserted: empty whenever nothing has restarted inside the
# window, which is the normal case for --check.
echo "  worker kinds         $(journalctl -u saathi-worker --since '90 seconds ago' --no-pager | grep -o "scheduled kinds:.*" | tail -1)"

ERR=$(journalctl -u saathi-web -u saathi-worker --since '90 seconds ago' --no-pager | grep -ciE 'traceback|critical' || true)
echo "  errors since restart $ERR"
[ "$ERR" = "0" ] || fail "$ERR traceback/critical line(s) in the last 90 seconds"

if [ "$FAIL" -ne 0 ]; then
  echo
  echo "VERIFY FAILED. This stopped nothing — the deploy installed, migrated and"
  echo "restarted before reaching here. Treat it as an outage in progress, not as"
  echo "a deploy that was prevented. The previous tree is in the snapshot printed"
  echo "earlier in this run; see docs/RUNBOOK.md, 'Putting the previous tree back'."
  exit 1
fi
