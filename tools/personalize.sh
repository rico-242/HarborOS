set -eu
test "$(docker inspect -f '{{.State.Status}}' harbor-release-final)" = exited
test "$(docker inspect -f '{{.State.ExitCode}}' harbor-release-final)" = 0
tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
sh /DATA/harbor/source/tools/prepare-appliance.sh
