set -eu
tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
install -m 644 /DATA/harbor/source/harbor/web/app.js /opt/harbor/web/app.js
systemd-analyze verify /etc/systemd/system/harbor.service /etc/systemd/system/harbor-console.service /etc/systemd/system/harbor-boot-guard.service
/usr/lib/systemd/systemd-networkd-wait-online --any --ipv4 --timeout=5
sh /DATA/harbor/source/tools/update-release-tls.sh
