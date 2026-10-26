set -eu
python3 /DATA/harbor/source/tools/transfer-vm-file.py /tmp/harbour-bad-release-test.bundle /tmp/harbour-bad-release-test.bundle
python3 /DATA/harbor/source/tools/guest-agent.py /DATA/harbor/source/tools/guest-maintenance-recovery.py
