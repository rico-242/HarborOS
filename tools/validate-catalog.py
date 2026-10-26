"""Validate every pinned manifest with Docker Compose without running containers."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'harbor'))
from appstore import OFFICIAL,prepare,project_name

good,bad=[],[]
with tempfile.TemporaryDirectory(prefix='harbor-catalog-') as temporary:
    for ident in OFFICIAL:
        try:
            plan=prepare(ident,'/srv/harbor/apps','/srv/harbor/storage')
            path=Path(temporary)/'compose.json'
            path.write_text(json.dumps(plan['compose']))
            result=subprocess.run(['docker-compose','-p',project_name(ident),'-f',str(path),'config','--quiet'],capture_output=True,text=True)
            if result.returncode:raise ValueError(result.stderr[-500:])
            good.append(ident)
        except Exception as error:
            bad.append({'id':ident,'reason':str(error)})
report={'valid':len(good),'total':len(OFFICIAL),'unsupported':bad}
print(json.dumps(report,indent=2))
