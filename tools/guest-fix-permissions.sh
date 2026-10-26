set -eu
chmod 755 /srv/harbor/users /srv/harbor/storage/shares
getent passwd rico | cut -d: -f1,6
systemctl --failed --no-pager
