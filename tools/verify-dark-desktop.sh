set -eu
systemctl is-active harbor.service
systemctl --failed --no-legend
python3 - <<'PY'
import json
from pathlib import Path
import ssl
import urllib.request
context=ssl.create_default_context(cafile='/var/lib/harbor/tls.crt')
with urllib.request.urlopen('https://192.168.1.97:8443/api/health',context=context,timeout=10) as response:
    health=json.load(response)
assert health['setup_required'] is False
print('HTTPS health:',health)
print('UI deployment:',json.loads(Path('/var/lib/harbor/ui-deployment.json').read_text())['interface'])
PY
