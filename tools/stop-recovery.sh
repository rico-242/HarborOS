set -eu
printf 'frozen\n' > /sys/block/md0/md/sync_action
printf '\n--- Recovery state ---\n'
cat /proc/mdstat
printf '\n--- Data disk health ---\n'
for disk in /dev/sdb /dev/sdc /dev/sdd /dev/sde; do
  printf '\n--- %s ---\n' "$disk"
  smartctl -H -A "$disk" || true
done
printf '\n--- Mount users ---\n'
findmnt -S /dev/md0
fuser -m /media/zima 2>/dev/null || true
