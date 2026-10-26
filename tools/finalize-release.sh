set -eu
test "$(docker inspect -f '{{.State.ExitCode}}' harbor-release)" = 0
test "$(docker inspect -f '{{.State.ExitCode}}' harbor-initrd-fix)" = 0
docker run -d --name harbor-release-final --privileged -v /dev:/dev -v /DATA/harbor/release:/work -v /DATA/harbor/rootfs:/target:ro --entrypoint /bin/bash harbor-image-builder:0.1 -c '
set -euo pipefail
image=/work/artifacts/harbor-0.1.0-amd64.img
loop=$(losetup --find --show --partscan "$image")
mkdir -p /mnt/image
mount "${loop}p3" /mnt/image
cleanup() { umount /mnt/image; losetup -d "$loop"; }
trap cleanup EXIT
rsync -aHAX --numeric-ids --exclude=/etc/fstab --exclude=/boot/grub/*** --exclude=/boot/efi/*** --exclude=/proc/*** --exclude=/sys/*** --exclude=/dev/*** --exclude=/run/*** --exclude=/tmp/*** --exclude=/mnt/harbor-host/*** /target/ /mnt/image/
rm -f /mnt/image/etc/ssh/ssh_host_* /mnt/image/var/lib/harbor/admin.json /mnt/image/var/lib/harbor/setup-token /mnt/image/var/lib/harbor/tls.key /mnt/image/var/lib/harbor/tls.crt
test -f /mnt/image/boot/harbor-initrd
test -x /mnt/image/usr/bin/docker
test -x /mnt/image/usr/bin/busybox
sync -f "$image"
cleanup
trap - EXIT
cd /work/artifacts
sha256sum harbor-0.1.0-amd64.img > harbor-0.1.0-amd64.img.sha256
zstd -T2 -3 -f --keep harbor-0.1.0-amd64.img
sha256sum harbor-0.1.0-amd64.img.zst > harbor-0.1.0-amd64.img.zst.sha256
echo "Release image finalized."
'
