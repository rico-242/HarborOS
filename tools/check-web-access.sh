set -eu
printf '\n--- Harbor service ---\n'
systemctl is-active harbor.service
systemctl is-enabled harbor.service
printf '\n--- Address ---\n'
hostname -I
printf '\n--- Web listener ---\n'
ss -lntp | grep ':8443 '
printf '\n--- Recent service messages ---\n'
journalctl -u harbor.service -n 12 --no-pager
