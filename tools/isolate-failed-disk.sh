set -eu
printf '\n--- Confirm failed drive identity ---\n'
test "$(readlink -f /dev/disk/by-id/ata-WDC_WD10EZEX-60M2NA0_WD-WCC3F0YAV0YU)" = /dev/sdd
printf 'Removing the failed WD-WCC3F0YAV0YU drive from the running kernel.\n'
echo 1 > /sys/block/sdd/device/delete
printf 'Failed disk isolated.\n'
cat /proc/mdstat
