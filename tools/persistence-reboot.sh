set -eu
grep -qx 'ID=harbor' /etc/os-release
test -f /var/lib/harbor/boot-confirmed
grub-editenv /boot/efi/EFI/BOOT/grubenv list | grep -qx 'harbor_default=1'
systemd-run --unit=harbor-persistence-reboot --on-active=5s /usr/bin/systemctl reboot
printf 'Default-boot persistence check scheduled.\n'
