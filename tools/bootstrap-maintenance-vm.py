"""Install the updater bridge only in the dedicated disposable VM."""
import socket,json,base64,time,sys
from pathlib import Path
source=Path('/DATA/harbor/source');root=Path('/DATA/harbor/graphical-test')
sock=socket.socket(socket.AF_UNIX);sock.settimeout(30);sock.connect(str(root/'agent.sock'));stream=sock.makefile('rwb',buffering=0)
def command(name,args=None):
    stream.write((json.dumps({'execute':name,'arguments':args or {}})+'\n').encode())
    while True:
        value=json.loads(stream.readline())
        if 'error' in value:raise RuntimeError(value['error'])
        if 'return' in value:return value['return']
def execute(script):
    job=command('guest-exec',{'path':'/usr/bin/python3','arg':['-c',script],'capture-output':True})
    while True:
        result=command('guest-exec-status',{'pid':job['pid']})
        if result['exited']:break
        time.sleep(.2)
    if result.get('exitcode'):
        raise RuntimeError(base64.b64decode(result.get('err-data','')).decode())
    if result.get('out-data'):print(base64.b64decode(result['out-data']).decode(),end='')
def upload(local,dest):
    handle=command('guest-file-open',{'path':dest,'mode':'w'})
    with local.open('rb') as data:
        while chunk:=data.read(49152):command('guest-file-write',{'handle':handle,'buf-b64':base64.b64encode(chunk).decode()})
    command('guest-file-close',{'handle':handle})
command('guest-sync',{'id':1740})
execute("from pathlib import Path; assert Path('/sys/class/dmi/id/product_name').read_text().startswith('Standard PC'); [Path('/tmp/harbour-maintenance-source/'+p).mkdir(parents=True,exist_ok=True) for p in ('os','harbor')]")
support_only='--support-only' in sys.argv
if not support_only:
    for path in (source/'harbor').rglob('*'):
        if path.is_file() and path.suffix in ('.py','.js','.css','.html') and '__pycache__' not in path.parts:upload(path,'/opt/harbor/'+path.relative_to(source/'harbor').as_posix())
for name in ('release_bundle.py','release_worker.py'):upload(source/'harbor'/name,'/tmp/harbour-maintenance-source/harbor/'+name)
for name in ('install-maintenance.sh','release-public.pem','harbour-release-update','harbour-network-change','harbour-package-update','harbour-update-recover.service','harbour-network-recover.service','harbor.service'):upload(source/'os'/name,'/tmp/harbour-maintenance-source/os/'+name)
upload(Path('/tmp/harbour-0.4.0-update.bundle'),'/tmp/harbour-0.4.0-update.bundle')
if not support_only:execute("from pathlib import Path; p=Path('/opt/harbor/server.py');p.write_text(p.read_text().replace(\"VERSION = '0.4.0'\",\"VERSION = '0.3.1'\"))")
execute("""from pathlib import Path
import subprocess
subprocess.run(['sh','/tmp/harbour-maintenance-source/os/install-maintenance.sh','/tmp/harbour-maintenance-source','/'],check=True)
subprocess.run(['install','-m','644','/tmp/harbour-maintenance-source/os/harbor.service','/etc/systemd/system/harbor.service'],check=True)
subprocess.run(['systemctl','daemon-reload'],check=True)
subprocess.run(['systemctl','start','harbour-update-recover'],check=True)
subprocess.run(['systemctl','restart','harbor'],check=True)
print('Maintenance support installed in the disposable VM.')
""")
