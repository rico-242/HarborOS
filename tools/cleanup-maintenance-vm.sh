set -eu
python3 /DATA/harbor/source/tools/guest-agent.py /tmp/harbour-maintenance-cleanup.py
sh /DATA/harbor/source/tools/stop-graphical-test.sh
