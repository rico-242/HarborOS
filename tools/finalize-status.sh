set -eu
docker ps -a --filter name=harbor- --format '{{.Names}} {{.Status}}'
printf '\n--- Original builder ---\n'
docker top harbor-build -eo pid,stat,etime,args 2>/dev/null || true
docker logs --tail 8 harbor-build 2>&1 || true
printf '\n--- Finalizer ---\n'
docker logs --tail 20 harbor-finalize 2>&1 || true
printf '\n--- Array ---\n'
cat /proc/mdstat
