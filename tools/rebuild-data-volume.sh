set -eu
# Target-specific recovery: the user explicitly declared all NAS data disposable.
# Only these two inspected healthy HDDs may be formatted. Never touch the SSD.
disk1=/dev/disk/by-id/ata-ST1000DM010-2EP102_ZN16ST2R
disk2=/dev/disk/by-id/ata-WDC_WD10EZEX-60M2NA0_WD-WCC3F2UPCNDD
boot=/dev/disk/by-id/ata-SPCC_Solid_State_Disk_BC640732015301264694
test "$(readlink -f "$boot")" = /dev/sda
test "$(readlink -f "$disk1")" = /dev/sdb
test "$(readlink -f "$disk2")" = /dev/sdc
for disk in "$disk1" "$disk2"; do
  test "$(lsblk -dn -o TYPE "$disk")" = disk
  test "$(blockdev --getsize64 "$disk")" = 1000204886016
  test "$(readlink -f "$disk")" != "$(readlink -f "$boot")"
done
systemctl stop casaos-local-storage.service 2>/dev/null || true
for path in /var/lib/casaos_data/.media/zima /DATA/.media/zima /media/zima; do
  if mountpoint -q "$path"; then umount "$path"; fi
done
mdadm --stop /dev/md0
# Erase signatures only on the two exact verified devices.
wipefs -a "$disk1" "$disk2"
mkfs.btrfs -f -L harbor-data -m raid1 -d raid1 "$disk1" "$disk2"
mkdir -p /media/harbor
mount -o noatime,compress=zstd:3 "$disk1" /media/harbor
mkdir -p /media/harbor/shares
btrfs filesystem show /media/harbor
btrfs filesystem usage /media/harbor
blkid "$disk1" "$disk2"
