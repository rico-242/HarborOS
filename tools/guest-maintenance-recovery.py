"""Verify automatic network timeout and failed-release recovery only in the VM."""
import hashlib,http.client,json,time
from pathlib import Path
assert Path('/sys/class/dmi/id/product_name').read_text().startswith('Standard PC')
accounts=json.loads(Path('/root/harbour-test-accounts.json').read_text());cookie='';csrf=''
def request(path,data=None,raw=False):
    global cookie,csrf
    connection=http.client.HTTPConnection('127.0.0.1',17080,timeout=30);headers={'Cookie':cookie,'X-Harbor-CSRF':csrf}
    if data is not None:headers['Content-Type']='application/octet-stream' if raw else 'application/json'
    connection.request('POST' if data is not None else 'GET',path,data if raw else json.dumps(data) if data is not None else None,headers)
    response=connection.getresponse();body=response.read();value=json.loads(body)
    if response.status==401:raise PermissionError('Sign in again')
    if response.status>=400:raise RuntimeError((path,response.status,value))
    if response.getheader('Set-Cookie'):cookie=response.getheader('Set-Cookie').split(';')[0]
    if isinstance(value,dict) and 'csrf' in value:csrf=value['csrf']
    return value
def login():request('/api/login',{'username':accounts['owner'],'password':accounts['owner_password']})
login();report_path=Path('/root/harbour-maintenance-validation.json');report=json.loads(report_path.read_text())
for _ in range(130):
    state=request('/api/network')['transaction']
    if state['phase']=='rolled_back':break
    if state['state']=='failed':raise RuntimeError(state)
    time.sleep(1)
else:raise RuntimeError('The network rollback timer did not run')
assert not Path('/sys/class/net/bond0').exists();assert request('/api/network')['config'] is None
report['automatic_network_timeout']=True;print('Unconfirmed LACP network automatically restored after the real timer.',flush=True)
before=hashlib.sha256(Path('/var/lib/harbor/admin.json').read_bytes()).hexdigest();candidate=request('/api/os-updates/upload',Path('/tmp/harbour-bad-release-test.bundle').read_bytes(),raw=True)
job=request('/api/os-updates/action',{'action':'install','candidate':candidate['id'],'confirmation':'UPDATE 0.4.1'})
for _ in range(150):
    try:
        current=next(j for j in request('/api/jobs') if j['id']==job['id'])
        if current['state']=='failed':break
    except (OSError,http.client.HTTPException):
        try:login()
        except (OSError,http.client.HTTPException):pass
    time.sleep(1)
else:raise RuntimeError('The unhealthy release was not recovered')
assert 'previous release was restored' in current['error'],current
assert request('/api/health')['version']=='0.4.0';login()
assert hashlib.sha256(Path('/var/lib/harbor/admin.json').read_bytes()).hexdigest()==before
report['failed_release_automatic_recovery']=True
# Remove only the explicitly disposable candidate receipt so it cannot be installed accidentally again.
(Path('/var/lib/harbor/release-updates/candidates')/(candidate['id']+'.json')).unlink()
(Path('/var/lib/harbor/release-updates/incoming')/(candidate['id']+'.bundle')).unlink()
report_path.write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
