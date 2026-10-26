#!/bin/bash
set -euo pipefail
image=/work/vm/vendor-efi.img
test ! -e "$image"
truncate -s 12G "$image"
parted -s "$image" mklabel gpt mkpart ESP fat32 1MiB 129MiB set 1 esp on
for n in 2 3 4 5 6 7; do
  start=$((129+(n-2)*2))
  end=$((start+2))
  parted -s "$image" mkpart "placeholder$n" "${start}MiB" "${end}MiB"
done
parted -s "$image" mkpart harbor-test ext4 141MiB 100%
loop=$(losetup --find --show --partscan "$image")
mkdir -p /mnt/test-esp /mnt/test-root
cleanup() { umount /mnt/test-esp /mnt/test-root 2>/dev/null || true; losetup -d "$loop"; }
trap cleanup EXIT
mkfs.vfat -F32 "${loop}p1"
dd if=/work/vm/subdir.img of="${loop}p8" bs=16M status=none
mount "${loop}p1" /mnt/test-esp
mount "${loop}p8" /mnt/test-root
mkdir -p /mnt/test-esp/EFI/BOOT
cp /esp/BOOTX64.EFI /esp/grubenv /mnt/test-esp/EFI/BOOT/
uuid=$(blkid -s UUID -o value "${loop}p8")
sed -e "s/4fc77cd8-8c54-4a6a-b6c6-c3d2c51e84e2/$uuid/g" -e 's/console=tty1/console=ttyS0,115200n8/g' -e '/search --no-floppy --fs-uuid --set=harborroot /c\    regexp --set 1:boothd (.+),.+ ${root}\n    set harborroot=${boothd},gpt8' /esp/grub.cfg > /mnt/test-esp/EFI/BOOT/grub.cfg
grub-editenv /mnt/test-esp/EFI/BOOT/grubenv set harbor_once=1 harbor_default=0
root=/mnt/test-root/harbor/rootfs
printf '/dev/vda8 / ext4 defaults 0 1\nLABEL=harbor-data /srv/harbor/storage btrfs defaults,nofail 0 0\n' > "$root/etc/fstab"
cp -a /target/boot/initrd.img-* /target/boot/harbor-initrd "$root/boot/"
touch "$root/var/lib/harbor/boot-confirmed"
sync -f "$image"
printf 'Vendor EFI fixture built.\n'
