set -eu
test "$(docker inspect -f '{{.State.Status}}' harbor-final-pass-2)" = exited
test "$(docker inspect -f '{{.State.ExitCode}}' harbor-final-pass-2)" = 0
docker run -d --name harbor-subdir-build --privileged -v /dev:/dev -v /DATA/harbor:/work -v /DATA/harbor/rootfs:/target:ro --entrypoint /bin/bash harbor-image-builder:0.1 /work/source/os/build-subdir-test.sh
