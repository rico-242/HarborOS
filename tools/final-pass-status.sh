set -eu
docker ps -a --filter name=harbor- --format '{{.Names}} {{.Status}}'
docker logs --tail 30 harbor-final-pass-2 2>&1
