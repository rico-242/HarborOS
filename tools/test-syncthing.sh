set -eu
umask 077
directory=$(mktemp -d /var/lib/harbor/syncthing-check.XXXXXX)
cleanup() {
  docker rm -f harbor-syncthing-check >/dev/null 2>&1 || true
  case "$directory" in /var/lib/harbor/syncthing-check.*) rm -rf -- "$directory";; esac
}
trap cleanup EXIT
chown 1000:1000 "$directory"
docker pull syncthing/syncthing:latest >/dev/null
docker run -d --name harbor-syncthing-check --user 1000:1000 --cap-drop=ALL --security-opt=no-new-privileges:true --memory=2g --cpus=2 -e STGUIADDRESS=0.0.0.0:8384 -v "$directory:/var/syncthing" -p 127.0.0.1:18384:8384 syncthing/syncthing:latest >/dev/null
for attempt in $(seq 1 60); do
  if curl --fail --silent --max-time 2 http://127.0.0.1:18384/rest/noauth/health; then
    printf '\nPASS: Syncthing starts without elevated container capabilities and returns a healthy response.\n'
    exit 0
  fi
  sleep 1
done
docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' harbor-syncthing-check
exit 1
