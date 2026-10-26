import http.client
import json
from pathlib import Path
import ssl
import sys

password = sys.stdin.readline().rstrip('\n')
assert password
assert 'ID=harbor' in Path('/etc/os-release').read_text()
boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
assert boot_id != '7a872461-103f-4b2b-b6d2-e434d02c64fb'
cmdline = Path('/proc/cmdline').read_text()
assert 'harbor.subdir=harbor/rootfs' in cmdline
assert 'harbor.trial=1' not in cmdline
context=ssl.create_default_context(cafile='/var/lib/harbor/tls.crt')
conn=http.client.HTTPSConnection('127.0.0.1',8443,context=context,timeout=15)
conn.request('POST','/api/login',json.dumps({'username':'rico','password':password}),{'Content-Type':'application/json'})
response=conn.getresponse()
assert response.status==200, response.read()
session=json.loads(response.read())
cookie=response.getheader('Set-Cookie').split(';')[0]
conn.close()
conn=http.client.HTTPSConnection('127.0.0.1',8443,context=context,timeout=15)
conn.request('GET','/api/summary',headers={'Cookie':cookie})
response=conn.getresponse()
summary=json.loads(response.read())
assert response.status==200 and summary['storage']['mounted'],summary
assert summary['storage']['redundancy']=='Mirrored (RAID1)',summary
conn.close()
config=json.loads(Path('/var/lib/harbor/config.json').read_text())
assert {'Documents','Media','Backups'}.issubset({s['name'] for s in config['shares']})
original=Path('/srv/harbor/storage/shares/Documents/Harbor-Readme.txt').read_bytes()
restored=Path('/srv/harbor/storage/shares/Harbor-Restore-Check/Harbor-Readme.txt').read_bytes()
assert original==restored
assert Path('/srv/harbor/storage/shares/Documents/smb-test.txt').read_bytes()==b'Harbor SMB integrity verification\n'
conn=http.client.HTTPSConnection('127.0.0.1',8443,context=context,timeout=15)
conn.request('POST','/api/logout','{}',{'Cookie':cookie,'Content-Type':'application/json','X-Harbor-CSRF':session['csrf']})
response=conn.getresponse()
assert response.status==200
response.read()
conn.close()
Path('/var/lib/harbor/post-reboot-verification.json').write_text(json.dumps({'boot_id':boot_id,'cmdline':cmdline.strip(),'summary':summary},indent=2))
print('PASS: new physical boot ID, persistent Harbor default, HTTPS login, RAID1 mount, shared folders, and original/restored file contents')
