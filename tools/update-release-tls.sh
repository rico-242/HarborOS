set -eu
image=/DATA/harbor/release/artifacts/harbor-0.1.0-amd64.img
test -f "$image"
loop=$(losetup --find --show --partscan "$image")
case "$loop" in /dev/loop[0-9]*) ;; *) exit 1;; esac
directory=/mnt/harbor-release-edit
mkdir -p "$directory"
mount "${loop}p3" "$directory"
cleanup() { umount "$directory"; losetup -d "$loop"; }
trap cleanup EXIT
test ! -f "$directory/var/lib/harbor/admin.json"
install -m 644 /DATA/harbor/source/os/harbor.service "$directory/etc/systemd/system/harbor.service"
install -m 755 /DATA/harbor/source/os/harbor-init "$directory/usr/local/sbin/harbor-init"
install -m 644 /opt/harbor/server.py "$directory/opt/harbor/server.py"
install -m 644 /opt/harbor/web/app.js "$directory/opt/harbor/web/app.js"
mkdir -p "$directory/etc/systemd/system/systemd-networkd-wait-online.service.d"
install -m 644 /DATA/harbor/source/os/harbor-network-online.conf "$directory/etc/systemd/system/systemd-networkd-wait-online.service.d/harbor.conf"
sync -f "$image"
cleanup
trap - EXIT
cd /DATA/harbor/release/artifacts
sha256sum harbor-0.1.0-amd64.img > harbor-0.1.0-amd64.img.sha256
zstd -T2 -3 -f --keep harbor-0.1.0-amd64.img
sha256sum harbor-0.1.0-amd64.img.zst > harbor-0.1.0-amd64.img.zst.sha256
printf 'Release archive updated with the certificate setup fix.\n'
