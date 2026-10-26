#!/bin/bash
set -euo pipefail
image=/work/vm/subdir.img
test ! -e "$image"
truncate -s 8G "$image"
loop=$(losetup --find --show "$image")
case "$loop" in /dev/loop[0-9]*) ;; *) exit 1;; esac
mkfs.ext4 -F "$loop"
mkdir -p /mnt/subdir
mount "$loop" /mnt/subdir
trap 'umount /mnt/subdir; losetup -d "$loop"' EXIT
mkdir -p /mnt/subdir/harbor/rootfs
rsync -aHAX --numeric-ids --exclude=/proc/*** --exclude=/sys/*** --exclude=/dev/*** --exclude=/run/*** --exclude=/tmp/*** --exclude=/mnt/harbor-host/*** /target/ /mnt/subdir/harbor/rootfs/
root=/mnt/subdir/harbor/rootfs
mkdir -p "$root/proc" "$root/sys" "$root/dev" "$root/run" "$root/tmp"
chmod 1777 "$root/tmp"
rm -f "$root"/etc/ssh/ssh_host_* "$root"/var/lib/harbor/admin.json "$root"/var/lib/harbor/setup-token "$root"/var/lib/harbor/tls.key "$root"/var/lib/harbor/tls.crt
printf '/dev/vda / ext4 defaults 0 1\nLABEL=harbor-data /srv/harbor/storage btrfs defaults,nofail 0 0\n' > "$root/etc/fstab"
cp "$(ls /target/boot/vmlinuz-* | sort -V | tail -1)" /work/vm/subdir-vmlinuz
cp "$(ls /target/boot/initrd.img-* | sort -V | tail -1)" /work/vm/subdir-initrd
sync -f "$image"
printf 'Directory-root test disk created.\n'
