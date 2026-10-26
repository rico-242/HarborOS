"""Signed 0.5.0 upgrade and anonymous GitHub checks in the disposable VM."""
import hashlib
import http.client
import json
import time
import urllib.request
from pathlib import Path

assert Path('/sys/class/dmi/id/product_name').read_text().startswith('Standard PC')
accounts=json.loads(Path('/root/harbour-test-accounts.json').read_text())
cookie=csrf=''

def request(path,data=None,raw=False):
    global cookie,csrf
    conn=http.client.HTTPConnection('127.0.0.1',17080,timeout=40)
    headers={'Cookie':cookie,'X-Harbor-CSRF':csrf}
    if data is not None:headers['Content-Type']='application/octet-stream' if raw else 'application/json'
    conn.request('POST' if data is not None else 'GET',path,data if raw else json.dumps(data) if data is not None else None,headers)
    response=conn.getresponse();value=json.loads(response.read());conn.close()
    if response.status==401:raise PermissionError('Session must reconnect')
    assert response.status<400,(path,response.status,value)
    if response.getheader('Set-Cookie'):cookie=response.getheader('Set-Cookie').split(';')[0]
    if isinstance(value,dict) and 'csrf' in value:csrf=value['csrf']
    return value

def login():request('/api/login',{'username':accounts['owner'],'password':accounts['owner_password']})

def wait(job):
    for _ in range(180):
        try:
            value=next(j for j in request('/api/jobs') if j['id']==job['id'])
            if value['state'] in ('failed','completed'):
                assert value['state']=='completed',value
                return value
        except (PermissionError,OSError,http.client.HTTPException):
            try:login()
            except (PermissionError,OSError,http.client.HTTPException):pass
        time.sleep(1)
    raise RuntimeError('Update job timed out')

login()
assert request('/api/health')['version']=='0.4.1'
before=hashlib.sha256(Path('/var/lib/harbor/admin.json').read_bytes()).hexdigest()
storage=request('/api/summary')['storage']['source']
network=request('/api/network')['config']
candidate=request('/api/os-updates/upload',Path('/tmp/harbour-0.5.0-update.bundle').read_bytes(),raw=True)
wait(request('/api/os-updates/action',{'action':'install','candidate':candidate['id'],'confirmation':'UPDATE 0.5.0'}))
assert request('/api/health')['version']=='0.5.0'
login()
info=request('/api/os-updates')
assert info['repository']=='rico-242/HarborOS' and info['include_prereleases'] and not info['token_configured'],info
request('/api/os-updates/action',{'action':'source','repository':'rico-242/HarborOS','include_prereleases':True,'token_action':'remove'})
result=wait(request('/api/os-updates/action',{'action':'check'}))['result']
assert result['version'] in ('0.4.1','0.5.0') and not result['available'],result
assert not Path('/var/lib/harbor/release-updates/github-credential.json').exists()
assert Path('/var/lib/harbor/release-updates').stat().st_mode&0o777==0o700
assert hashlib.sha256(Path('/var/lib/harbor/admin.json').read_bytes()).hexdigest()==before
assert request('/api/summary')['storage']['source']==storage
assert request('/api/network')['config']==network
assert request('/api/system')['services']['harbor']=='active'
for asset,marker in (('theme.js',b'harbourAppearance'),('experience.js',b'theme-set'),('experience.css',b'data-theme=light'),('wallpaper.svg',b'<svg'),('catalog/icons/featured-blinko.png',b'\x89PNG')):
    with urllib.request.urlopen('http://127.0.0.1:17080/'+asset,timeout=30) as response:
        body=response.read()
        assert response.status==200 and marker in body,asset
assert request('/api/system')['device']['model']
assert set(('linear','0','1','5','6','10')).issubset(request('/api/storage/disks')['levels'])
assert not request('/api/os-updates')['candidates']
report={'version':'0.5.0','theme_assets_served':True,'featured_artwork_served':True,'device_info':True,'raid_options_available':True,'older_candidates_hidden':True,'signed_vm_upgrade':True,'public_github_check':True,'token_required':False,
        'default_repository':True,'experimental_channel':True,'owner_preserved':True,'storage_preserved':True,'network_preserved':True}
Path('/root/harbour-experience-validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report),flush=True)
request('/api/logout',{})
