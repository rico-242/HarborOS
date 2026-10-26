set -eu
pkill -f '^python3 /tmp/harbor-test-live-install.py$' || true
python3 /tmp/harbor-test-live-install.py
