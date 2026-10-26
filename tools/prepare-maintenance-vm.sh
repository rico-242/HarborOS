set -eu
tar -xzf /tmp/harbor-source.tar.gz -C /DATA/harbor/source
test ! -e /DATA/harbor/graphical-test/guest.pid
sh /DATA/harbor/source/tools/reboot-graphical-installed.sh
