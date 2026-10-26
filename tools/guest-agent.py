"""Execute acceptance checks inside the dedicated disposable graphical VM."""
import base64,json,socket,time,sys
from pathlib import Path
root=Path('/DATA/harbor/graphical-test')
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
process=command('guest-exec',{'path':'/usr/bin/python3','arg':['-c',script],'capture-output':True})
while True:
    result=command('guest-exec-status',{'pid':process['pid']})
    if result['exited']:break
    time.sleep(.5)
for key in ('out-data','err-data'):
    if result.get(key):print(base64.b64decode(result[key]).decode(errors='replace'),end='')
sys.exit(result.get('exitcode',1))
