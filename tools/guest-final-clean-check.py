import json,http.client,ssl,subprocess
from pathlib import Path
assert 'boot=live' not in Path('/proc/cmdline').read_text().split()
conn=http.client.HTTPConnection('127.0.0.1',17080);conn.request('GET','/api/health');response=conn.getresponse();health=json.loads(response.read())
assert health['version']=='0.3.0' and health['setup_required'] and health['local_console'] and not health['live']
assert not Path('/var/lib/harbor/setup-token').exists()
assert not Path('/var/lib/harbor/admin.json').exists()
assert not Path('/var/lib/harbor/members.json').exists()
assert not Path('/etc/systemd/system/getty@tty2.service.d/harbor-live.conf').exists()
context=ssl.create_default_context(cafile='/var/lib/harbor/tls.crt')
public=http.client.HTTPSConnection('127.0.0.1',8443,context=context);public.request('GET','/api/setup-session');response=public.getresponse();assert response.status==403;response.read()
assert subprocess.getoutput('systemctl is-active lightdm harbor smbd docker').splitlines()==['active']*4
print(json.dumps({'final_iso_offline_install':True,'final_iso_raw_usb_bios_boot':True,'final_iso_installed_uefi_boot':Path('/sys/firmware/efi').exists(),'fresh_account_state':True,'setup_code_absent':True,'public_setup_denied':True,'graphical_services_active':True}))
