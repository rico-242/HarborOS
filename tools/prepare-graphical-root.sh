set -eu
target=/DATA/harbor/iso-build/root
test -f /DATA/harbor/iso-build/root-ready
test ! -f "$target/var/lib/harbor/admin.json"
for name in dev proc sys; do
  if ! mountpoint -q "$target/$name"; then
    case "$name" in dev) mount --rbind /dev "$target/dev";; proc) mount -t proc proc "$target/proc";; sys) mount -t sysfs sysfs "$target/sys";; esac
  fi
  mount --make-rslave "$target/$name"
done
cleanup() { for name in sys proc dev; do umount -R "$target/$name"; done; }
trap cleanup EXIT
rm -f "$target/etc/resolv.conf"
cp -L /etc/resolv.conf "$target/etc/resolv.conf"
printf '#!/bin/sh\nexit 101\n' > "$target/usr/sbin/policy-rc.d"
chmod +x "$target/usr/sbin/policy-rc.d"
chroot "$target" /bin/sh -c 'export DEBIAN_FRONTEND=noninteractive; apt-get update; apt-get install -y --no-install-recommends lightdm openbox chromium chromium-sandbox xserver-xorg-core xserver-xorg-input-libinput xserver-xorg-video-all x11-xserver-utils dbus-x11 fonts-dejavu-core plymouth plymouth-themes qemu-guest-agent; apt-get clean'
rm -f "$target/usr/sbin/policy-rc.d"
ln -sfn /run/systemd/resolve/stub-resolv.conf "$target/etc/resolv.conf"
printf 'Graphical build dependencies installed in isolated release root.\n'
