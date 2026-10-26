set -eu
timeout 8 ping -c 1 1.1.1.1 || true
timeout 10 resolvectl query deb.debian.org || true
ip -4 route
