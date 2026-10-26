set -eu
python3 - <<'PY'
import json,socket,time
from pathlib import Path
root=Path('/DATA/harbor/iso-test')
destination=Path('/DATA/harbor/iso-test-first')
assert not destination.exists()
s=socket.socket(socket.AF_UNIX);s.connect(str(root/'qmp.sock'));f=s.makefile('rwb',buffering=0);f.readline()
for command in ('qmp_capabilities','quit'):
    f.write((json.dumps({'execute':command})+'\n').encode())
    while True:
        line=f.readline()
        if not line or 'return' in json.loads(line):break
s.close();time.sleep(1)
root.rename(destination)
print('First disposable VM retained for diagnostics. The final ISO test will use new virtual disks.')
PY
