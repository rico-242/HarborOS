import json,urllib.request,subprocess
from pathlib import Path
assert 'boot=live' in Path('/proc/cmdline').read_text().split()
health=json.load(urllib.request.urlopen('http://127.0.0.1:17080/api/health'))
installer=json.load(urllib.request.urlopen('http://127.0.0.1:17081/api/status'))
assert health['version']=='0.3.1' and installer['version']=='0.3.1'
assert health['setup_required'] and health['live']
for asset in ('widgets.js','process.js','refinements.css'):
    assert urllib.request.urlopen('http://127.0.0.1:17080/'+asset).status==200
assert subprocess.getoutput('systemctl is-active lightdm harbor harbor-installer').splitlines()==['active']*3
assert not Path('/var/lib/harbor/admin.json').exists()
for name in ('/usr/local/sbin/harbor-installer-server','/usr/local/sbin/harbor-install'):
    assert b'\r' not in Path(name).read_bytes().splitlines(keepends=True)[0]
print(json.dumps({'iso_version':'0.3.1','raw_usb_bios_boot':True,'graphical_services_active':True,'installer_ready':installer['phase']=='ready','new_assets_http_200':True,'fresh_owner_state':True,'linux_script_headers_valid':True}))
