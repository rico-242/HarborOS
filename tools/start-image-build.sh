set -eu
tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
test "$(docker inspect -f '{{.State.ExitCode}}' harbor-finalize)" = 0
cp -a /DATA/harbor/source/harbor/. /DATA/harbor/rootfs/opt/harbor/
docker run -d --name harbor-image --privileged -v /dev:/dev -v /DATA/harbor:/work -v /DATA/harbor/rootfs:/target:ro --entrypoint /bin/bash harbor-builder:0.1 -c 'apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends grub2-common && /bin/bash /work/source/os/build-image.sh'
