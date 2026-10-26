set -eu
directory=/DATA/harbor/iso-test
test -f "$directory/install-result.json"
python3 - <<'PY'
import json,socket,time
from pathlib import Path
root=Path('/DATA/harbor/iso-test')
s=socket.socket(socket.AF_UNIX);s.connect(str(root/'qmp.sock'));f=s.makefile('rwb',buffering=0);f.readline()
for command in ('qmp_capabilities','quit'):
    f.write((json.dumps({'execute':command})+'\n').encode())
    while True:
        line=f.readline()
        if not line or 'return' in json.loads(line):break
s.close()
time.sleep(1)
(root/'guest.pid').unlink(missing_ok=True)
(root/'serial.log').rename(root/'serial-live-install.log')
PY
qemu-system-x86_64 -enable-kvm -machine q35 -cpu host -m 4096 -smp 2 \
  -drive file="$directory/system.qcow2",if=none,id=system,format=qcow2 -device virtio-blk-pci,drive=system,serial=HARBOR_TEST_SYSTEM \
  -drive file="$directory/data1.qcow2",if=none,id=data1,format=qcow2 -device virtio-blk-pci,drive=data1,serial=HARBOR_TEST_DATA1 \
  -drive file="$directory/data2.qcow2",if=none,id=data2,format=qcow2 -device virtio-blk-pci,drive=data2,serial=HARBOR_TEST_DATA2 \
  -drive file="$directory/data3.qcow2",if=none,id=data3,format=qcow2 -device virtio-blk-pci,drive=data3,serial=HARBOR_TEST_DATA3 \
  -drive file="$directory/data4.qcow2",if=none,id=data4,format=qcow2 -device virtio-blk-pci,drive=data4,serial=HARBOR_TEST_DATA4 \
  -netdev user,id=net0,hostfwd=tcp:127.0.0.1:19443-:8443,hostfwd=tcp:127.0.0.1:19222-:22 \
  -device virtio-net-pci,netdev=net0 -display none \
  -chardev socket,id=serial0,path="$directory/serial.sock",server=on,wait=off,logfile="$directory/serial.log" \
  -serial chardev:serial0 -qmp unix:"$directory/qmp.sock",server=on,wait=off -daemonize -pidfile "$directory/guest.pid"
printf 'Installed Harbor boot started in legacy BIOS mode, with the ISO removed.\n'
