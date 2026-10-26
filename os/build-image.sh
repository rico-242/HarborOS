#!/bin/bash
# Run in the builder container with /target=rootfs and /work=build directory.
set -euo pipefail
image=/work/artifacts/harbor-0.1.0-amd64.img
test ! -e "$image" || { echo 'Image already exists; choose a new output directory.'; exit 1; }
truncate -s 12G "$image"
parted -s "$image" mklabel gpt mkpart BIOS 1MiB 3MiB set 1 bios_grub on mkpart ESP fat32 3MiB 259MiB set 2 esp on mkpart harbor-root ext4 259MiB 100%
loop=$(losetup --find --show --partscan "$image")
case "$loop" in /dev/loop[0-9]*) ;; *) echo 'Invalid loop device'; exit 1;; esac
root=/mnt/harbor-image
mkdir -p "$root"
cleanup() { umount "$root/boot/efi" 2>/dev/null || true; umount "$root" 2>/dev/null || true; losetup -d "$loop"; }
trap cleanup EXIT
mkfs.vfat -F32 -n HARBOR_EFI "${loop}p2"
mkfs.ext4 -F -L harbor-root "${loop}p3"
mount "${loop}p3" "$root"
rsync -aHAX --numeric-ids --exclude=/proc/*** --exclude=/sys/*** --exclude=/dev/*** --exclude=/run/*** --exclude=/tmp/*** --exclude=/mnt/harbor-host/*** /target/ "$root/"
# Release images generate their own host identity and administrator at first boot.
rm -f "$root"/etc/ssh/ssh_host_* "$root"/var/lib/harbor/admin.json "$root"/var/lib/harbor/setup-token "$root"/var/lib/harbor/tls.key "$root"/var/lib/harbor/tls.crt
mkdir -p "$root/boot/efi" "$root/proc" "$root/sys" "$root/dev" "$root/run" "$root/tmp"
chmod 1777 "$root/tmp"
mount "${loop}p2" "$root/boot/efi"
uuid=$(blkid -s UUID -o value "${loop}p3")
efi_uuid=$(blkid -s UUID -o value "${loop}p2")
printf 'UUID=%s / ext4 defaults 0 1\nUUID=%s /boot/efi vfat umask=0077 0 2\n' "$uuid" "$efi_uuid" > "$root/etc/fstab"
printf 'LABEL=harbor-data /srv/harbor/storage btrfs defaults,nofail,x-systemd.device-timeout=10 0 0\n' >> "$root/etc/fstab"
grub-install --target=x86_64-efi --efi-directory="$root/boot/efi" --boot-directory="$root/boot" --removable --no-nvram
grub-install --target=i386-pc --boot-directory="$root/boot" "$loop"
kernel=$(basename "$(ls "$root"/boot/vmlinuz-* | sort -V | tail -1)")
initrd=$(basename "$(ls "$root"/boot/initrd.img-* | sort -V | tail -1)")
cat > "$root/boot/grub/grub.cfg" <<EOF
set timeout=5
set default=0
menuentry 'Harbor OS 0.1.0' {
  search --no-floppy --fs-uuid --set=root $uuid
  linux /boot/harbor-vmlinuz root=UUID=$uuid rw rootwait console=tty0 console=ttyS0,115200n8 panic=30
  initrd /boot/harbor-initrd
}
EOF
sync -f "$image"
cleanup
trap - EXIT
sha256sum "$image" > "$image.sha256"
zstd -T2 -3 --keep "$image"
sha256sum "$image.zst" > "$image.zst.sha256"
echo 'Bootable image complete.'
