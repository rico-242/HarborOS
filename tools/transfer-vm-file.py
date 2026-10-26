"""Copy a fixture to /tmp in the dedicated VM; no host device paths are accepted."""
import base64,json,socket,sys
from pathlib import Path,PurePosixPath
source=Path(sys.argv[1]);destination=sys.argv[2]
if not destination.startswith('/tmp/harbour-') or '..' in PurePosixPath(destination).parts:raise SystemExit('Use a dedicated /tmp/harbour- fixture path')
sock=socket.socket(socket.AF_UNIX);sock.settimeout(30);sock.connect('/DATA/harbor/graphical-test/agent.sock');stream=sock.makefile('rwb',buffering=0)
def command(name,args):
    stream.write((json.dumps({'execute':name,'arguments':args})+'\n').encode())
    while True:
        value=json.loads(stream.readline())
        if 'error' in value:raise RuntimeError(value['error'])
        if 'return' in value:return value['return']
command('guest-sync',{'id':2840});handle=command('guest-file-open',{'path':destination,'mode':'w'})
with source.open('rb') as input_file:
    while chunk:=input_file.read(49152):assert command('guest-file-write',{'handle':handle,'buf-b64':base64.b64encode(chunk).decode()})['count']==len(chunk)
command('guest-file-close',{'handle':handle});stream.close();sock.close()
