import json,subprocess,http.client
from pathlib import Path
report_path=Path('/root/harbour-0.3-acceptance.json');report=json.loads(report_path.read_text())
report['installed_boot_modes']=['UEFI','BIOS'] if not Path('/sys/firmware/efi').exists() else ['UEFI']
assert not Path('/sys/firmware/efi').exists(),'This verification expects the BIOS test boot'
assert subprocess.getoutput('systemctl is-active lightdm harbor docker smbd').splitlines()==['active']*4
assert ' /srv/harbor/storage ' in subprocess.getoutput('cat /proc/mounts')
accounts=json.loads(Path('/root/harbour-test-accounts.json').read_text());conn=http.client.HTTPConnection('127.0.0.1',17080)
conn.request('POST','/api/login',json.dumps({'username':accounts['owner'],'password':accounts['owner_password']}),{'Content-Type':'application/json'})
response=conn.getresponse();assert response.status==200;response.read()
report['bios_login_and_storage_persistence']=True
report_path.write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
