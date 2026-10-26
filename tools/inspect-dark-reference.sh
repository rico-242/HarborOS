set -eu
printf '\n--- Available read-only hardware metrics ---\n'
for directory in /sys/class/hwmon/hwmon*; do
  printf '%s ' "$directory"
  cat "$directory/name" 2>/dev/null || true
  cat "$directory/temp1_input" 2>/dev/null || true
done
printf '\n--- Power counters ---\n'
find /sys/class/powercap -maxdepth 3 -name energy_uj 2>/dev/null | head -5
printf '\n--- Interfaces ---\n'
cat /proc/net/route
printf '\n--- Original ZimaOS public frontend location ---\n'
mkdir -p /mnt/harbor-zima-reference
if ! mountpoint -q /mnt/harbor-zima-reference; then
  mount -t squashfs -o ro /dev/disk/by-id/ata-SPCC_Solid_State_Disk_BC640732015301264694-part3 /mnt/harbor-zima-reference
fi
find /mnt/harbor-zima-reference -name 'index-yeNfqxRp.css' -o -name 'zimaos-logo.svg' 2>/dev/null | head -10
