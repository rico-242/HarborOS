set -eu
python3 /tmp/harbour-guest-agent.py /tmp/harbour-guest-final-report-0.3.py > /DATA/harbor/graphical-test/acceptance-result.json
cat /DATA/harbor/graphical-test/acceptance-result.json
