set -eu
docker run --rm --privileged -v /DATA/harbor/rootfs:/target --entrypoint /bin/bash harbor-image-builder:0.1 -c '
set -euo pipefail
mount --bind /dev /target/dev
mount -t proc proc /target/proc
mount -t sysfs sysfs /target/sys
trap '\''umount /target/dev /target/proc /target/sys'\'' EXIT
chroot /target update-initramfs -u -k all
'
