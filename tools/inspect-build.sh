set -eu
printf '\n--- Build and recovery tools ---\n'
for x in kexec grub-editenv efibootmgr qemu-img virsh curl wget tar gzip sha256sum sfdisk parted losetup mount mkfs.ext4 mkfs.vfat resize2fs e2fsck; do command -v "$x" || true; done
printf '\n--- Firmware and boot config ---\n'
cat /sys/kernel/kexec_loaded 2>/dev/null || true
cat /sys/kernel/kexec_crash_loaded 2>/dev/null || true
cat /sys/kernel/security/lockdown 2>/dev/null || true
ls -l /mnt/boot
find /mnt/boot -maxdepth 4 -type f
printf '\n--- Docker and virtualization ---\n'
docker images --format '{{.Repository}}:{{.Tag}} {{.Size}}'
qemu-system-x86_64 --version | head -1
printf '\n--- Disk identity ---\n'
ls -l /dev/disk/by-id | head -35
printf '\n--- Host services ---\n'
systemctl is-active sshd || true
cat /etc/ssh/sshd_config | head -60
printf '\n--- Internet ---\n'
curl -I --connect-timeout 10 https://deb.debian.org/debian/ 2>/dev/null | head -3
