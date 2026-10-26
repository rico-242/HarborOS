set -eu
printf '\n--- Boot identity ---\n'
cat /proc/sys/kernel/random/boot_id
cat /proc/cmdline
uptime
printf '\n--- Verified storage ---\n'
python3 - <<'PY'
from pathlib import Path
import json
v=json.loads(Path('/var/lib/harbor/physical-verification.json').read_text())
print(json.dumps(v['summary']['storage'],indent=2))
print('Shared folders:', ', '.join(s['name'] for s in json.loads(Path('/var/lib/harbor/config.json').read_text())['shares']))
PY
printf '\n--- Drive identities ---\n'
lsblk -d -o NAME,MODEL,SERIAL,SIZE
printf '\n--- Default boot ---\n'
grub-editenv /boot/efi/EFI/BOOT/grubenv list
printf '\n--- Listening services ---\n'
ss -lnt | grep -E ':(22|445|8443) '
