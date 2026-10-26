set -eu
grep -qx 'ID=harbor' /etc/os-release
systemctl is-active --quiet harbor ssh smbd docker
test -f /var/lib/harbor/admin.json
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup=/var/lib/harbor/release-backups/harbour-0.3-$stamp
mkdir -p "$backup"
tar -czf "$backup/application.tar.gz" -C /opt harbor
cp -a /etc/os-release /etc/harbor.conf "$backup/"
cp -a /boot/efi/EFI/BOOT/grub.cfg "$backup/grub.cfg"
tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
python3 -m compileall -q /DATA/harbor/source/harbor
rsync -a --delete /DATA/harbor/source/harbor/ /opt/harbor/
install -m 755 /DATA/harbor/source/os/harbour-package-update /usr/local/sbin/harbour-package-update
install -m 755 /DATA/harbor/source/os/harbor-init /usr/local/sbin/harbor-init
install -m 755 /DATA/harbor/source/os/harbor-console /usr/local/sbin/harbor-console
systemctl restart harbor
systemctl is-active harbor
printf 'Web release updated; owner, TLS identity and data remain in their existing state directories.\n'
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends lightdm openbox chromium chromium-sandbox xserver-xorg-core xserver-xorg-input-libinput xserver-xorg-video-all x11-xserver-utils dbus-x11 fonts-dejavu-core plymouth plymouth-themes
sh /DATA/harbor/source/os/configure-graphical.sh /DATA/harbor/source /
cat > /etc/os-release <<'EOF'
NAME="Harbour OS"
PRETTY_NAME="Harbour OS 0.3.0 (Debian 13)"
ID=harbor
ID_LIKE=debian
VERSION="0.3.0"
VERSION_ID="0.3.0"
DEBIAN_CODENAME=trixie
EOF
python3 - <<'PY'
from pathlib import Path
path=Path('/boot/efi/EFI/BOOT/grub.cfg')
text=path.read_text().replace("menuentry 'Harbor OS 0.1.0'", "menuentry 'Harbour OS 0.3.0'")
text=text.replace('panic=30 net.ifnames=0 biosdevname=0 console=tty1','panic=30 net.ifnames=0 biosdevname=0 quiet splash console=tty0')
assert 'ZimaOS (previous system)' in text and 'harbor.subdir=harbor/rootfs' in text
path.write_text(text)
PY
update-initramfs -u -k all
systemctl daemon-reload
systemctl start lightdm
systemctl is-active harbor lightdm ssh smbd docker
printf 'Graphical boot configured. The physical NAS was not rebooted or upgraded.\n'
