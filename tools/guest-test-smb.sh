set -eu
python3 /tmp/harbor-test-smb.py
curl --retry 30 --retry-all-errors --retry-delay 2 --max-time 5 --fail --silent http://127.0.0.1:8096/health
printf '\nPASS: Jellyfin HTTP health endpoint\n'
systemctl --failed --no-pager
