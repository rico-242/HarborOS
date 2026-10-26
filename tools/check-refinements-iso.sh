set -eu
python3 /DATA/harbor/source/tools/guest-agent.py /tmp/harbour-refinements-iso-check.py > /DATA/harbor/graphical-test/refinements-iso-validation.json
cat /DATA/harbor/graphical-test/refinements-iso-validation.json
