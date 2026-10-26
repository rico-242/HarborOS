set -eu
docker ps -a --filter name=harbor-vendor --format '{{.Names}} {{.Status}}'
docker logs --tail 15 harbor-vendor-test-build 2>&1
