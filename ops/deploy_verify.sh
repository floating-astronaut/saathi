#!/usr/bin/env bash
# On-box verification, run after every deploy and by `ops/deploy.sh --check`.
# Read-only: it starts nothing, stops nothing and writes nothing.
#
# Both transports run this same file — remote mode ships it over SSM, local
# mode runs it directly — so "verified" means the same thing either way.
#
# `active` is not the same as `working`, which is the whole point of the last
# three lines.
set -u

for u in saathi-web saathi-worker cloudflared-saathi postgresql; do
  printf '  %-20s %s\n' "$u" "$(systemctl is-active $u)"
done
echo -n "  healthz              "; curl -s --max-time 8 http://127.0.0.1:3130/healthz; echo
echo "  worker kinds         $(journalctl -u saathi-worker --since '90 seconds ago' --no-pager | grep -o "scheduled kinds:.*" | tail -1)"
ERR=$(journalctl -u saathi-web -u saathi-worker --since '90 seconds ago' --no-pager | grep -ciE 'traceback|critical' || true)
echo "  errors since restart $ERR"
