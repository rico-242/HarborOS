#!/bin/sh
set -eu
source=${1:-/DATA/harbor/source}
target=${2:-/}
test -f "$source/os/release-public.pem"
mkdir -p "$target/etc/harbor" "$target/usr/local/lib/harbour-updater" "$target/etc/systemd/system"
if test -e "$target/etc/harbor/update-public.pem"; then
  cmp -s "$source/os/release-public.pem" "$target/etc/harbor/update-public.pem" || { echo 'Existing trusted release key differs; refusing automatic key replacement.' >&2; exit 1; }
else
  install -m 644 "$source/os/release-public.pem" "$target/etc/harbor/update-public.pem"
fi
install -m 644 "$source/harbor/release_bundle.py" "$target/usr/local/lib/harbour-updater/release_bundle.py"
install -m 644 "$source/harbor/release_worker.py" "$target/usr/local/lib/harbour-updater/release_worker.py"
install -m 755 "$source/os/harbour-release-update" "$target/usr/local/sbin/harbour-release-update"
install -m 755 "$source/os/harbour-network-change" "$target/usr/local/sbin/harbour-network-change"
install -m 755 "$source/os/harbour-package-update" "$target/usr/local/sbin/harbour-package-update"
install -m 644 "$source/os/harbour-update-recover.service" "$target/etc/systemd/system/harbour-update-recover.service"
install -m 644 "$source/os/harbour-network-recover.service" "$target/etc/systemd/system/harbour-network-recover.service"
chroot "$target" systemctl enable harbour-update-recover.service harbour-network-recover.service
