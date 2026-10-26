set -eu
grep -qx 'ID=harbor' /etc/os-release
tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
install -m 644 /DATA/harbor/source/os/harbor.service /etc/systemd/system/harbor.service
install -m 755 /DATA/harbor/source/os/harbor-init /usr/local/sbin/harbor-init
mkdir -p /etc/systemd/system/systemd-networkd-wait-online.service.d
install -m 644 /DATA/harbor/source/os/harbor-network-online.conf /etc/systemd/system/systemd-networkd-wait-online.service.d/harbor.conf
systemctl daemon-reload
/usr/local/sbin/harbor-init --renew-certificate
systemctl restart harbor.service
openssl x509 -in /var/lib/harbor/tls.crt -noout -fingerprint -sha256 -ext subjectAltName
openssl x509 -in /var/lib/harbor/tls.crt -noout -checkip 192.168.1.97
DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends zstd
