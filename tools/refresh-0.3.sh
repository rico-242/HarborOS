set -eu
tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
python3 -m compileall -q /DATA/harbor/source/harbor
rsync -a --delete /DATA/harbor/source/harbor/ /opt/harbor/
install -m 755 /DATA/harbor/source/os/harbour-package-update /usr/local/sbin/harbour-package-update
systemctl restart harbor
systemctl is-active harbor lightdm ssh smbd docker
bash /DATA/harbor/source/os/build-iso.sh
