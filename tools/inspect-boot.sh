set -eu
printf '\n--- Bootloader ---\n'
cat /mnt/boot/EFI/BOOT/grub.cfg
grub-editenv /mnt/boot/EFI/BOOT/grubenv list
printf '\n--- Filesystem identifiers ---\n'
blkid /dev/sda8 /dev/md0
mdadm --detail --scan
printf '\n--- Firmware ---\n'
efibootmgr -v
printf '\n--- Build progress ---\n'
docker logs --tail 20 harbor-build 2>&1
