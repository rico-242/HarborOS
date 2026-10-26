import http.client
import json
from pathlib import Path
import ssl
import sys
import time

password = sys.stdin.readline().rstrip('\n')
assert password
assert 'ID=harbor' in Path('/etc/os-release').read_text()
context = ssl.create_default_context(cafile='/var/lib/harbor/tls.crt')
cookie = ''
csrf = ''

def request(path, data=None, raw=False):
    global cookie, csrf
    headers = {'Cookie':cookie, 'X-Harbor-CSRF':csrf}
    if data is not None and not raw:
        data = json.dumps(data)
        headers['Content-Type'] = 'application/json'
    conn = http.client.HTTPSConnection('127.0.0.1',8443,context=context,timeout=30)
    conn.request('POST' if data is not None else 'GET',path,data,headers)
    response = conn.getresponse()
    body = response.read()
    if response.getheader('Set-Cookie'):
        cookie = response.getheader('Set-Cookie').split(';')[0]
    try: value = json.loads(body)
    except ValueError: value = body
    conn.close()
    assert response.status < 400, (path,response.status,value)
    return value

def finish(job):
    for _ in range(60):
        item=next(j for j in request('/api/jobs') if j['id']==job['id'])
        if item['state']=='failed': raise RuntimeError(item['error'])
        if item['state']=='completed': return item.get('result')
        time.sleep(1)
    raise RuntimeError('Timed out waiting for the verification job.')

session = request('/api/login', {'username':'rico','password':password})
csrf = session['csrf']
summary = request('/api/summary')
assert not summary['demo'] and summary['storage']['mounted'], summary
assert summary['storage']['filesystem']=='btrfs', summary
assert summary['storage']['redundancy']=='Mirrored (RAID1)', summary
assert request('/api/apps'), 'Docker catalog unavailable'
print('PASS: physical Harbor boot, verified HTTPS sign-in, mirrored data volume, and Docker engine')
shares={item['name'] for item in request('/api/shares')}
for name in ('Documents','Media','Backups'):
    if name not in shares: request('/api/shares', {'name':name})
content=b'Welcome to Harbor OS.\nYour personal server is running Harbor OS 0.1.0 on Debian 13.\nYour shared folders are Documents, Media, and Backups.\n'
listing=request('/api/files?path=Documents')
if not any(f['name']=='Harbor-Readme.txt' for f in listing['entries']):
    request('/api/upload?path=Documents&name=Harbor-Readme.txt',content,raw=True)
assert request('/api/download?path=Documents/Harbor-Readme.txt')==content
snapshot=finish(request('/api/snapshots',{'share':'Documents'}))
restored='Harbor-Restore-Check'
if restored not in shares:
    finish(request('/api/restore',{'snapshot':snapshot['id'],'name':restored}))
assert request('/api/download?path='+restored+'/Harbor-Readme.txt')==content
print('PASS: physical file transfer, snapshot, and restored file integrity')
Path('/var/lib/harbor/physical-verification.json').write_text(json.dumps({'summary':summary,'snapshot':snapshot,'restored':restored},indent=2))
request('/api/logout',{})
Path('/var/lib/harbor/boot-confirmed').write_text('Physical boot, TLS, mirror, Docker, file transfer, and restore verified.\n')
print('Trial boot confirmed. Ready to make Harbor the default.')
