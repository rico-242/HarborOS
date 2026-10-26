set -eu
cat /boot/efi/EFI/BOOT/grub.cfg
cat /etc/os-release
df -h /
lspci | sed -n '/VGA\|Display/p'
cat /etc/initramfs/post-update.d/harbor-boot
