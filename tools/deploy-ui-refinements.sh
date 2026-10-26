set -eu
IFS= read -r harbour_existing_password
export HARBOR_EXISTING_PASSWORD="$harbour_existing_password"
python3 - <<'PY'
import http.client,json,os
from pathlib import Path
username=json.loads(Path('/var/lib/harbor/admin.json').read_text())['username']
conn=http.client.HTTPConnection('127.0.0.1',17080,timeout=40)
conn.request('POST','/api/login',json.dumps({'username':username,'password':os.environ['HARBOR_EXISTING_PASSWORD']}),{'Content-Type':'application/json'})
response=conn.getresponse();session=json.loads(response.read());assert response.status==200,'Cannot check active tasks before deployment'
headers={'Cookie':response.getheader('Set-Cookie').split(';')[0],'X-Harbor-CSRF':session['csrf'],'Content-Type':'application/json'}
conn.request('GET','/api/jobs',headers=headers);response=conn.getresponse();jobs=json.loads(response.read());assert response.status==200
assert not any(j['state'] in ('queued','running') for j in jobs),'A task is active; finish it before deploying the web service'
conn.request('POST','/api/logout','{}',headers);response=conn.getresponse();response.read()
print('No active app, drive or system tasks will be interrupted.')
PY
unset HARBOR_EXISTING_PASSWORD harbour_existing_password
grep -qx 'ID=harbor' /etc/os-release
stamp=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p /var/lib/harbor/release-backups
tar -czf "/var/lib/harbor/release-backups/ui-refinements-$stamp.tar.gz" -C /opt harbor
tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
python3 -m compileall -q /DATA/harbor/source/harbor
rsync -a --delete /DATA/harbor/source/harbor/ /opt/harbor/
systemctl restart harbor
python3 - <<'PY'
from pathlib import Path
path=Path('/etc/os-release');path.write_text(path.read_text().replace('0.3.0','0.3.1'))
PY
systemctl is-active harbor lightdm ssh smbd docker
printf 'Desktop and progress refinements deployed. No disk configuration changed.\n'
