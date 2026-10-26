set -eu
root=/DATA/harbor/rootfs
test -x "$root/usr/bin/python3"
test -f "$root/etc/harbor.conf"
# Preserve the already-authorized account and host identity for this machine.
chroot "$root" id rico >/dev/null 2>&1 || chroot "$root" useradd -m -s /bin/bash -G sudo rico
getent shadow rico | cut -d: -f1,2 | chroot "$root" chpasswd -e
for key in /etc/ssh/ssh_host_*; do
  test -f "$key" || continue
  cp -p "$key" "$root/etc/ssh/"
done
mkdir -p /DATA/harbor/artifacts/zima-boot-backup
cp -p /mnt/boot/EFI/BOOT/grub.cfg /mnt/boot/EFI/BOOT/grubenv /DATA/harbor/artifacts/zima-boot-backup/
root_uuid=$(blkid -s UUID -o value /dev/disk/by-id/ata-SPCC_Solid_State_Disk_BC640732015301264694-part8)
data_uuid=$(blkid -s UUID -o value /dev/disk/by-id/ata-ST1000DM010-2EP102_ZN16ST2R)
efi_uuid=$(blkid -s UUID -o value /dev/disk/by-id/ata-SPCC_Solid_State_Disk_BC640732015301264694-part1)
mkdir -p "$root/boot/efi"
printf 'UUID=%s / ext4 defaults 0 1\nUUID=%s /srv/harbor/storage btrfs defaults,noatime,compress=zstd:3,nofail,x-systemd.device-timeout=30 0 0\nUUID=%s /boot/efi vfat umask=0077 0 2\n' "$root_uuid" "$data_uuid" "$efi_uuid" > "$root/etc/fstab"
printf 'AUTO -all\n' > "$root/etc/mdadm/mdadm.conf"
printf '["Two HDDs are excluded due to read errors: WD-WCC3F0YAV0YU and WD-WCC3F0RSA3AX. Replace these drives before adding storage."]\n' > "$root/var/lib/harbor/hardware-alerts.json"
cat > "$root/etc/smartd.conf" <<'EOF'
/dev/disk/by-id/ata-SPCC_Solid_State_Disk_BC640732015301264694 -a -n standby,q
/dev/disk/by-id/ata-ST1000DM010-2EP102_ZN16ST2R -a -n standby,q
/dev/disk/by-id/ata-WDC_WD10EZEX-60M2NA0_WD-WCC3F2UPCNDD -a -n standby,q
EOF
printf '\n--- Root filesystem ---\n'
du -sh "$root"
printf '\n--- Storage health ---\n'
cat /proc/mdstat
btrfs filesystem usage /media/harbor
printf '\n--- Final build state ---\n'
cat "$root/etc/os-release"
