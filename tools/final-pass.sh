set -eu
tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
docker run -d --name harbor-final-pass-2 --privileged -v /DATA/harbor/rootfs:/target -v /DATA/harbor/source:/source:ro --entrypoint /bin/bash harbor-image-builder:0.1 /source/os/build-rootfs.sh
