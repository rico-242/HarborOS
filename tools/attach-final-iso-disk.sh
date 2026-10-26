set -eu
python3 - <<'PY'
import json,socket
from pathlib import Path
root=Path('/DATA/harbor/graphical-test')
s=socket.socket(socket.AF_UNIX);s.connect(str(root/'qmp.sock'));f=s.makefile('rwb',buffering=0);f.readline()
for command in [{'execute':'qmp_capabilities'},{'execute':'device_add','arguments':{'driver':'usb-storage','drive':'finaldisk','id':'finalsystem','serial':'HARBOUR_GUI_SYSTEM'}}]:
    f.write((json.dumps(command)+'\n').encode())
    while True:
        result=json.loads(f.readline())
        if 'error' in result:raise RuntimeError(result['error'])
        if 'return' in result:break
s.close()
PY
sleep 2
python3 /tmp/harbour-guest-agent.py /tmp/harbour-guest-graphical-install.py
