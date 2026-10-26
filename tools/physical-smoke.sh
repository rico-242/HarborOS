set -eu
python3 /tmp/harbor-test-smb.py
printf '\n--- Operating system ---\n'
cat /etc/os-release
uname -r
printf '\n--- Services ---\n'
systemctl is-active harbor ssh smbd docker systemd-networkd
systemctl --failed --no-pager
printf '\n--- Root and data mounts ---\n'
findmnt -n -o SOURCE,FSTYPE,TARGET /
findmnt -n -o SOURCE,FSTYPE,TARGET /srv/harbor/storage
findmnt -n -o SOURCE,FSTYPE,TARGET /boot/efi
printf '\n--- TLS identity ---\n'
openssl x509 -in /var/lib/harbor/tls.crt -noout -fingerprint -sha256
