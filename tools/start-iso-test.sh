set -eu
directory=/DATA/harbor/iso-test
mkdir -p "$directory"
test ! -e "$directory/guest.pid"
test -f /DATA/harbor/release/artifacts/harbor-0.2.0-amd64.iso
for disk in system data1 data2 data3 data4; do
  size=2G
  if [ "$disk" = system ]; then size=24G; fi
  if [ ! -e "$directory/$disk.qcow2" ]; then qemu-img create -f qcow2 "$directory/$disk.qcow2" "$size"; fi
done
cp /usr/share/OVMF/OVMF_VARS_4M.fd "$directory/vars.fd"
qemu-system-x86_64 -enable-kvm -machine q35 -cpu host -m 4096 -smp 2 \
  -drive if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd \
  -drive if=pflash,format=raw,file="$directory/vars.fd" \
  -drive file="$directory/system.qcow2",if=none,id=system,format=qcow2 -device virtio-blk-pci,drive=system,serial=HARBOR_TEST_SYSTEM \
  -drive file="$directory/data1.qcow2",if=none,id=data1,format=qcow2 -device virtio-blk-pci,drive=data1,serial=HARBOR_TEST_DATA1 \
  -drive file="$directory/data2.qcow2",if=none,id=data2,format=qcow2 -device virtio-blk-pci,drive=data2,serial=HARBOR_TEST_DATA2 \
  -drive file="$directory/data3.qcow2",if=none,id=data3,format=qcow2 -device virtio-blk-pci,drive=data3,serial=HARBOR_TEST_DATA3 \
  -drive file="$directory/data4.qcow2",if=none,id=data4,format=qcow2 -device virtio-blk-pci,drive=data4,serial=HARBOR_TEST_DATA4 \
  -cdrom /DATA/harbor/release/artifacts/harbor-0.2.0-amd64.iso -boot order=d \
  -netdev user,id=net0,hostfwd=tcp:127.0.0.1:19443-:8443,hostfwd=tcp:127.0.0.1:19222-:22 \
  -device virtio-net-pci,netdev=net0 -display none \
  -chardev socket,id=serial0,path="$directory/serial.sock",server=on,wait=off,logfile="$directory/serial.log" \
  -serial chardev:serial0 -qmp unix:"$directory/qmp.sock",server=on,wait=off -daemonize -pidfile "$directory/guest.pid"
printf 'UEFI live-ISO VM started with five disposable virtual disks.\n'
