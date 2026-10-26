set -eu
test -f /DATA/harbor/rootfs/var/lib/harbor/admin.json
test -f /mnt/boot/EFI/BOOT/grub-zima.cfg
grub-editenv /mnt/boot/EFI/BOOT/grubenv set harbor_once=1 harbor_default=0
sync -f /mnt/boot/EFI/BOOT/grubenv
systemd-run --unit=harbor-trial-reboot --on-active=5s /usr/bin/systemctl reboot
printf 'Harbor one-shot trial boot scheduled in five seconds.\n'
