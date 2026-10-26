set -eu
directory=/DATA/harbor/graphical-test
mkdir -p "$directory"
test ! -e "$directory/guest.pid"
for disk in system data1 data2; do
  size=2G; if [ "$disk" = system ]; then size=24G; fi
  if [ ! -e "$directory/$disk.qcow2" ]; then qemu-img create -f qcow2 "$directory/$disk.qcow2" "$size"; fi
done
cp /usr/share/OVMF/OVMF_VARS_4M.fd "$directory/vars.fd"
qemu-system-x86_64 -enable-kvm -machine q35 -cpu host -m 4096 -smp 2 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
  -drive if=pflash,format=raw,file="$directory/vars.fd" \
  -drive file="$directory/system.qcow2",if=none,id=system,format=qcow2 -device virtio-blk-pci,drive=system,serial=HARBOUR_GUI_SYSTEM \
  -drive file="$directory/data1.qcow2",if=none,id=data1,format=qcow2 -device virtio-blk-pci,drive=data1,serial=HARBOUR_GUI_DATA1 \
  -drive file="$directory/data2.qcow2",if=none,id=data2,format=qcow2 -device virtio-blk-pci,drive=data2,serial=HARBOUR_GUI_DATA2 \
  -cdrom /DATA/harbor/release/artifacts/harbour-0.3.0-amd64.iso -boot order=d \
  -netdev user,id=net0,hostfwd=tcp:127.0.0.1:20443-:8443,hostfwd=tcp:127.0.0.1:20222-:22 \
  -device virtio-net-pci,netdev=net0 -vga virtio -vnc unix:"$directory/vnc.sock" \
  -device virtio-serial-pci -chardev socket,path="$directory/agent.sock",server=on,wait=off,id=agent0 \
  -device virtserialport,chardev=agent0,name=org.qemu.guest_agent.0 \
  -chardev socket,id=serial0,path="$directory/serial.sock",server=on,wait=off,logfile="$directory/serial.log" \
  -serial chardev:serial0 -qmp unix:"$directory/qmp.sock",server=on,wait=off -daemonize -pidfile "$directory/guest.pid"
if ! test -f /usr/share/novnc/vnc.html; then DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends novnc websockify; fi
systemd-run --unit=harbour-test-vnc --collect /usr/bin/websockify --web=/usr/share/novnc --unix-target="$directory/vnc.sock" 127.0.0.1:20608
printf 'Graphical test VM started; VNC is accessible only through SSH.\n'
