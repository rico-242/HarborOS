set -eu
systemctl is-active --quiet harbor.service
python3 - <<'PY'
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile

names={'index.html','app.js','style.css','favicon.svg'}
state=Path('/var/lib/harbor')
stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
backup=state/'ui-backups'/stamp
stage=state/('ui-stage-'+stamp)
live=Path('/opt/harbor/web')
backup.mkdir(parents=True)
stage.mkdir(mode=0o700)
with tarfile.open('/tmp/harbor-desktop-ui.tar.gz','r:gz') as archive:
    members=archive.getmembers()
    assert {m.name for m in members}==names and len(members)==len(names)
    assert all(m.isfile() and m.name in names for m in members)
    archive.extractall(stage,filter='data')
for name in names:
    shutil.copy2(live/name,backup/name)
for name in ('style.css','app.js','favicon.svg','index.html'):
    (stage/name).chmod(0o644)
    os.replace(stage/name,live/name)
source=Path('/DATA/harbor/source/harbor/web')
source.mkdir(parents=True,exist_ok=True)
for name in names:
    shutil.copy2(live/name,source/name)
stage.rmdir()
report={'interface':'Dark desktop','deployed':stamp,'backup':str(backup),
        'sha256':{name:hashlib.sha256((live/name).read_bytes()).hexdigest() for name in sorted(names)}}
(state/'ui-deployment.json').write_text(json.dumps(report,indent=2))
print('Dark desktop deployed. Previous UI saved at '+str(backup))
print(json.dumps(report['sha256'],indent=2))
PY
systemctl is-active harbor.service
