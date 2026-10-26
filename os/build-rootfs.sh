#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
TARGET=${HARBOR_TARGET:-/target}
SOURCE=${HARBOR_SOURCE:-/source}
if [ ! -f "$TARGET/etc/debian_version" ]; then
  debootstrap --variant=minbase --include=ca-certificates trixie "$TARGET" https://deb.debian.org/debian
fi
cleanup() { umount "$TARGET/dev/pts" "$TARGET/dev" "$TARGET/proc" "$TARGET/sys" 2>/dev/null || true; }
trap cleanup EXIT
mountpoint -q "$TARGET/dev" || mount --bind /dev "$TARGET/dev"
mountpoint -q "$TARGET/dev/pts" || mount --bind /dev/pts "$TARGET/dev/pts"
mountpoint -q "$TARGET/proc" || mount -t proc proc "$TARGET/proc"
mountpoint -q "$TARGET/sys" || mount -t sysfs sysfs "$TARGET/sys"
rm -f "$TARGET/etc/resolv.conf"
cp -L /etc/resolv.conf "$TARGET/etc/resolv.conf"
cat > "$TARGET/usr/sbin/policy-rc.d" <<'EOF'
#!/bin/sh
exit 101
EOF
chmod +x "$TARGET/usr/sbin/policy-rc.d"
cat > "$TARGET/etc/apt/sources.list" <<'EOF'
deb https://deb.debian.org/debian trixie main contrib non-free-firmware
deb https://deb.debian.org/debian trixie-updates main contrib non-free-firmware
deb https://security.debian.org/debian-security trixie-security main contrib non-free-firmware
EOF
chroot "$TARGET" apt-get update
chroot "$TARGET" apt-get install -y --no-install-recommends linux-image-amd64 systemd-sysv systemd-timesyncd systemd-resolved dbus udev initramfs-tools busybox python3 openssh-server sudo ca-certificates curl openssl iproute2 iputils-ping ethtool pciutils usbutils btrfs-progs mdadm smartmontools samba smbclient docker.io docker-cli avahi-daemon libnss-mdns locales kmod less nano rsync parted e2fsprogs dosfstools cloud-guest-utils firmware-realtek firmware-iwlwifi intel-microcode grub-efi-amd64-bin grub-pc-bin
rsync -a "$SOURCE"/harbor/ "$TARGET/opt/harbor/"
install -m 644 "$SOURCE"/os/harbor.service "$TARGET/etc/systemd/system/harbor.service"
install -m 755 "$SOURCE"/os/harbor-init "$TARGET/usr/local/sbin/harbor-init"
install -m 755 "$SOURCE"/os/harbor-console "$TARGET/usr/local/sbin/harbor-console"
install -m 644 "$SOURCE"/os/harbor-console.service "$TARGET/etc/systemd/system/harbor-console.service"
install -m 755 "$SOURCE"/os/harbor-subdir "$TARGET/etc/initramfs-tools/scripts/local-bottom/harbor-subdir"
mkdir -p "$TARGET/etc/initramfs/post-update.d"
install -m 755 "$SOURCE"/os/harbor-kernel-update "$TARGET/etc/initramfs/post-update.d/harbor-boot"
install -m 755 "$SOURCE"/os/harbor-boot-guard "$TARGET/usr/local/sbin/harbor-boot-guard"
install -m 644 "$SOURCE"/os/harbor-boot-guard.service "$TARGET/etc/systemd/system/harbor-boot-guard.service"
install -m 644 "$SOURCE"/os/harbor.conf "$TARGET/etc/harbor.conf"
mkdir -p "$TARGET/etc/systemd/network" "$TARGET/var/lib/harbor" "$TARGET/srv/harbor/storage" "$TARGET/srv/harbor/apps" "$TARGET/etc/samba/harbor.d"
sh "$SOURCE"/os/install-maintenance.sh "$SOURCE" "$TARGET"
mkdir -p "$TARGET/etc/systemd/system/ssh.service.d"
printf '[Unit]\nAfter=harbor.service\n' > "$TARGET/etc/systemd/system/ssh.service.d/harbor.conf"
mkdir -p "$TARGET/etc/systemd/system/systemd-networkd-wait-online.service.d"
install -m 644 "$SOURCE"/os/harbor-network-online.conf "$TARGET/etc/systemd/system/systemd-networkd-wait-online.service.d/harbor.conf"
cat > "$TARGET/etc/systemd/network/20-wired.network" <<'EOF'
[Match]
Name=en* eth*
[Network]
DHCP=yes
MulticastDNS=yes
[DHCPv4]
UseHostname=no
EOF
cat > "$TARGET/etc/hostname" <<'EOF'
harbor
EOF
cat > "$TARGET/etc/hosts" <<'EOF'
127.0.0.1 localhost
127.0.1.1 harbor
::1 localhost ip6-localhost ip6-loopback
EOF
cat > "$TARGET/etc/samba/smb.conf" <<'EOF'
[global]
   workgroup = WORKGROUP
   server string = Harbor OS
   server role = standalone server
   map to guest = Never
   server min protocol = SMB2
   usershare allow guests = no
   load printers = no
   disable spoolss = yes
   include = /etc/samba/harbor-shares.conf
EOF
touch "$TARGET/etc/samba/harbor-shares.conf"
cat > "$TARGET/etc/ssh/sshd_config.d/harbor.conf" <<'EOF'
PermitRootLogin no
PasswordAuthentication yes
PermitEmptyPasswords no
MaxAuthTries 4
EOF
printf 'Harbor OS 0.1.0\nDebian GNU/Linux 13 base\n' > "$TARGET/etc/issue"
rm -f "$TARGET/etc/os-release"
cat > "$TARGET/etc/os-release" <<'EOF'
NAME="Harbor OS"
PRETTY_NAME="Harbor OS 0.1.0 (Debian 13)"
ID=harbor
ID_LIKE=debian
VERSION="0.1.0"
VERSION_ID="0.1.0"
DEBIAN_CODENAME=trixie
EOF
printf 'Harbor OS\nManage this server at https://harbor.local:8443\n' > "$TARGET/etc/motd"
chroot "$TARGET" systemctl enable harbor.service harbor-console.service harbor-boot-guard.service systemd-networkd.service systemd-resolved.service systemd-timesyncd.service ssh.service smbd.service docker.service avahi-daemon.service
chroot "$TARGET" systemctl disable NetworkManager.service 2>/dev/null || true
rm -f "$TARGET/usr/sbin/policy-rc.d"
chroot "$TARGET" update-initramfs -u -k all
ln -sf /run/systemd/resolve/stub-resolv.conf "$TARGET/etc/resolv.conf"
chroot "$TARGET" apt-get clean
rm -f "$TARGET/etc/machine-id" "$TARGET/var/lib/dbus/machine-id"
touch "$TARGET/etc/machine-id"
printf '\nHarbor root filesystem built successfully.\n'
