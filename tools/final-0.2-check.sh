set -eu
printf 'Harbor service: '
systemctl is-active harbor
printf 'Failed services:\n'
systemctl --failed --no-legend
printf 'RAID personality modules:\n'
for module in btrfs raid0 raid1 raid10 raid456; do modinfo -F filename "$module"; done
printf 'ISO:\n'
ls -lh /DATA/harbor/release/artifacts/harbor-0.2.0-amd64.iso
cat /DATA/harbor/release/artifacts/harbor-0.2.0-amd64.iso.sha256
printf 'VM acceptance:\n'
cat /DATA/harbor/iso-test/acceptance-result.json
