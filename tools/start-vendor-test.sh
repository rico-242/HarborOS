set -eu
test "$(docker inspect -f '{{.State.ExitCode}}' harbor-vendor-test-build)" = 0
cp /usr/share/qemu/edk2-i386-vars.fd /DATA/harbor/vm/vendor-vars.fd
if [ -f /DATA/harbor/vm/serial.log ]; then mv /DATA/harbor/vm/serial.log /DATA/harbor/vm/serial-subdir-success.log; fi
qemu-system-x86_64 -enable-kvm -machine q35 -cpu host -m 3072 -smp 2 -drive if=pflash,format=raw,readonly=on,file=/usr/share/qemu/edk2-x86_64-code.fd -drive if=pflash,format=raw,file=/DATA/harbor/vm/vendor-vars.fd -drive file=/DATA/harbor/vm/vendor-efi.img,if=virtio,format=raw -drive file=/DATA/harbor/vm/data.img,if=virtio,format=raw -netdev user,id=net0,hostfwd=tcp:127.0.0.1:18443-:8443,hostfwd=tcp:127.0.0.1:12222-:22,hostfwd=tcp:127.0.0.1:1445-:445 -device virtio-net-pci,netdev=net0 -display none -serial file:/DATA/harbor/vm/serial.log -qmp unix:/DATA/harbor/vm/qmp.sock,server=on,wait=off -daemonize -pidfile /DATA/harbor/vm/harbor.pid
printf 'Vendor EFI bootloader VM started.\n'
