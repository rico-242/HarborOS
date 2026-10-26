set -eu
docker ps -a --filter name=harbor- --format '{{.Names}} {{.Status}}'
docker logs --tail 25 harbor-package 2>&1 || true
ls -lh /DATA/harbor/artifacts
