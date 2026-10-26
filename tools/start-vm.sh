set -eu
umask 077
test -f /DATA/harbor/artifacts/harbor-0.1.0-amd64.img
test ! -e /DATA/harbor/vm/harbor.pid
qemu-img create -f qcow2 -F raw -b /DATA/harbor/artifacts/harbor-0.1.0-amd64.img /DATA/harbor/vm/boot.qcow2
truncate -s 4G /DATA/harbor/vm/data.img
mkfs.btrfs -f -L harbor-data /DATA/harbor/vm/data.img
qemu-system-x86_64 -enable-kvm -machine q35 -cpu host -m 3072 -smp 2 -drive file=/DATA/harbor/vm/boot.qcow2,if=virtio,format=qcow2 -drive file=/DATA/harbor/vm/data.img,if=virtio,format=raw -netdev user,id=net0,hostfwd=tcp:127.0.0.1:18443-:8443,hostfwd=tcp:127.0.0.1:12222-:22,hostfwd=tcp:127.0.0.1:1445-:445 -device virtio-net-pci,netdev=net0 -display none -serial file:/DATA/harbor/vm/serial.log -qmp unix:/DATA/harbor/vm/qmp.sock,server=on,wait=off -daemonize -pidfile /DATA/harbor/vm/harbor.pid
printf 'Harbor VM started.\n'
