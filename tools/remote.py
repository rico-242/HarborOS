"""Workspace SSH utility. Password supplied only through HARBOR_SSH_PASSWORD."""
import argparse
import os
from pathlib import Path
import shlex
import sys
import base64
import hashlib
import re

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.local' / 'pylibs'))
import paramiko

parser = argparse.ArgumentParser()
parser.add_argument('--host', default='192.168.1.97')
parser.add_argument('--user', default='rico')
parser.add_argument('--sudo', action='store_true')
parser.add_argument('--guest', action='store_true', help='Connect to the private VM through the authenticated host, pinning its key to the trusted serial console.')
parser.add_argument('--script')
parser.add_argument('--input-password', action='store_true', help='Supply the existing password to a provisioning script over stdin.')
parser.add_argument('--upload', nargs=2, metavar=('LOCAL', 'REMOTE'))
parser.add_argument('--download', nargs=2, metavar=('REMOTE', 'LOCAL'))
args = parser.parse_args()
password = os.environ.get('HARBOR_SSH_PASSWORD')
client = paramiko.SSHClient()
host_client = None
client.load_system_host_keys(str(Path.home() / '.ssh' / 'known_hosts'))
client.set_missing_host_key_policy(paramiko.RejectPolicy())
try:
    client.connect(args.host, username=args.user, password=password,
                   look_for_keys=False, allow_agent=False, timeout=10)
    if args.guest:
        host_client = client
        inp, out, err = host_client.exec_command("sudo -S -p '' cat /DATA/harbor/vm/serial.log")
        inp.write(password + '\n')
        inp.flush()
        inp.channel.shutdown_write()
        console = out.read().decode(errors='replace')
        if out.channel.recv_exit_status():
            raise RuntimeError('Cannot read the trusted guest console.')
        fingerprints = re.findall(r'SHA256:([A-Za-z0-9+/]{43})', console)
        if not fingerprints:
            raise RuntimeError('Guest SSH fingerprint is not available from the trusted console.')
        expected = fingerprints[-1]
        class PinnedGuestKey(paramiko.MissingHostKeyPolicy):
            def missing_host_key(self, client, hostname, key):
                actual = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip('=')
                if actual != expected:
                    raise paramiko.SSHException('Guest SSH key differs from the trusted VM console.')
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(PinnedGuestKey())
        tunnel = host_client.get_transport().open_channel('direct-tcpip', ('127.0.0.1', 12222), ('127.0.0.1', 0))
        client.connect('harbor-vm', username=args.user, password=password, sock=tunnel,
                       look_for_keys=False, allow_agent=False, timeout=10)
    if args.upload:
        with client.open_sftp() as sftp:
            sftp.put(*args.upload)
    if args.download:
        Path(args.download[1]).parent.mkdir(parents=True, exist_ok=True)
        with client.open_sftp() as sftp:
            sftp.get(*args.download, max_concurrent_prefetch_requests=64)
    if args.script:
        script = Path(args.script).read_text(encoding='utf-8')
        command = 'sh -c ' + shlex.quote(script)
        if args.sudo:
            command = "sudo -S -p '' " + command
        stdin, stdout, stderr = client.exec_command(command)
        if args.sudo and password:
            stdin.write(password + '\n')
            stdin.flush()
        if args.input_password and password:
            stdin.write(password + '\n')
            stdin.flush()
        stdin.channel.shutdown_write()
        # Merge streams to avoid a full stderr pipe blocking command completion.
        channel = stdout.channel
        while True:
            if channel.recv_ready():
                sys.stdout.buffer.write(channel.recv(65536))
                sys.stdout.buffer.flush()
            if channel.recv_stderr_ready():
                sys.stderr.buffer.write(channel.recv_stderr(65536))
                sys.stderr.buffer.flush()
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                break
            import time
            time.sleep(0.05)
        sys.exit(channel.recv_exit_status())
finally:
    client.close()
    if host_client:
        host_client.close()
