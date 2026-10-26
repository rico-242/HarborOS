set -eu
printf 'Resolver\n'
ls -l /etc/resolv.conf
cat /etc/resolv.conf
resolvectl status --no-pager | head -45
printf '\nAPT state\n'
ls /DATA/harbor/release
