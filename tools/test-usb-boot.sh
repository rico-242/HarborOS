set -eu
directory=/DATA/harbor/iso-test
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
(root/'serial.log').rename(root/'serial-installed-uefi.log')
PY
qemu-system-x86_64 -enable-kvm -machine q35 -cpu host -m 4096 -smp 2 \
  -device qemu-xhci -drive if=none,id=usbmedia,format=raw,readonly=on,file=/DATA/harbor/release/artifacts/harbor-0.2.0-amd64.iso \
  -device usb-storage,drive=usbmedia,bootindex=1 \
  -netdev user,id=net0,hostfwd=tcp:127.0.0.1:19443-:8443 -device virtio-net-pci,netdev=net0 -display none \
  -chardev socket,id=serial0,path="$directory/serial.sock",server=on,wait=off,logfile="$directory/serial.log" \
  -serial chardev:serial0 -qmp unix:"$directory/qmp.sock",server=on,wait=off -daemonize -pidfile "$directory/guest.pid"
python3 - <<'PY'
from pathlib import Path
import json,time
root=Path('/DATA/harbor/iso-test')
deadline=time.monotonic()+150
while time.monotonic()<deadline:
    text=(root/'serial.log').read_text(errors='replace')
    if 'LIVE / INSTALL' in text and 'First-time setup code:' in text:
        report=json.loads((root/'acceptance-result.json').read_text())
        report['hybrid_usb_boot']='Legacy BIOS, read-only USB storage device, no destination disks attached'
        (root/'acceptance-result.json').write_text(json.dumps(report,indent=2))
        print('Final hybrid ISO booted from USB storage under legacy BIOS.')
        break
    time.sleep(2)
else:raise RuntimeError('USB boot failed: '+text[-2500:])
PY
