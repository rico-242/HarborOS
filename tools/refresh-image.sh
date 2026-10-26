set -eu
tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
cp -a /DATA/harbor/source/harbor/. /DATA/harbor/rootfs/opt/harbor/
# Shut down the disposable VM through its dedicated QMP socket.
python3 - <<'PY'
import json, socket, time
s=socket.socket(socket.AF_UNIX)
s.connect('/DATA/harbor/vm/qmp.sock')
f=s.makefile('rwb', buffering=0)
f.readline()
for command in ('qmp_capabilities','quit'):
    f.write((json.dumps({'execute':command})+'\n').encode())
    while True:
        line=f.readline()
        if not line or 'return' in json.loads(line): break
s.close()
time.sleep(1)
PY
mv /DATA/harbor/vm/boot.qcow2 /DATA/harbor/vm/boot-first-test.qcow2
mv /DATA/harbor/vm/serial.log /DATA/harbor/vm/serial-first-test.log
rm -f /DATA/harbor/vm/harbor.pid
docker run --rm --privileged -v /dev:/dev -v /DATA/harbor:/work --entrypoint /bin/bash harbor-image-builder:0.1 -c '
set -euo pipefail
image=/work/artifacts/harbor-0.1.0-amd64.img
loop=$(losetup --find --show --partscan "$image")
mkdir -p /mnt/image
mount "${loop}p3" /mnt/image
trap '\''umount /mnt/image; losetup -d "$loop"'\'' EXIT
cp -a /work/source/harbor/. /mnt/image/opt/harbor/
mkdir -p /mnt/image/etc/systemd/system/ssh.service.d
printf "[Unit]\nAfter=harbor.service\n" > /mnt/image/etc/systemd/system/ssh.service.d/harbor.conf
sync -f "$image"
'
qemu-img create -f qcow2 -F raw -b /DATA/harbor/artifacts/harbor-0.1.0-amd64.img /DATA/harbor/vm/boot.qcow2
qemu-system-x86_64 -enable-kvm -machine q35 -cpu host -m 3072 -smp 2 -drive file=/DATA/harbor/vm/boot.qcow2,if=virtio,format=qcow2 -drive file=/DATA/harbor/vm/data.img,if=virtio,format=raw -netdev user,id=net0,hostfwd=tcp:127.0.0.1:18443-:8443,hostfwd=tcp:127.0.0.1:12222-:22,hostfwd=tcp:127.0.0.1:1445-:445 -device virtio-net-pci,netdev=net0 -display none -serial file:/DATA/harbor/vm/serial.log -qmp unix:/DATA/harbor/vm/qmp.sock,server=on,wait=off -daemonize -pidfile /DATA/harbor/vm/harbor.pid
printf 'Refreshed Harbor VM started.\n'
