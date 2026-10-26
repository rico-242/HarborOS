set -eu
python3 /tmp/harbour-guest-agent.py /tmp/harbour-guest-final-clean-check.py > /DATA/harbor/graphical-test/final-iso-validation.json
cat /DATA/harbor/graphical-test/final-iso-validation.json
