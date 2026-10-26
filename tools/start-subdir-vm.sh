set -eu
test "$(docker inspect -f '{{.State.ExitCode}}' harbor-subdir-build)" = 0
python3 /DATA/harbor/source/tools/stop-vm.py
mv /DATA/harbor/vm/serial.log /DATA/harbor/vm/serial-disk-test.log
qemu-system-x86_64 -enable-kvm -machine q35 -cpu host -m 3072 -smp 2 -kernel /DATA/harbor/vm/subdir-vmlinuz -initrd /DATA/harbor/vm/subdir-initrd -append 'root=/dev/vda rw rootwait harbor.subdir=harbor/rootfs console=ttyS0,115200n8 panic=30' -drive file=/DATA/harbor/vm/subdir.img,if=virtio,format=raw -drive file=/DATA/harbor/vm/data.img,if=virtio,format=raw -netdev user,id=net0,hostfwd=tcp:127.0.0.1:18443-:8443,hostfwd=tcp:127.0.0.1:12222-:22,hostfwd=tcp:127.0.0.1:1445-:445 -device virtio-net-pci,netdev=net0 -display none -serial file:/DATA/harbor/vm/serial.log -qmp unix:/DATA/harbor/vm/qmp.sock,server=on,wait=off -daemonize -pidfile /DATA/harbor/vm/harbor.pid
printf 'Directory-root Harbor VM started.\n'
