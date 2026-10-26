set -eu
python3 - <<'PY'
import socket,json
s=socket.socket(socket.AF_UNIX);s.connect('/DATA/harbor/graphical-test/qmp.sock');f=s.makefile('rwb',buffering=0);f.readline()
for cmd in ('qmp_capabilities','query-status'):
    f.write((json.dumps({'execute':cmd})+'\n').encode())
    while True:
        value=json.loads(f.readline())
        if 'return' in value:print(value);break
PY
tail -6 /DATA/harbor/graphical-test/serial.log
