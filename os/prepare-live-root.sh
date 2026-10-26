#!/bin/bash
set -euo pipefail
work=${HARBOR_ISO_WORK:-/DATA/harbor/iso-build}
target=$work/root
image=/DATA/harbor/release/artifacts/harbor-0.1.0-amd64.img
mkdir -p "$work"
if [ ! -f "$work/root-ready" ]; then
  test ! -e "$target"
  mkdir -p "$target" "$work/image-mount"
  loop=$(losetup --find --show --partscan --read-only "$image")
  case "$loop" in /dev/loop[0-9]*) ;; *) exit 1;; esac
  mount -o ro "${loop}p3" "$work/image-mount"
  trap 'umount "$work/image-mount"; losetup -d "$loop"' EXIT
  rsync -aHAX --numeric-ids "$work/image-mount/" "$target/"
  umount "$work/image-mount"
  losetup -d "$loop"
  trap - EXIT
  touch "$work/root-ready"
fi
test ! -f "$target/var/lib/harbor/admin.json"
mount --bind /dev "$target/dev"
mount --bind /dev/pts "$target/dev/pts"
mount -t proc proc "$target/proc"
mount -t sysfs sysfs "$target/sys"
cleanup() { for path in "$target/sys" "$target/proc" "$target/dev"; do mount --make-rslave "$path"; umount -R "$path"; done; }
trap cleanup EXIT
rm -f "$target/etc/resolv.conf"
cp -L /etc/resolv.conf "$target/etc/resolv.conf"
printf '#!/bin/sh\nexit 101\n' > "$target/usr/sbin/policy-rc.d"
chmod +x "$target/usr/sbin/policy-rc.d"
chroot "$target" /bin/bash -c 'export DEBIAN_FRONTEND=noninteractive; apt-get update; apt-get install -y --no-install-recommends live-boot live-boot-initramfs-tools squashfs-tools grub2-common mtools docker-compose python3-yaml; apt-get clean'
rm -f "$target/usr/sbin/policy-rc.d"
chroot "$target" update-initramfs -u -k all
ln -sf /run/systemd/resolve/stub-resolv.conf "$target/etc/resolv.conf"
printf 'Live root dependencies ready.\n'
