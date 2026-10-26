"""API acceptance test against the installed disposable VM, with console-pinned TLS."""
import hashlib
import http.client
import json
from pathlib import Path
import re
import secrets
import ssl
import time

root=Path('/DATA/harbor/iso-test')
cookie=''
csrf=''


def request(path,data=None):
    global cookie,csrf
    console=(root/'serial.log').read_text(errors='replace')
    fingerprint=re.findall(r'sha256 Fingerprint=([0-9A-F:]{95})',console,re.I)[-1].replace(':','').lower()
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname=False;context.verify_mode=ssl.CERT_NONE
    connection=http.client.HTTPSConnection('127.0.0.1',19443,context=context,timeout=45)
    connection.connect()
    assert hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest()==fingerprint,'VM TLS identity mismatch'
    headers={'Cookie':cookie,'X-Harbor-CSRF':csrf}
    body=None
    if data is not None:
        body=json.dumps(data);headers['Content-Type']='application/json'
    connection.request('POST' if data is not None else 'GET',path,body,headers)
    response=connection.getresponse();encoded=response.read()
    if response.getheader('Set-Cookie'):cookie=response.getheader('Set-Cookie').split(';')[0]
    value=json.loads(encoded)
    if response.status>=400:raise RuntimeError(f'{path}: {response.status}: {value}')
    if isinstance(value,dict) and 'csrf' in value:csrf=value['csrf']
    connection.close()
    return value


def wait_job(job,timeout=300):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        current=next(j for j in request('/api/jobs') if j['id']==job['id'])
        if current['state']=='failed':raise RuntimeError(current['error'])
        if current['state']=='completed':return current
        time.sleep(2)
    raise RuntimeError('VM job timed out')


deadline=time.monotonic()+120
while time.monotonic()<deadline:
    try:
        if re.search(r'sha256 Fingerprint=',(root/'serial.log').read_text(errors='replace')):
            health=request('/api/health');break
    except (OSError,IndexError):pass
    time.sleep(2)
else:raise RuntimeError('Installed Harbor did not reach first setup')
assert health['version']=='0.2.0' and not health['demo']
if health['setup_required']:
    password=secrets.token_urlsafe(24)
    code=re.findall(r'First-time setup code: ([0-9a-f]{48})',(root/'serial.log').read_text(errors='replace'))[-1]
    request('/api/setup',{'code':code,'username':'harbortest','password':password})
    (root/'test-account.json').write_text(json.dumps({'username':'harbortest','password':password}))
    (root/'test-account.json').chmod(0o600)
else:
    request('/api/login',json.loads((root/'test-account.json').read_text()))
catalog=request('/api/catalog');apps=request('/api/apps')
assert len(apps)==181
inventory=request('/api/storage/disks')
assert not inventory['live']
system=next(d for d in inventory['disks'] if d['serial']=='HARBOR_TEST_SYSTEM')
assert not system['eligible'],'System disk must be protected'
selected=[d for d in inventory['disks'] if d['serial'] in ('HARBOR_TEST_DATA1','HARBOR_TEST_DATA2')]
assert len(selected)==2
if not request('/api/summary')['storage']['mounted']:
    assert all(d['eligible'] for d in selected)
    plan=request('/api/storage/plan',{'name':'Test-Mirror','level':'1','disks':[d['id'] for d in selected]})
    wait_job(request('/api/storage/create',{'token':plan['token'],'confirmation':'ERASE Test-Mirror','acknowledge':True}))
else:
    assert all(not d['eligible'] for d in selected),'All active RAID members must be protected'
summary=request('/api/summary')
assert summary['storage']['mounted'] and summary['storage']['redundancy']=='RAID1'
if not any(e['name']=='Install-Test' for e in request('/api/files')['entries']):request('/api/shares',{'name':'Install-Test'})
assert any(e['name']=='Install-Test' for e in request('/api/files')['entries'])
print('Installed BIOS boot, first setup, catalog, protected system disk, RAID1 creation and sharing passed.',flush=True)
app_plan=request('/api/app-plan',{'id':'syncthing'})
if not next(a for a in request('/api/apps') if a['id']=='syncthing')['installed']:
    wait_job(request('/api/app-action',{'id':'syncthing','action':'install','options':{'approve_access':True}}),timeout=900)
app=next(a for a in request('/api/apps') if a['id']=='syncthing')
assert app['installed'] and app['state']=='running'
wait_job(request('/api/app-action',{'id':'syncthing','action':'stop'}))
assert next(a for a in request('/api/apps') if a['id']=='syncthing')['state']=='stopped'
wait_job(request('/api/app-action',{'id':'syncthing','action':'start'}))
assert next(a for a in request('/api/apps') if a['id']=='syncthing')['state']=='running'
report={'iso_live_boot':'UEFI','installed_boot':'BIOS','version':health['version'],'catalog':len(apps),
        'catalog_revision':catalog['revision'],'raid':'RAID1','share':'Install-Test','app_install_stop_start':'Syncthing','passed':True}
(root/'acceptance-result.json').write_text(json.dumps(report,indent=2))
print('Official Syncthing install, stop and start passed.',flush=True)
