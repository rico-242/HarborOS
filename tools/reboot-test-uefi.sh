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
(root/'serial.log').rename(root/'serial-installed-bios.log')
PY
qemu-system-x86_64 -enable-kvm -machine q35 -cpu host -m 4096 -smp 2 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
  -drive if=pflash,format=raw,file="$directory/vars.fd" \
  -drive file="$directory/system.qcow2",if=none,id=system,format=qcow2 -device virtio-blk-pci,drive=system,serial=HARBOR_TEST_SYSTEM \
  -drive file="$directory/data1.qcow2",if=none,id=data1,format=qcow2 -device virtio-blk-pci,drive=data1,serial=HARBOR_TEST_DATA1 \
  -drive file="$directory/data2.qcow2",if=none,id=data2,format=qcow2 -device virtio-blk-pci,drive=data2,serial=HARBOR_TEST_DATA2 \
  -drive file="$directory/data3.qcow2",if=none,id=data3,format=qcow2 -device virtio-blk-pci,drive=data3,serial=HARBOR_TEST_DATA3 \
  -drive file="$directory/data4.qcow2",if=none,id=data4,format=qcow2 -device virtio-blk-pci,drive=data4,serial=HARBOR_TEST_DATA4 \
  -netdev user,id=net0,hostfwd=tcp:127.0.0.1:19443-:8443,hostfwd=tcp:127.0.0.1:19222-:22,hostfwd=tcp:127.0.0.1:19384-:8384 \
  -device virtio-net-pci,netdev=net0 -display none \
  -chardev socket,id=serial0,path="$directory/serial.sock",server=on,wait=off,logfile="$directory/serial.log" \
  -serial chardev:serial0 -qmp unix:"$directory/qmp.sock",server=on,wait=off -daemonize -pidfile "$directory/guest.pid"
printf 'Installed Harbor boot started in UEFI mode with its RAID1 data disks.\n'
