set -eu
ip -j -d link show
ip -j address show
ip -j route show
networkctl list --no-pager
find /etc/systemd/network -maxdepth 1 -type f -print -exec cat {} \;
ethtool eth0 | head -18
systemctl is-active systemd-networkd NetworkManager
printf 'Network inspection complete.\n'
