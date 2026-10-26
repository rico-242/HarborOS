set -eu
mkdir -p /DATA/harbor/release/artifacts
test ! -e /DATA/harbor/release/artifacts/harbor-0.1.0-amd64.img
docker run -d --name harbor-release --privileged -v /dev:/dev -v /DATA/harbor/release:/work -v /DATA/harbor/rootfs:/target:ro -v /DATA/harbor/source:/source:ro --entrypoint /bin/bash harbor-image-builder:0.1 /source/os/build-image.sh
