#!/bin/bash
# Build only inside /DATA/harbor/iso-build. Never uses physical disk targets.
set -euo pipefail
work=/DATA/harbor/iso-build
target=$work/root
source=/DATA/harbor/source
iso=$work/iso
test -f "$work/root-ready"
test ! -f "$target/var/lib/harbor/admin.json"
# Clear chroot pseudo-filesystem mounts left by package hooks before squashing.
for path in "$target/sys" "$target/proc" "$target/dev"; do
  if mountpoint -q "$path"; then mount --make-rslave "$path"; umount -R "$path"; fi
done
rsync -a --delete "$source/harbor/" "$target/opt/harbor/"
install -m 755 "$source/os/harbor-install.py" "$target/usr/local/sbin/harbor-install"
install -m 755 "$source/os/harbor-live-menu" "$target/usr/local/sbin/harbor-live-menu"
install -m 644 "$source/os/harbor.service" "$target/etc/systemd/system/harbor.service"
sh "$source/os/configure-graphical.sh" "$source" "$target"
rm -f "$target/etc/systemd/system/getty@tty1.service.d/harbor-live.conf"
mkdir -p "$target/etc/modules-load.d" "$target/etc/systemd/system/getty@tty2.service.d" "$target/etc/systemd/system/serial-getty@ttyS0.service.d"
printf 'md_mod\nraid0\nraid1\nraid10\nraid456\n' > "$target/etc/modules-load.d/harbor-storage.conf"
for unit in getty@tty2 serial-getty@ttyS0; do
  printf '[Service]\nExecStart=\nExecStart=-/sbin/agetty --autologin root --noclear %%I 115200,38400,9600 $TERM\n' > "$target/etc/systemd/system/$unit.service.d/harbor-live.conf"
done
rm -f "$target/root/.bash_profile"
sed -i '/^HARBOR_LIVE=/d' "$target/etc/harbor.conf"
printf '\nHARBOR_LIVE=1\n' >> "$target/etc/harbor.conf"
printf '# Live preview: data disks are configured only after installing Harbor.\n' > "$target/etc/fstab"
printf 'Harbour OS 0.5.0 — graphical live installer\n' > "$target/etc/issue"
cat > "$target/etc/os-release" <<'EOF'
NAME="Harbour OS"
PRETTY_NAME="Harbour OS 0.5.0 (Debian 13)"
ID=harbor
ID_LIKE=debian
VERSION="0.5.0"
VERSION_ID="0.5.0"
DEBIAN_CODENAME=trixie
EOF
mkdir -p "$target/etc/systemd/resolved.conf.d"
printf '[Resolve]\nFallbackDNS=1.1.1.1 8.8.8.8\n' > "$target/etc/systemd/resolved.conf.d/harbor.conf"
ln -sfn /run/systemd/resolve/stub-resolv.conf "$target/etc/resolv.conf"
rm -f "$target"/etc/ssh/ssh_host_* "$target"/var/lib/harbor/tls.key "$target"/var/lib/harbor/tls.crt "$target"/var/lib/harbor/setup-token
printf '' > "$target/etc/machine-id"
for name in dev proc sys; do
  case "$name" in dev) mount --rbind /dev "$target/dev";; proc) mount -t proc proc "$target/proc";; sys) mount -t sysfs sysfs "$target/sys";; esac
  mount --make-rslave "$target/$name"
done
cleanup() { for name in sys proc dev; do if mountpoint -q "$target/$name"; then umount -R "$target/$name"; fi; done; }
trap cleanup EXIT
chroot "$target" update-initramfs -u -k all
cleanup
mkdir -p "$iso/live" "$iso/boot/grub"
cp -L "$target/boot/harbor-vmlinuz" "$iso/live/vmlinuz"
cp -L "$target/boot/harbor-initrd" "$iso/live/initrd.img"
mksquashfs "$target" "$iso/live/filesystem.squashfs" -noappend -comp zstd -Xcompression-level 10 -processors 2 -wildcards -e 'proc/*' 'sys/*' 'dev/*' 'run/*' 'tmp/*' 'mnt/*' 'var/cache/apt/archives/*.deb' 'var/log/*' 'var/lib/systemd/random-seed'
cat > "$iso/boot/grub/grub.cfg" <<'EOF'
set default=0
set timeout=10
set color_normal=light-gray/black
set color_highlight=black/light-green
menuentry 'Harbour OS 0.5.0 — graphical setup and live desktop' {
  linux /live/vmlinuz boot=live components nopersistence noeject quiet splash console=tty0 console=ttyS0,115200n8
  initrd /live/initrd.img
}
menuentry 'Harbour OS — console rescue (live only)' {
  linux /live/vmlinuz boot=live components nopersistence noeject systemd.unit=multi-user.target console=tty2 console=ttyS0,115200n8
  initrd /live/initrd.img
}
EOF
cat > "$iso/README.txt" <<'EOF'
Harbour OS 0.5.0 graphical live installer, x86-64 / amd64.
Write this ISO to USB in raw/DD mode or boot it in a VM. Supports UEFI and legacy BIOS.
Secure Boot is not supported. At least 4 GB RAM and a separate 16 GiB system disk are required.
Live mode runs in RAM; it does not install or create storage automatically.
The graphical installer shows the destination model and serial, then asks for explicit erasure confirmation.
After installation, remove the USB and boot the system disk. Create the owner on the local graphical screen; no setup code is required.
Configure separate data disks through Storage > Create storage. Internet is needed to download app images.
Official ZimaOS app definitions: IceWhaleTech/CasaOS-AppStore, Apache 2.0. Individual apps retain their licenses.
EOF
(cd "$iso" && find live -type f -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
mkdir -p /DATA/harbor/release/artifacts
grub-mkrescue -o /DATA/harbor/release/artifacts/harbour-0.5.0-amd64.iso "$iso" -- -volid HARBOUR_050
cd /DATA/harbor/release/artifacts
sha256sum harbour-0.5.0-amd64.iso > harbour-0.5.0-amd64.iso.sha256
xorriso -indev harbour-0.5.0-amd64.iso -report_el_torito plain -report_system_area plain 2>&1 | tail -25
printf 'Hybrid live installer ISO built.\n'
