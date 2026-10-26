"""Find this NAS after DHCP changes, matching its existing SSH public key before authentication."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import socket
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.local' / 'pylibs'))
import paramiko

known = paramiko.HostKeys(str(Path.home()/'.ssh'/'known_hosts'))
expected = known['192.168.1.97']['ssh-ed25519'].asbytes()

def check(number):
    host = '192.168.1.' + str(number)
    transport = None
    connection = None
    try:
        connection = socket.create_connection((host,22),timeout=.6)
        transport = paramiko.Transport(connection)
        transport.start_client(timeout=2)
        if transport.get_remote_server_key().asbytes() == expected:
            return host
    except Exception:
        pass
    finally:
        if transport: transport.close()
        elif connection: connection.close()

with ThreadPoolExecutor(max_workers=32) as workers:
    matches = [host for host in workers.map(check, range(1,255)) if host]
print('Matching NAS SSH identity: ' + (', '.join(matches) or 'not reachable yet'))
