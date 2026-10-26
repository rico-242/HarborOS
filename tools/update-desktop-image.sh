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
for name in index.html app.js style.css favicon.svg; do
  install -m 644 "/opt/harbor/web/$name" "$directory/opt/harbor/web/$name"
done
install -m 644 /opt/harbor/server.py "$directory/opt/harbor/server.py"
sync -f "$image"
cleanup
trap - EXIT
cd /DATA/harbor/release/artifacts
sha256sum harbor-0.1.0-amd64.img > harbor-0.1.0-amd64.img.sha256
zstd -T2 -3 -f --keep harbor-0.1.0-amd64.img
sha256sum harbor-0.1.0-amd64.img.zst > harbor-0.1.0-amd64.img.zst.sha256
printf 'Standalone image updated with the dark desktop.\n'
