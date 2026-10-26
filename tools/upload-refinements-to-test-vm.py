"""Copy the changed application files into the dedicated disposable VM via QGA."""
import socket,json,base64,time
from pathlib import Path
root=Path('/DATA/harbor/graphical-test');source=Path('/DATA/harbor/source/harbor')
sock=socket.socket(socket.AF_UNIX);sock.settimeout(30);sock.connect(str(root/'agent.sock'));stream=sock.makefile('rwb',buffering=0)
def command(name,args=None):
    stream.write((json.dumps({'execute':name,'arguments':args or {}})+'\n').encode())
    while True:
        value=json.loads(stream.readline())
        if 'error' in value:raise RuntimeError(value['error'])
        if 'return' in value:return value['return']
command('guest-sync',{'id':1731})
files=[p for p in source.rglob('*') if p.is_file() and p.suffix in ('.py','.js','.css','.html') and '__pycache__' not in p.parts]
for path in files:
    dest='/opt/harbor/'+path.relative_to(source).as_posix()
    handle=command('guest-file-open',{'path':dest,'mode':'w'})
    with path.open('rb') as data:
        while chunk:=data.read(49152):
            result=command('guest-file-write',{'handle':handle,'buf-b64':base64.b64encode(chunk).decode()});assert result['count']==len(chunk)
    command('guest-file-close',{'handle':handle})
process=command('guest-exec',{'path':'/usr/bin/systemctl','arg':['restart','harbor'],'capture-output':True})
for _ in range(40):
    status=command('guest-exec-status',{'pid':process['pid']})
    if status['exited']:assert status.get('exitcode')==0,status;break
    time.sleep(.5)
else:raise RuntimeError('Test service did not restart')
print('Changed application files loaded into the disposable VM.')
