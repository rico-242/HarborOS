set -eu
python3 /tmp/harbour-guest-agent.py /tmp/harbour-guest-install-complete.py
export HARBOR_TEST_SYSTEM_DISK=final-system.qcow2
sh /tmp/harbour-reboot-graphical-installed.sh
