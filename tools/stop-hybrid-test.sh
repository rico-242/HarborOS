set -eu
python3 - <<'PY'
import json,socket,time,os
from pathlib import Path
root=Path('/DATA/harbor/hybrid-test')
s=socket.socket(socket.AF_UNIX);s.connect(str(root/'qmp.sock'));f=s.makefile('rwb',buffering=0);f.readline()
for command in ('qmp_capabilities','system_powerdown'):
 f.write((json.dumps({'execute':command})+'\n').encode())
 while True:
  line=f.readline()
  if not line or 'return' in json.loads(line):break
s.close()
for _ in range(60):
 if not (root/'guest.pid').exists():break
 time.sleep(1)
assert not (root/'guest.pid').exists(),'Disposable VM did not stop'
print('Disposable hybrid VM shut down cleanly.')
PY
