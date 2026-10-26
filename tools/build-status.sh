set -eu
docker ps -a --filter name=harbor-build --format '{{.Names}} {{.Status}}'
tail -15 /DATA/harbor/artifacts/builder.log 2>/dev/null || true
docker logs --tail 20 harbor-build 2>&1 || true
