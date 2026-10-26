set -eu
python3 /DATA/harbor/source/tools/guest-agent.py /tmp/harbour-maintenance-report.py > /DATA/harbor/release/artifacts/maintenance-validation.json
cat /DATA/harbor/release/artifacts/maintenance-validation.json
