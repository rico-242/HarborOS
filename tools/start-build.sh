set -eu
mkdir -p /DATA/harbor/source /DATA/harbor/rootfs /DATA/harbor/artifacts /DATA/harbor/vm
tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
cd /DATA/harbor/source
docker build -f os/Dockerfile.builder -t harbor-builder:0.1 . > /DATA/harbor/artifacts/builder.log 2>&1
docker run -d --name harbor-build --privileged -v /DATA/harbor/rootfs:/target -v /DATA/harbor/source:/source:ro harbor-builder:0.1
