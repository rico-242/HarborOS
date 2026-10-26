import argparse
import os
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.local' / 'pylibs'))
import paramiko

parser = argparse.ArgumentParser(description='Read-only wait for Harbor SSH and optional reboot identity change.')
parser.add_argument('--after-boot-id')
args = parser.parse_args()

deadline = time.monotonic() + 55
last = 'Waiting for SSH after reboot.'
while time.monotonic() < deadline:
    client = paramiko.SSHClient()
    client.load_system_host_keys(str(Path.home()/'.ssh'/'known_hosts'))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    try:
        client.connect('192.168.1.97', username='rico', password=os.environ['HARBOR_SSH_PASSWORD'],
                       look_for_keys=False, allow_agent=False, timeout=3, banner_timeout=4, auth_timeout=4)
        _, out, err = client.exec_command('cat /etc/os-release; uname -r; hostname -I; cat /proc/sys/kernel/random/boot_id')
        result = out.read().decode()
        if 'ID=harbor' in result and (not args.after_boot_id or args.after_boot_id not in result):
            print(result)
            client.close()
            sys.exit(0)
        last = 'SSH is reachable, but the host still reports the previous operating system.'
    except Exception as error:
        last = type(error).__name__
    finally:
        client.close()
    time.sleep(3)
print('Harbor is not reachable yet: ' + last)
sys.exit(1)
