"""Execute acceptance checks inside the dedicated disposable graphical VM."""
import base64,json,socket,time,sys
from pathlib import Path
root=Path('/DATA/harbor/hybrid-test')
sock=socket.socket(socket.AF_UNIX);sock.settimeout(30);sock.connect(str(root/'agent.sock'))
stream=sock.makefile('rwb',buffering=0)
def command(name,args=None):
    stream.write((json.dumps({'execute':name,'arguments':args or {}})+'\n').encode())
    while True:
        line=stream.readline()
        if not line:raise RuntimeError('Guest agent closed')
        value=json.loads(line)
        if 'error' in value:raise RuntimeError(value['error'])
        if 'return' in value:return value['return']
command('guest-sync',{'id':1703})
script=Path(sys.argv[1]).read_text()
if len(sys.argv)>2 and sys.argv[2]=='--sandbox':
    script='import os;os.environ["HYBRID_SANDBOX_TEST"]="1"\n'+script
    launch=['--wait','--pipe','--collect','--unit=harbour-hybrid-acceptance','--property=ProtectHome=yes','--property=ProtectKernelTunables=yes','--property=ProtectKernelModules=yes','--property=ProtectControlGroups=yes','--property=NoNewPrivileges=yes','--property=PrivateTmp=yes','--property=UMask=0077','/usr/bin/python3','-c',script]
    process=command('guest-exec',{'path':'/usr/bin/systemd-run','arg':launch,'capture-output':True})
else:
    process=command('guest-exec',{'path':'/usr/bin/python3','arg':['-c',script],'capture-output':True})
while True:
    result=command('guest-exec-status',{'pid':process['pid']})
    if result['exited']:break
    time.sleep(.5)
for key in ('out-data','err-data'):
    if result.get(key):print(base64.b64decode(result[key]).decode(errors='replace'),end='')
sys.exit(result.get('exitcode',1))
