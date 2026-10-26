set -eu
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends docker-cli
docker version --format '{{.Client.Version}} / {{.Server.Version}}'
systemctl --failed --no-pager
