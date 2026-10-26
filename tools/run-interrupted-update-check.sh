set -eu
python3 /DATA/harbor/source/tools/transfer-vm-file.py /tmp/harbour-latest-release-worker.py /tmp/harbour-latest-release-worker.py
python3 /DATA/harbor/source/tools/guest-agent.py /tmp/harbour-interrupted-update-check.py
