"""Test the JBOD fallback only on the disposable VM's remaining virtual disks."""
import base64
import hashlib
import json
from pathlib import Path
import re
import shlex
import time
import paramiko

root=Path('/DATA/harbor/iso-test')
account=json.loads((root/'test-account.json').read_text())
expected=re.findall(r'SHA256:([A-Za-z0-9+/]{43})',(root/'serial.log').read_text(errors='replace'))[-1]
class ConsoleKey(paramiko.MissingHostKeyPolicy):
    def missing_host_key(self,client,hostname,key):
        actual=base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
        if actual!=expected:raise RuntimeError('Disposable VM SSH identity mismatch')
client=paramiko.SSHClient();client.set_missing_host_key_policy(ConsoleKey())
client.connect('127.0.0.1',port=19222,username=account['username'],password=account['password'],look_for_keys=False,allow_agent=False)
with client.open_sftp() as transfer:
    transfer.put('/DATA/harbor/source/harbor/storage.py','/tmp/harbor-storage-final.py')
    transfer.put('/DATA/harbor/source/harbor/server.py','/tmp/harbor-server-final.py')
script='''set -eu
test "$(lsblk -dn -o SERIAL /dev/vda)" = HARBOR_TEST_SYSTEM
install -m 644 /tmp/harbor-storage-final.py /opt/harbor/storage.py
install -m 644 /tmp/harbor-server-final.py /opt/harbor/server.py
sed -i 's|^HARBOR_STORAGE=.*|HARBOR_STORAGE=/srv/harbor/jbodtest|' /etc/harbor.conf
mkdir -p /srv/harbor/jbodtest
systemctl restart harbor
'''
stdin,stdout,stderr=client.exec_command("sudo -S -p '' sh -c "+shlex.quote(script))
stdin.write(account['password']+'\n');stdin.flush();stdin.channel.shutdown_write()
error=stderr.read().decode();status=stdout.channel.recv_exit_status()
assert status==0,error
client.close()
# Reuse the acceptance client's certificate-pinned API helpers without its test body.
source=Path('/tmp/harbor-test-installed.py').read_text().split('deadline=time.monotonic()+120')[0]
namespace={};exec(compile(source,'acceptance-client','exec'),namespace)
request=namespace['request'];wait_job=namespace['wait_job']
for attempt in range(15):
    try:
        request('/api/login',account)
        break
    except (OSError,ConnectionError):
        if attempt==14:raise
        time.sleep(1)
selected=[d for d in request('/api/storage/disks')['disks'] if d['serial'] in ('HARBOR_TEST_DATA3','HARBOR_TEST_DATA4')]
assert len(selected)==2 and all(d['eligible'] for d in selected)
plan=request('/api/storage/plan',{'name':'Test-JBOD','level':'linear','disks':[d['id'] for d in selected]})
wait_job(request('/api/storage/create',{'token':plan['token'],'confirmation':'ERASE Test-JBOD','acknowledge':True}))
summary=request('/api/summary')
assert summary['storage']['mounted'] and summary['storage']['total']>3*1024**3
assert summary['storage']['redundancy']=='JBOD (Btrfs single)'
request('/api/shares',{'name':'JBOD-Test'})
assert any(e['name']=='JBOD-Test' for e in request('/api/files')['entries'])
report=json.loads((root/'acceptance-result.json').read_text())
report['jbod']='Btrfs single-data profile, created and shared on two additional virtual disks'
report['installed_boot']=['BIOS','UEFI']
(root/'acceptance-result.json').write_text(json.dumps(report,indent=2))
print('JBOD creation, capacity, system-managed mount and file sharing passed.',flush=True)
