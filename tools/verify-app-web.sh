set -eu
python3 - <<'PY'
import http.client,json,time
from pathlib import Path
root=Path('/DATA/harbor/iso-test')
deadline=time.monotonic()+100
while time.monotonic()<deadline:
    try:
        connection=http.client.HTTPConnection('127.0.0.1',19384,timeout=4)
        connection.request('GET','/')
        response=connection.getresponse();body=response.read()
        connection.close()
        if response.status==200 and b'Syncthing' in body:
            report=json.loads((root/'acceptance-result.json').read_text())
            report['app_web_ui']='Syncthing HTTP 200 with application page after reboot'
            (root/'acceptance-result.json').write_text(json.dumps(report,indent=2))
            print('Syncthing web interface is serving HTTP 200 after reboot.')
            break
    except OSError:pass
    time.sleep(2)
else:raise RuntimeError('Syncthing did not serve its web interface after reboot')
PY
