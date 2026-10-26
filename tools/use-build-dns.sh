set -eu
resolvectl dns eth0 1.1.1.1 8.8.8.8
resolvectl flush-caches
timeout 12 getent ahostsv4 deb.debian.org | head -2
