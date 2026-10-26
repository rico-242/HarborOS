import json,urllib.request,subprocess
from pathlib import Path
if 'boot=live' in Path('/proc/cmdline').read_text().split():
    value=json.load(urllib.request.urlopen('http://127.0.0.1:17081/api/status'));print(json.dumps(value))
else:
    print(urllib.request.urlopen('http://127.0.0.1:17080/api/health').read().decode())
print(subprocess.getoutput('systemctl is-active lightdm harbor qemu-guest-agent'))
print(subprocess.getoutput('ps -eo user,args | grep "chromium --" | grep -v grep')[:800])
