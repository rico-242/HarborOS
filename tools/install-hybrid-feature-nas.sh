set -eu
IFS= read -r existing_password
export HARBOR_EXISTING_PASSWORD="$existing_password"
python3 - <<'PY'
import hashlib,http.client,json,os,time,urllib.request
from pathlib import Path
cookie=csrf='';username=json.loads(Path('/var/lib/harbor/admin.json').read_text())['username']
def request(path,data=None,raw=False):
 global cookie,csrf
 conn=http.client.HTTPConnection('127.0.0.1',17080,timeout=40);headers={'Cookie':cookie,'X-Harbor-CSRF':csrf}
 if data is not None:headers['Content-Type']='application/octet-stream' if raw else 'application/json'
 conn.request('POST' if data is not None else 'GET',path,data if raw else json.dumps(data) if data is not None else None,headers)
 response=conn.getresponse();value=json.loads(response.read());conn.close()
 if response.status==401:raise PermissionError('Sign in again')
 assert response.status<400,(path,response.status,value)
 if response.getheader('Set-Cookie'):cookie=response.getheader('Set-Cookie').split(';')[0]
 if isinstance(value,dict) and 'csrf' in value:csrf=value['csrf']
 return value
def login():request('/api/login',{'username':username,'password':os.environ['HARBOR_EXISTING_PASSWORD']})
def wait(job,limit=240):
 for _ in range(limit):
  try:
   current=next(j for j in request('/api/jobs') if j['id']==job['id'])
   if current['state'] in ('failed','completed'):
    assert current['state']=='completed',current
    return current
  except (OSError,http.client.HTTPException):
   try:login()
   except (OSError,http.client.HTTPException):pass
  time.sleep(1)
 raise RuntimeError('Operation did not complete in time')
login();assert request('/api/health')['version']=='0.5.2'
owner=hashlib.sha256(Path('/var/lib/harbor/admin.json').read_bytes()).hexdigest()
storage=request('/api/summary')['storage']['source'];network=request('/api/network')['config']
candidate=request('/api/os-updates/upload',Path('/tmp/harbour-0.6.0-update.bundle').read_bytes(),True)
wait(request('/api/os-updates/action',{'action':'install','candidate':candidate['id'],'confirmation':'UPDATE 0.6.0'}))
login();assert request('/api/health')['version']=='0.6.0'
assert hashlib.sha256(Path('/var/lib/harbor/admin.json').read_bytes()).hexdigest()==owner
assert request('/api/summary')['storage']['source']==storage
assert request('/api/network')['config']==network
print('Signed 0.6.0 installed; owner, storage and network preserved.',flush=True)
request('/api/logout',{})
PY
unset HARBOR_EXISTING_PASSWORD existing_password
systemctl is-active harbor lightdm ssh smbd docker
