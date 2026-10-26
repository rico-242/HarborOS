set -eu
python3 -m py_compile /tmp/harbor-dark-server.py
stamp=$(date -u +%Y%m%dT%H%M%SZ)
install -m 644 /opt/harbor/server.py "/var/lib/harbor/ui-backups/server-$stamp.py"
install -m 644 /tmp/harbor-dark-server.py /opt/harbor/server.py
install -m 644 /opt/harbor/server.py /DATA/harbor/source/harbor/server.py
systemctl restart harbor.service
systemctl is-active harbor.service
if mountpoint -q /mnt/harbor-zima-reference; then umount /mnt/harbor-zima-reference; fi
