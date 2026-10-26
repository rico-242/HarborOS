set -eu
tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
python3 /DATA/harbor/source/tools/stop-vm.py 2>/dev/null || true
docker run -d --name harbor-vendor-test-build --privileged -v /dev:/dev -v /DATA/harbor:/work -v /DATA/harbor/rootfs:/target:ro -v /DATA/harbor/source:/source:ro -v /mnt/boot/EFI/BOOT:/esp:ro --entrypoint /bin/bash harbor-image-builder:0.1 /source/os/build-vendor-efi-test.sh
