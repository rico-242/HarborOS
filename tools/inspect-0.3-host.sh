set -eu
systemctl is-active harbor
df -h /DATA
apt-cache policy chromium lightdm openbox xserver-xorg-core plymouth | head -45
ls -ld /DATA/harbor/iso-build/root
test ! -f /DATA/harbor/iso-test/guest.pid && echo Previous-test-stopped
