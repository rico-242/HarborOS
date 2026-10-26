set -eu
python3 - <<'PY'
import json,socket,time
from pathlib import Path
root=Path('/DATA/harbor/iso-test')
s=socket.socket(socket.AF_UNIX);s.connect(str(root/'qmp.sock'));f=s.makefile('rwb',buffering=0);f.readline()
for command in ('qmp_capabilities','system_powerdown'):
    f.write((json.dumps({'execute':command})+'\n').encode())
    while True:
        line=f.readline()
        if not line or 'return' in json.loads(line):break
s.close()
deadline=time.monotonic()+40
while time.monotonic()<deadline and (root/'guest.pid').exists():time.sleep(1)
assert not (root/'guest.pid').exists(),'VM did not shut down cleanly'
print('Disposable test VM shut down; virtual disks and acceptance report retained.')
PY
