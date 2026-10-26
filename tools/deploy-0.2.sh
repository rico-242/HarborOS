set -eu
tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
python3 -m compileall -q /DATA/harbor/source/harbor
stamp=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p /var/lib/harbor/release-backups
tar -czf "/var/lib/harbor/release-backups/harbor-$stamp.tar.gz" -C /opt harbor
rsync -a --delete /DATA/harbor/source/harbor/ /opt/harbor/
modprobe md_mod
for module in raid0 raid1 raid10 raid456; do modprobe "$module"; done
systemctl restart harbor
systemctl is-active harbor
