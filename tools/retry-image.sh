set -eu
tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
cp -a /DATA/harbor/source/harbor/. /DATA/harbor/rootfs/opt/harbor/
docker commit harbor-image harbor-image-builder:0.1 >/dev/null
docker run -d --name harbor-package --privileged -v /dev:/dev -v /DATA/harbor:/work -v /DATA/harbor/rootfs:/target:ro --entrypoint /bin/bash harbor-image-builder:0.1 /work/source/os/build-image.sh
