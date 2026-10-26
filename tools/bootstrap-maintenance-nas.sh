# One-time bridge for installations made before signed update support existed.
set -eu
if [ -t 0 ]; then
  harbour_existing_password=$(python3 -c 'import getpass; print(getpass.getpass("Existing Harbour owner password: "))')
else
  IFS= read -r harbour_existing_password
fi
export HARBOR_EXISTING_PASSWORD="$harbour_existing_password"
python3 - <<'PY'
import http.client,json,os
from pathlib import Path
username=json.loads(Path('/var/lib/harbor/admin.json').read_text())['username']
conn=http.client.HTTPConnection('127.0.0.1',17080,timeout=40)
conn.request('POST','/api/login',json.dumps({'username':username,'password':os.environ['HARBOR_EXISTING_PASSWORD']}),{'Content-Type':'application/json'})
response=conn.getresponse();session=json.loads(response.read());assert response.status==200,'Cannot authenticate to check current tasks'
headers={'Cookie':response.getheader('Set-Cookie').split(';')[0],'X-Harbor-CSRF':session['csrf'],'Content-Type':'application/json'}
conn.request('GET','/api/health');response=conn.getresponse();health=json.loads(response.read());assert health['version']=='0.3.1',health
conn.request('GET','/api/jobs',headers=headers);response=conn.getresponse();jobs=json.loads(response.read());assert response.status==200
assert not any(j['state'] in ('queued','running') for j in jobs),'Finish the current task before installing the updater bridge'
conn.request('POST','/api/logout','{}',headers);response=conn.getresponse();response.read()
print('Baseline 0.3.1 authenticated; no current tasks will be interrupted.')
PY
unset HARBOR_EXISTING_PASSWORD harbour_existing_password
grep -qx 'ID=harbor' /etc/os-release
test ! -f /var/lib/harbor/release-state.json
stamp=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p /var/lib/harbor/release-backups
tar -czf "/var/lib/harbor/release-backups/pre-updater-$stamp.tar.gz" -C /opt harbor
tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
sh /DATA/harbor/source/os/install-maintenance.sh /DATA/harbor/source /
rsync -a --delete /DATA/harbor/source/harbor/ /opt/harbor/
python3 - <<'PY'
from pathlib import Path
path=Path('/opt/harbor/server.py');path.write_text(path.read_text().replace("VERSION = '0.4.0'","VERSION = '0.3.1'"))
PY
install -m 644 /DATA/harbor/source/os/harbor.service /etc/systemd/system/harbor.service
systemctl daemon-reload
systemctl start harbour-update-recover.service
systemctl restart harbor.service
systemctl is-active harbor lightdm ssh smbd docker
printf 'Trusted updater bridge installed. The signed release can now be installed without an ISO.\n'
