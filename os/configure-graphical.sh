#!/bin/sh
# Configure a normal unprivileged Chromium session; no browser sandbox bypasses.
set -eu
source=${1:-/DATA/harbor/source}
target=${2:-/DATA/harbor/iso-build/root}
test -f "$target/etc/debian_version"
sh "$source/os/install-maintenance.sh" "$source" "$target"
if ! chroot "$target" id harbour-display >/dev/null 2>&1; then
  chroot "$target" useradd --system --create-home --home-dir /var/lib/harbour-display --shell /bin/bash --groups video,render harbour-display
fi
mkdir -p "$target/etc/lightdm/lightdm.conf.d" "$target/etc/harbor" "$target/usr/share/xsessions" "$target/etc/systemd/system/lightdm.service.d"
install -m 755 "$source/os/harbor-kiosk-session" "$target/usr/local/sbin/harbor-kiosk-session"
install -m 755 "$source/os/installer-server.py" "$target/usr/local/sbin/harbor-installer-server"
install -m 755 "$source/os/harbour-package-update" "$target/usr/local/sbin/harbour-package-update"
install -m 644 "$source/os/harbor-installer.service" "$target/etc/systemd/system/harbor-installer.service"
install -m 644 "$source/os/harbour.desktop" "$target/usr/share/xsessions/harbour.desktop"
install -m 644 "$source/os/openbox.xml" "$target/etc/harbor/openbox.xml"
install -m 755 "$source/os/harbor-console" "$target/usr/local/sbin/harbor-console"
install -m 755 "$source/os/harbor-init" "$target/usr/local/sbin/harbor-init"
mkdir -p "$target/usr/share/plymouth/themes/harbour"
install -m 644 "$source/os/harbour.plymouth" "$target/usr/share/plymouth/themes/harbour/harbour.plymouth"
install -m 644 "$source/os/harbour.script" "$target/usr/share/plymouth/themes/harbour/harbour.script"
chroot "$target" plymouth-set-default-theme harbour
cat > "$target/etc/lightdm/lightdm.conf.d/50-harbour.conf" <<'EOF'
[LightDM]
minimum-vt=1
[Seat:*]
autologin-user=harbour-display
autologin-user-timeout=0
autologin-session=harbour
user-session=harbour
greeter-hide-users=true
EOF
printf '[Unit]\nAfter=harbor.service harbor-installer.service\n' > "$target/etc/systemd/system/lightdm.service.d/harbour.conf"
ln -sfn /dev/null "$target/etc/systemd/system/getty@tty1.service"
chroot "$target" systemctl enable lightdm.service harbor-installer.service
if test -x "$target/usr/sbin/qemu-ga"; then chroot "$target" systemctl enable qemu-guest-agent.service; fi
chroot "$target" systemctl set-default graphical.target
printf 'Graphical Harbour session configured with sandboxed Chromium.\n'
