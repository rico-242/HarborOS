"""Exercise the interactive installer over the dedicated disposable VM console."""
from pathlib import Path
import json
import socket
import time

root=Path('/DATA/harbor/iso-test')
assert 'LIVE / INSTALL' in (root/'serial.log').read_text(errors='replace')
sock=socket.socket(socket.AF_UNIX)
sock.connect(str(root/'serial.sock'))
sock.settimeout(1)
sock.sendall(b'1\n')
received=b''
deadline=time.monotonic()+240
confirmed=False
selected=False
while time.monotonic()<deadline:
    try:
        chunk=sock.recv(65536)
    except socket.timeout:
        continue
    if not chunk:break
    received+=chunk
    if not selected and b'Destination number (Enter cancels):' in received:
        sock.sendall(b'1\n')
        selected=True
    if not confirmed and b'Type ERASE HARBOR_TEST_SYSTEM to install:' in received:
        assert b'/dev/disk/by-id/virtio-HARBOR_TEST_SYSTEM' in received
        sock.sendall(b'ERASE HARBOR_TEST_SYSTEM\n')
        confirmed=True
        print('Confirmed only the disposable HARBOR_TEST_SYSTEM disk.',flush=True)
    if b'INSTALLATION COMPLETE.' in received:
        (root/'install-result.json').write_text(json.dumps({'live_boot':'UEFI','installed':True,'target_serial':'HARBOR_TEST_SYSTEM'}))
        print('Interactive offline installation completed.',flush=True)
        break
    if b'Installation stopped:' in received or b'Cancelled.' in received:
        raise RuntimeError(received.decode(errors='replace')[-2500:])
else:
    raise RuntimeError('Installer timed out: '+received.decode(errors='replace')[-2500:])
sock.close()
assert confirmed and b'INSTALLATION COMPLETE.' in received
