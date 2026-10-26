set -eu
docker ps -a --filter name=harbor-subdir --format '{{.Names}} {{.Status}}'
docker logs --tail 15 harbor-subdir-build 2>&1
printf '\n--- Current network identity ---\n'
cat /sys/class/net/eth0/address
cat /etc/machine-id
grep -r -E 'ClientIdentifier|IAID|DUID|DHCP=' /etc/systemd/network 2>/dev/null || true
printf '\n--- Firmware GRUB capabilities ---\n'
python3 - <<'PY'
from pathlib import Path
b=Path('/mnt/boot/EFI/BOOT/BOOTX64.EFI').read_bytes()
print({name:name.encode() in b for name in ['ext2','search','search_fs_uuid','squash4','initrd','configfile']})
PY
