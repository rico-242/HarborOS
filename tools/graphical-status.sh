set -eu
tail -18 /DATA/harbor/graphical-test/serial.log
ls -l /DATA/harbor/graphical-test/agent.sock
systemctl is-active harbour-test-vnc
