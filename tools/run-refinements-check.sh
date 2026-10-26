set -eu
python3 /DATA/harbor/source/tools/guest-agent.py /DATA/harbor/source/tools/guest-refinements-check.py > /DATA/harbor/graphical-test/refinements-validation.json
cat /DATA/harbor/graphical-test/refinements-validation.json
