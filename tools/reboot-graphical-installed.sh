set -eu
python3 - <<'PY'
import json,socket,time
from pathlib import Path
root=Path('/DATA/harbor/graphical-test')
if (root/'qmp.sock').exists():
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
assert not (root/'guest.pid').exists(),'Test VM did not shut down cleanly'
(root/'guest.pid').unlink(missing_ok=True)
(root/'serial.log').rename(root/'serial-previous.log')
PY
directory=/DATA/harbor/graphical-test
system_disk=${HARBOR_TEST_SYSTEM_DISK:-system.qcow2}
case "$system_disk" in system.qcow2|final-system.qcow2) ;; *) exit 1;; esac
set --
if [ "${HARBOR_TEST_BIOS:-0}" != 1 ]; then
  set -- -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd -drive if=pflash,format=raw,file="$directory/vars.fd"
fi
qemu-system-x86_64 -enable-kvm -machine q35 -cpu host -m 4096 -smp 2 \
  "$@" \
  -drive file="$directory/$system_disk",if=none,id=system,format=qcow2 -device virtio-blk-pci,drive=system,serial=HARBOUR_GUI_SYSTEM \
  -drive file="$directory/data1.qcow2",if=none,id=data1,format=qcow2 -device virtio-blk-pci,drive=data1,serial=HARBOUR_GUI_DATA1 \
  -drive file="$directory/data2.qcow2",if=none,id=data2,format=qcow2 -device virtio-blk-pci,drive=data2,serial=HARBOUR_GUI_DATA2 \
  -netdev user,id=net0,hostfwd=tcp:127.0.0.1:20443-:8443,hostfwd=tcp:127.0.0.1:20222-:22 \
  -device virtio-net-pci,netdev=net0 -netdev user,id=net1 -device virtio-net-pci,netdev=net1,mac=52:54:00:11:22:02 -vga virtio -vnc unix:"$directory/vnc.sock" \
  -device virtio-serial-pci -chardev socket,path="$directory/agent.sock",server=on,wait=off,id=agent0 \
  -device virtserialport,chardev=agent0,name=org.qemu.guest_agent.0 \
  -chardev socket,id=serial0,path="$directory/serial.sock",server=on,wait=off,logfile="$directory/serial.log" \
  -serial chardev:serial0 -qmp unix:"$directory/qmp.sock",server=on,wait=off -daemonize -pidfile "$directory/guest.pid"
printf 'Installed graphical VM started without installation media.\n'
