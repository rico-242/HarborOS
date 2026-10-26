set -eu
root=/DATA/harbor/rootfs
mkdir -p "$root/etc/initramfs/post-update.d"
install -m 755 /DATA/harbor/source/os/harbor-kernel-update "$root/etc/initramfs/post-update.d/harbor-boot"
kernel=$(basename "$(ls "$root"/boot/vmlinuz-* | sort -V | tail -1)")
version=${kernel#vmlinuz-}
chroot "$root" /etc/initramfs/post-update.d/harbor-boot "$version"
ls -l "$root/boot/harbor-vmlinuz" "$root/boot/harbor-initrd"
