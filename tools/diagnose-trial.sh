set -eu
printf '\n--- Current boot ---\n'
cat /etc/os-release
cat /proc/cmdline
uptime
printf '\n--- Trial flags ---\n'
grub-editenv /mnt/boot/EFI/BOOT/grubenv list
printf '\n--- Harbor boot artifacts ---\n'
ls -l /DATA/harbor/rootfs/var/lib/harbor
ls -l /DATA/harbor/rootfs/boot/harbor-*
printf '\n--- Harbor journals ---\n'
find /DATA/harbor/rootfs/var/log -maxdepth 2 -type f | head -15
printf '\n--- Available EFI firmware ---\n'
find /usr/share -maxdepth 4 \( -iname '*ovmf*' -o -iname '*edk2*' \) 2>/dev/null | head -20
printf '\n--- Vendor GRUB module markers ---\n'
python3 - <<'PY'
from pathlib import Path
import re
b=Path('/mnt/boot/EFI/BOOT/BOOTX64.EFI').read_bytes()
strings=[v.decode(errors='replace') for v in re.findall(rb'[ -~]{4,}',b)]
print('\n'.join(s for s in strings if any(v in s for v in ('search','ext2','initrd','UUID','unknown filesystem')))[-2500:])
PY
