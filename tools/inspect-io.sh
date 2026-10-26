set -eu
printf '\n--- Storage synchronization ---\n'
cat /proc/mdstat
cat /proc/24880/wchan 2>/dev/null || true
cat /proc/24880/stack 2>/dev/null || true
printf '\n--- Kernel storage messages ---\n'
dmesg | tail -45
printf '\n--- SSD health ---\n'
smartctl -H /dev/sda || true
printf '\n--- Process state ---\n'
docker top harbor-build -eo pid,stat,wchan,etime,args
