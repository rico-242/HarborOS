set -eu
docker top harbor-build -eo pid,ppid,etime,args
docker exec harbor-build sh -c 'ls -l /target/etc/debian_version /target/etc/resolv.conf; cat /target/etc/apt/sources.list; ps ax -o pid,etime,args | tail -15' || true
docker logs --tail 8 harbor-build
