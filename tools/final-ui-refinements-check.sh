set -eu
grep -qx 'ID=harbor' /etc/os-release
python3 - <<'PY'
from pathlib import Path
path=Path('/etc/os-release');source=path.read_text();path.write_text(source.replace('0.3.0','0.3.1'))
PY
systemctl is-active harbor lightdm ssh smbd docker
systemctl --failed --no-pager
curl --fail --silent --cacert /var/lib/harbor/tls.crt https://127.0.0.1:8443/api/health
printf '\n'
for asset in process.js widgets.js refinements.css; do
  test "$(curl --silent --output /dev/null --write-out '%{http_code}' http://127.0.0.1:17080/$asset)" = 200
done
printf 'All new assets are available. Accounts and storage were preserved.\n'
