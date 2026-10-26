import json
from pathlib import Path
import subprocess
import sys
import tempfile

password = sys.stdin.readline().rstrip('\n')
assert password
config = json.loads(Path('/var/lib/harbor/config.json').read_text())
share = next((s['name'] for s in config['shares'] if s['name'].startswith('Verification')), 'Documents')
with tempfile.TemporaryDirectory(prefix='harbor-smb-') as directory:
    root = Path(directory)
    auth = root / 'auth'
    auth.write_text('username = rico\npassword = ' + password + '\n')
    auth.chmod(0o600)
    source = root / 'upload.txt'
    destination = root / 'download.txt'
    source.write_bytes(b'Harbor SMB integrity verification\n')
    result = subprocess.run(['smbclient', '//127.0.0.1/'+share, '-A', str(auth),
                             '-c', f'put {source} smb-test.txt; get smb-test.txt {destination}'],
                            capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise SystemExit(result.stderr + result.stdout)
    assert source.read_bytes() == destination.read_bytes()
    print('PASS: authenticated SMB upload/download with byte-for-byte integrity')
