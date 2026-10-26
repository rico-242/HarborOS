set -eu
if [ -t 0 ]; then
  harbour_existing_password=$(python3 -c 'import getpass; print(getpass.getpass("Existing Harbour owner password: "))')
else
  IFS= read -r harbour_existing_password
fi
export HARBOR_EXISTING_PASSWORD="$harbour_existing_password"
python3 - <<'PY'
import hashlib,http.client,json,os,time
from pathlib import Path
username=json.loads(Path('/var/lib/harbor/admin.json').read_text())['username'];cookie='';csrf=''
before=hashlib.sha256(Path('/var/lib/harbor/admin.json').read_bytes()).hexdigest()
def request(path,data=None,raw=False):
    global cookie,csrf
    conn=http.client.HTTPConnection('127.0.0.1',17080,timeout=40);headers={'Cookie':cookie,'X-Harbor-CSRF':csrf}
    if data is not None:headers['Content-Type']='application/octet-stream' if raw else 'application/json'
    conn.request('POST' if data is not None else 'GET',path,data if raw else json.dumps(data) if data is not None else None,headers)
    response=conn.getresponse();body=response.read();value=json.loads(body)
    if response.status==401:raise PermissionError('Sign in again')
    assert response.status<400,(path,response.status,value)
    if response.getheader('Set-Cookie'):cookie=response.getheader('Set-Cookie').split(';')[0]
    if isinstance(value,dict) and 'csrf' in value:csrf=value['csrf']
    return value
def login():request('/api/login',{'username':username,'password':os.environ['HARBOR_EXISTING_PASSWORD']})
login();storage=request('/api/summary')['storage']['source']
candidate=request('/api/os-updates/upload',Path('/tmp/harbour-0.4.0-update.bundle').read_bytes(),raw=True)
job=request('/api/os-updates/action',{'action':'install','candidate':candidate['id'],'confirmation':'UPDATE 0.4.0'})
for _ in range(180):
    try:
        current=next(j for j in request('/api/jobs') if j['id']==job['id'])
        if current['state'] in ('failed','completed'):break
    except (OSError,http.client.HTTPException):
        try:login()
        except (OSError,http.client.HTTPException):pass
    time.sleep(1)
else:raise RuntimeError('Signed update did not complete in time')
assert current['state']=='completed',current
assert request('/api/health')['version']=='0.4.0';login()
assert hashlib.sha256(Path('/var/lib/harbor/admin.json').read_bytes()).hexdigest()==before
assert request('/api/summary')['storage']['source']==storage
network=request('/api/network');assert network['config'] is None and not Path('/sys/class/net/bond0').exists()
result={'version':'0.4.0','signed_in_place_update':True,'owner_preserved':True,'storage_preserved':True,'network_unchanged':True,'ethernet_adapters':sum(i['physical'] for i in network['interfaces']),'bond_requires_second_adapter':network['eligible_count']<2,'repository':request('/api/os-updates')['repository'],'rebooted':False}
Path('/DATA/harbor/release/artifacts/maintenance-nas-validation.json').write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)
request('/api/logout',{})
PY
unset HARBOR_EXISTING_PASSWORD harbour_existing_password
systemctl is-active harbor lightdm ssh smbd docker
systemctl --failed --no-pager
