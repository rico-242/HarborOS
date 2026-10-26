set -eu
docker ps -a --filter name=harbor-release --format '{{.Names}} {{.Status}}'
docker logs --tail 10 harbor-release-final 2>&1
ls -lh /DATA/harbor/release/artifacts
