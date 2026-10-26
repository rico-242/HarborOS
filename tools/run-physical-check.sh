set -eu
python3 /DATA/harbor/source/tools/physical-check.py
systemctl --failed --no-pager
findmnt / /srv/harbor/storage /boot/efi || true
btrfs device stats /srv/harbor/storage
