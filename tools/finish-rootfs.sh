set -eu
tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
test -f /DATA/harbor/rootfs/etc/debian_version
test -f /DATA/harbor/rootfs/var/lib/dpkg/status
# Re-run the latest build script so source and boot recovery units match.
docker run -d --name harbor-finalize --privileged -v /DATA/harbor/rootfs:/target -v /DATA/harbor/source:/source:ro --entrypoint /bin/bash harbor-builder:0.1 /source/os/build-rootfs.sh
