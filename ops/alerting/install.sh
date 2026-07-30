#!/usr/bin/env bash
# Install Saathi alerting on the runtime box. Idempotent; safe to re-run.
#
# Two mechanisms, because neither covers the other's blind spot:
#
#   OnFailure=      fires the moment a unit fails. Cannot see a timer that
#                   never fired at all, or a worker that is "active" but wedged.
#   metric alarms   catch silence — a worker that stopped doing work, a backup
#                   that never ran. Both alarms treat missing data as BREACHING,
#                   so the monitoring failing looks like the thing failing.
#                   That false alarm is deliberate: an alarm that goes quiet
#                   when it breaks is indistinguishable from healthy.
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"

install -m 0755 "$HERE/saathi-alert"  /usr/local/bin/saathi-alert
install -m 0755 "$HERE/saathi-metric" /usr/local/bin/saathi-metric

# The backup unit this script wires alerting onto. It used to exist only in
# /usr/local/bin on one box, so the successor inherited the alerting and not the
# backup — the BackupSuccess alarm was armed against a job that could never run.
install -m 0755 "$HERE/../backup/saathi-backup" /usr/local/bin/saathi-backup
install -m 0644 "$HERE/../backup/saathi-backup.service" /etc/systemd/system/saathi-backup.service
install -m 0644 "$HERE/../backup/saathi-backup.timer"   /etc/systemd/system/saathi-backup.timer
install -m 0644 "$HERE/saathi-alert@.service" /etc/systemd/system/saathi-alert@.service
install -m 0644 "$HERE/../saathi-meta-guard.service" /etc/systemd/system/saathi-meta-guard.service
install -m 0644 "$HERE/../saathi-meta-guard.timer" /etc/systemd/system/saathi-meta-guard.timer

# OnFailure drop-ins rather than editing the units, so a redeploy of a unit
# file does not silently drop the alerting with it.
for unit in saathi-web saathi-worker saathi-backup cloudflared-saathi; do
    mkdir -p "/etc/systemd/system/${unit}.service.d"
    cat > "/etc/systemd/system/${unit}.service.d/10-alert.conf" <<CONF
[Unit]
OnFailure=saathi-alert@%N.service
CONF
done

# The backup is not Python, so it publishes its own success datapoint. Without
# this, "the timer never fired" is invisible: nothing failed, nothing ran.
mkdir -p /etc/systemd/system/saathi-backup.service.d
cat > /etc/systemd/system/saathi-backup.service.d/20-metric.conf <<'CONF'
[Service]
ExecStartPost=/usr/local/bin/saathi-metric BackupSuccess 1
CONF

systemctl daemon-reload
systemctl enable --now saathi-meta-guard.timer
systemctl enable --now saathi-backup.timer
echo "installed. verify with: systemctl show saathi-worker -p OnFailure"
echo "                        systemctl list-timers saathi-backup.timer"
