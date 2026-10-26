set -eu
directory=/DATA/harbor/graphical-test
iso_name=${HARBOR_TEST_ISO:-harbour-0.3.0-amd64.iso}
case "$iso_name" in harbour-0.3.0-amd64.iso|harbour-0.3.1-amd64.iso) ;; *) exit 1;; esac
python3 - <<'PY'
import json,socket,time
from pathlib import Path
root=Path('/DATA/harbor/graphical-test')
s=socket.socket(socket.AF_UNIX);s.connect(str(root/'qmp.sock'));f=s.makefile('rwb',buffering=0);f.readline()
for command in ('qmp_capabilities','system_powerdown'):
    f.write((json.dumps({'execute':command})+'\n').encode())
    while True:
        line=f.readline()
        if not line or 'return' in json.loads(line):break
s.close()
for _ in range(45):
    if not (root/'guest.pid').exists():break
    time.sleep(1)
assert not (root/'guest.pid').exists()
(root/'serial.log').rename(root/'serial-bios-installed.log')
PY
qemu-system-x86_64 -enable-kvm -machine q35 -cpu host -m 4096 -smp 2 \
  -device qemu-xhci -drive if=none,id=usbmedia,format=raw,readonly=on,file="/DATA/harbor/release/artifacts/$iso_name" \
  -device usb-storage,drive=usbmedia,bootindex=1 \
  -netdev user,id=net0,hostfwd=tcp:127.0.0.1:20443-:8443 -device virtio-net-pci,netdev=net0 \
  -vga virtio -vnc unix:"$directory/vnc.sock" \
  -device virtio-serial-pci -chardev socket,path="$directory/agent.sock",server=on,wait=off,id=agent0 \
  -device virtserialport,chardev=agent0,name=org.qemu.guest_agent.0 \
  -chardev socket,id=serial0,path="$directory/serial.sock",server=on,wait=off,logfile="$directory/serial.log" \
  -serial chardev:serial0 -qmp unix:"$directory/qmp.sock",server=on,wait=off -daemonize -pidfile "$directory/guest.pid"
printf 'Final ISO booting as a raw USB device under legacy BIOS, with no destination disks attached.\n'
