set -eu
python3 /tmp/harbor-post-reboot.py
systemctl is-active harbor ssh smbd docker systemd-networkd
systemctl --failed --no-pager
openssl x509 -in /var/lib/harbor/tls.crt -noout -fingerprint -sha256 -ext subjectAltName
grub-editenv /boot/efi/EFI/BOOT/grubenv list | grep -E '^harbor_'
