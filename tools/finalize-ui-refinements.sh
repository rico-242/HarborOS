set -eu
tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
rsync -a --delete /DATA/harbor/source/harbor/web/ /opt/harbor/web/
bash /DATA/harbor/source/os/build-iso.sh
