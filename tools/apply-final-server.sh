set -eu
install -m 644 /tmp/harbor-server.py /opt/harbor/server.py
systemctl restart harbor.service
systemctl is-active harbor.service
