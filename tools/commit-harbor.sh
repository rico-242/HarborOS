set -eu
grep -qx 'ID=harbor' /etc/os-release
test -f /var/lib/harbor/boot-confirmed
test -f /boot/efi/EFI/BOOT/grub-zima.cfg
systemctl is-active --quiet harbor ssh smbd docker
grub-editenv /boot/efi/EFI/BOOT/grubenv set harbor_default=1 harbor_once=0
sync -f /boot/efi/EFI/BOOT/grubenv
printf 'Harbor is now the default boot entry. ZimaOS remains selectable.\n'
grub-editenv /boot/efi/EFI/BOOT/grubenv list
